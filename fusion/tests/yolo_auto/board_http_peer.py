"""A small Ethernet/TCP peer exercises the actual bundled lwIP in a DLL.
No sockets, board, firewall changes, or fake implementations of tcp_write.
"""
from pathlib import Path
import ctypes as C, struct, json, unittest

ROOT=Path(__file__).resolve().parents[1]
CLIENT=b'\x02\0\0\0\0\x03';SERVER=bytes.fromhex('025449360002')
CIP=bytes([192,168,0,3]);SIP=bytes([192,168,0,2])

def checksum(data):
    if len(data)%2:data+=b'\0'
    n=sum(struct.unpack('!%dH'%(len(data)//2),data))
    while n>>16:n=(n&65535)+(n>>16)
    return (~n)&65535

class Stack:
    def __init__(self):
        self.lib=C.CDLL(str(ROOT/'verification/host_build/monitor_stack.dll'))
        self.lib.stack_input.argtypes=[C.c_char_p,C.c_uint]
        self.lib.stack_pop.argtypes=[C.c_void_p];self.lib.stack_pop.restype=C.c_uint
        assert self.lib.stack_init()==1
        self.inject(SERVER+CLIENT+b'\x08\x06'+struct.pack('!HHBBH',1,0x800,6,4,1)+CLIENT+CIP+b'\0'*6+SIP)
        self.pop_all();self.nextport=16000
    def inject(self,frame):assert self.lib.stack_input(frame,len(frame))==1
    def pop_all(self):
        out=[];buf=C.create_string_buffer(1600)
        while True:
            n=self.lib.stack_pop(buf)
            if not n:return out
            out.append(buf.raw[:n])
    def tick(self,n=250):self.lib.stack_tick(n)

class Peer:
    def __init__(self,stack,window=1460):
        self.s=stack;self.port=stack.nextport;stack.nextport+=1
        self.seq=1000;self.ack=0;self.window=window;self.data=bytearray();self.pending={};self.finished=False
        self.send(flags=2);self.seq+=1
        syn=[p for p in self.packets() if p['flags']&2]
        assert syn,'no SYN ACK';self.ack=syn[0]['seq']+1;self.send(flags=16)
    def send(self,data=b'',flags=24,corrupt=False):
        tcp=struct.pack('!HHIIBBHHH',self.port,80,self.seq,self.ack,5<<4,flags,self.window,0,0)+data
        pseudo=CIP+SIP+struct.pack('!BBH',0,6,len(tcp));check=checksum(pseudo+tcp)
        if corrupt:check^=1
        tcp=tcp[:16]+struct.pack('!H',check)+tcp[18:]
        ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(tcp),1,0,64,6,0,CIP,SIP)
        ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
        self.s.inject(SERVER+CLIENT+b'\x08\0'+ip+tcp)
    def packets(self):
        out=[]
        for frame in self.s.pop_all():
            if frame[12:14]!=b'\x08\0':continue
            ip=frame[14:];ihl=(ip[0]&15)*4;length=struct.unpack_from('!H',ip,2)[0]
            assert checksum(ip[:ihl])==0
            tcp=ip[ihl:length]
            if ip[9]!=6:continue
            assert checksum(ip[12:20]+struct.pack('!BBH',0,6,len(tcp))+tcp)==0,'bad TCP checksum'
            sp,dp,seq,ack,off,flags,win,_,_=struct.unpack_from('!HHIIBBHHH',tcp)
            if dp!=self.port:continue
            out.append(dict(seq=seq,ack=ack,flags=flags,data=tcp[(off>>4)*4:]))
        return out
    def collect(self,drop_first=False):
        dropped=False
        for _ in range(200):
            packets=self.packets()
            for p in packets:
                assert not p['flags']&4,'unexpected reset'
                if p['data']:
                    if drop_first and not dropped:dropped=True;continue
                    self.pending[p['seq']]=p['data']
                    while self.ack in self.pending:
                        data=self.pending.pop(self.ack);self.data.extend(data);self.ack+=len(data)
                    self.send(flags=16)
                if p['flags']&1 and p['seq']+len(p['data'])==self.ack:
                    self.ack+=1;self.finished=True;self.send(flags=16)
            if self.finished:
                self.send(flags=17);self.seq+=1;self.s.pop_all();return bytes(self.data),dropped
            self.s.tick()
        raise AssertionError('TCP response timed out')
    def get(self,path):
        req=f'GET {path} HTTP/1.1\r\nHost: ti60\r\n\r\n'.encode();self.send(req);self.seq+=len(req)
        return self.collect()[0]

