"""Send one harmless message to the demo listener. No attack traffic."""
import argparse
import socket
parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,default=5514)
args=parser.parse_args()
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    sock.sendto(b'<134>demo system,info MikroSOC loopback connectivity test',('127.0.0.1',args.port))
print('Sent one UDP test message. Look for it in Live logs (demo mode only).')
