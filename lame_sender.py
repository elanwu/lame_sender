#!/bin/python3

# Not complete Xmodem serial file (e.g. binary mcu firmware) transmiting program.
# Free to use, with your own risk.
# elanwu@yeah.net

import serial
import hashlib
import datetime
import struct
import time
import binascii
import random

## DESIGNATE: 1) BINARY FIRMWARE FILE NAME, 2) SERIAL PORT ##
BIN_FW_NAME = 'a.bin'
SER_PORT_NAME_DEFAULT = ('COM11', 'COM7', '/dev/ttyUSB0')[1]    # 0,1,2 ...

SOH = b'\x01'
NAK = b'\x15'
ACK = b'\x06'



def find_a_valid_serial_port_name():
    n = 32
    name = ''
    i = -1
    
    for i in range(n, -2, -1):
        name = "COM{}".format(i)
        try:
            s = serial.Serial(name)
            s.close()
            del s
            break;
        except Exception as e:
           print('.', end='') 

        name = "/dev/ttyUSB{}".format(i)
        try:
            s = serial.Serial(name)
            s.close()
            del s
            break;
        except Exception as e:
           print(',', end='') 

    if i < 0:
        name = ''

    return name


def calc_file_sha256_str(fn: str) -> str:
    '''
    Indentify a file by its sha256 digest.
    '''
    with open(fn, "rb") as f:
        s = hashlib.sha256()
        s.update(f.read())
        digest = s.digest().hex()
    return digest


def slice_file_into_128_bytes_blocks(fn: str) -> [bytes]:
    '''
    Slice file content into 128 bytes blocks, 
    and fill last insufficient block with 0x1A as Xmodem protocal required.
    '''
    ## 1/2 ##
    blocks = []
    with open(fn, "rb") as f:
        while True:
            blk_128byte = f.read(128)
            if blk_128byte == b'':          # read() Returns an empty bytes object on EOF.
                break;
            else:
                blocks.append(blk_128byte)

    ## 2/2 ##
    lst_block_len = len(blocks[-1])
    if lst_block_len < 128:
        blocks[-1] += b'\x1A' * (128 - lst_block_len)

    return blocks


def calc_xmodem_crc_byte(byts: bytes) -> bytes:
    crc = 0
    for b in byts:
        crc += int(b)

    crc &= 0xff 
    return struct.pack('B', crc)


def xmodem_transive(blks: [bytes], ser: serial.Serial):
    ser.apply_settings({'timeout': 2.7})

    tp1 = datetime.datetime.now()
    i = 0
    rpt = 0
    unit = b''
    while True:

        # Each block of the transfer looks like:
        # <SOH><blk #><255-blk #><--128 data bytes--><cksum>
        xmd_idx = (i + 1) & 0xff
        blk = blks[i]
        unit = SOH + struct.pack('BB', xmd_idx, 255-xmd_idx) + blk + calc_xmodem_crc_byte(blk)

        #incoming = ser.read_all()
        incoming = ser.read(1)

        # (reading) timeout expired, ACK/NAK get garbaged?
        #   or NAK received, resent in both situation.
        if incoming == b'' or NAK in incoming:
            rpt += 1
            print("{:03d}/{:03d} blocks repeating {}\r".format(i, len(blocks), '.' * rpt), end='')
            time.sleep(0.1 + (rpt / 70) * random.random())

        # procced.
        elif ACK in incoming:
            i+=1
            rpt = 0
            print("{:03d}/{:03d} blocks transmited".format(i, len(blocks)))
            time.sleep(0.03)

        # quit loop if retry too much or finished.
        if 10 < rpt or i == len(blks):  
            break

        ser.reset_input_buffer()
        ser.write(unit)

    # Note: no SENDRE EOT here, as RECIEVER will timeout.
    time.sleep(3)
    response = ser.read_all()
    tp2 = datetime.datetime.now()

    # TODO: failed when i != len(blocks)?
    # TODO: check XIC in response against calculated one, whether they two match.
    print("{:03d}/{:03d} blocks transmited in {} seconds".format(i, len(blocks), (tp2-tp1).seconds))
    print("response:<{}>".format(response))


if __name__ == "__main__":
    print('lame_sender V0.1.2')

    serial_port_name = find_a_valid_serial_port_name()
    print('serial_port_found:<{}>'.format(serial_port_name))

    SER_PORT_NAME = SER_PORT_NAME_DEFAULT if serial_port_name == '' else serial_port_name
    print('bin_firmware_file:<{}>, serial_port:<{}>'.format(BIN_FW_NAME, SER_PORT_NAME))

    dgst = calc_file_sha256_str(fn=BIN_FW_NAME)
    print("bin_firware_file:<{}> is found, with sha256 digest:<{}>.".format(BIN_FW_NAME, dgst[0:5]))

    ser = serial.Serial(SER_PORT_NAME, 9600)           # open serial port.
    print("serial_port:<{}> is opened, with init config:<{}>, 9600,8N1 is expected.".format(SER_PORT_NAME, ser.get_settings()))

    blocks = slice_file_into_128_bytes_blocks(fn=BIN_FW_NAME)
    
    xmodem_transive(blks=blocks, ser=ser)
    
    print('Done')
    input('Press any key to exit ...')



'''
XIC: printf("XIC:<%C%C>", ('H' + (sum >> 4)), ('H' + (sum & 0x0f)));

http://techheap.packetizer.com/communication/modems/xmodem.html

  -------- 1. DEFINITIONS.

 <soh> 01H
 <eot> 04H
 <ack> 06H
 <nak> 15H
 <can> 18H

 -------- 3. MESSAGE BLOCK LEVEL PROTOCOL

 Each block of the transfer looks like:
 <SOH><blk #><255-blk #><--128 data bytes--><cksum>
    in which:

 <SOH>       = 01 hex
 <blk #>     = binary number, starts at 01 increments by 1, and
               wraps 0FFH to 00H (not to 01)
 <255-blk #> = blk # after going thru 8080 "CMA" instr.
               Formally, this is the "ones complement".
 <cksum>     = the sum of the data bytes only.  Toss any carry.



 -------- 5. DATA FLOW EXAMPLE INCLUDING ERROR RECOVERY

Here is a sample of the data flow, sending a 3-block message.
It includes the two most common line hits - a garbaged block,
and an <ack> reply getting garbaged.  <xx> represents the
checksum byte.

  SENDER                           RECIEVER
                                   Times out after 10 seconds,
                           <---    <nak>
  <soh> 01 FE -data- <xx>   --->
                           <---    <ack>
  <soh> 02 FD -data- <xx>   --->   (data gets line hit)
                           <---    <nak>
  <soh> 02 FD -data- <xx>   --->
                           <---    <ack>
  <soh> 03 FC -data- <xx>   --->
    (ack gets garbaged)    <---    <ack>
  <soh> 03 FC -data- <xx>   --->
                           <---    <ack>
  <eot>                     --->
                           <---    <ack>

'''

