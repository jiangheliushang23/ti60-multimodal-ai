"""Execute the compiled transfer helper on RV32 and validate host integrity rules."""
from pathlib import Path
import hashlib,json,struct,sys,tempfile,unittest,zlib
from collections import deque
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
sys.path.insert(0,str(SW))
from yolo_auto_uart import HEADER,UartDownloader,check_application_range,validate_loader
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.riscv_const import UC_RISCV_REG_PC

class Target:
 def __init__(self):
  self.rx=deque();self.tx=bytearray();self.uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32)
  self.uc.mem_map(0,0x1000000);self.uc.mem_map(0xf8010000,0x1000);self.uc.mem_map(0xf8b0b000,0x1000)
  self.uc.mem_write(0xc00000,validate_loader());self.pc=0xc00000
  def read(uc,access,address,size,value,context):
   if address==0xf8010004:
    following=int.from_bytes(uc.mem_read(uc.reg_read(UC_RISCV_REG_PC)+4,4),'little')
    if not self.rx and following&0xfff0707f==0x01805013:uc.emu_stop()
    uc.mem_write(address,struct.pack('<I',128<<16|int(bool(self.rx))<<24))
   elif address==0xf8010000:
    uc.mem_write(address,struct.pack('<I',self.rx.popleft() if self.rx else 0))
  def write(uc,access,address,size,value,context):
   if address==0xf8010000:self.tx.append(value&255)
  def code(uc,pc,size,context):
   # Unicorn has coherent RAM and no Sapphire custom cache opcode. Only that
   # cache barrier is skipped; actual compiled UART, copy and CRC code executes.
   if bytes(uc.mem_read(pc,4))==b'\x0f\x50\x00\x00':uc.reg_write(UC_RISCV_REG_PC,pc+4)
  self.uc.hook_add(UC_HOOK_MEM_READ,read,begin=0xf8010000,end=0xf8010004)
  self.uc.hook_add(UC_HOOK_MEM_WRITE,write,begin=0xf8010000,end=0xf8010000)
  self.uc.hook_add(UC_HOOK_CODE,code)
 def exchange(self,packet):
  self.rx.extend(packet);self.tx.clear();self.uc.emu_start(self.pc,0,count=2000000)
  self.pc=self.uc.reg_read(UC_RISCV_REG_PC)
  return bytes(self.tx)

class LoaderTests(unittest.TestCase):
 def setUp(self):self.target=Target()
 def call(self,cmd,address=0,size=0,checksum=0,payload=b'',seq=91):
  out=self.target.exchange(HEADER.pack(b'YULQ',cmd,seq,address,size,checksum)+payload)
  self.assertGreaterEqual(len(out),24);header=HEADER.unpack(out[:24]);self.assertEqual(header[:3],(b'YULR',cmd,seq))
  return header,out[24:]
 def test_compiled_full_write_read_and_finish(self):
  h,_=self.call(1);self.assertEqual(h[3:],(0,4096,0x10001))
  data=bytes((i*73+17)&255 for i in range(4096));crc=zlib.crc32(data)
  h,_=self.call(2,0x1000,len(data),crc,data);self.assertEqual(h[3:],(0,0,crc))
  h,out=self.call(3,0x1000,len(data));self.assertEqual(out,data);self.assertEqual(h[3:],(0,len(data),crc))
  h,_=self.call(4,0x1000,len(data),crc);self.assertEqual(h[3:],(0,0,crc))
  self.assertGreaterEqual(self.target.pc,0xc00000) # No automatic application launch.
 def test_crc_failure_does_not_overwrite_firmware(self):
  self.target.uc.mem_write(0x1000,b'ORIGINAL')
  h,_=self.call(2,0x1000,8,123,b'CORRUPT!');self.assertEqual(h[3],3)
  self.assertEqual(bytes(self.target.uc.mem_read(0x1000,8)),b'ORIGINAL')
 def test_out_of_range_and_oversized_requests(self):
  for cmd,address,size in [(2,0xc00000,4),(3,0xff0,32),(3,0xbffff0,32),(2,0x1000,4097),(4,0x1000,0)]:
   h,_=self.call(cmd,address,size);self.assertEqual(h[3],1)
 def test_wrong_whole_image_crc_is_rejected(self):
  h,_=self.call(4,0x1000,64,123);self.assertEqual(h[3],4)
 def test_partial_unaligned_last_block(self):
  data=b'last seven!';h,_=self.call(2,0x2003,len(data),zlib.crc32(data),data)
  self.assertEqual(h[3],0);h,out=self.call(3,0x2003,len(data));self.assertEqual(out,data)
 def test_host_rejects_valid_crc_for_wrong_bytes_and_does_not_finish(self):
  class FakeSerial:
   def __init__(s):s.pending=bytearray();s.commands=[]
   def write(s,packet):
    _,cmd,seq,address,size,checksum=HEADER.unpack(packet[:24]);s.commands.append(cmd)
    if cmd==1:n,crc=4096,0x10001;body=b''
    elif cmd==2:n,crc=0,checksum;body=b''
    else:body=b'X'*size;n,crc=size,zlib.crc32(body)
    s.pending.extend(HEADER.pack(b'YULR',cmd,seq,0,n,crc)+body);return len(packet)
   def flush(s):pass
   def read(s,n):out=bytes(s.pending[:n]);del s.pending[:n];return out
  with tempfile.TemporaryDirectory() as folder:
   uart=FakeSerial();loader=UartDownloader(uart,folder,lambda _:None);loader.recover=lambda:None
   with self.assertRaisesRegex(RuntimeError,'读回与固件不一致'):loader.download(b'A'*17)
   self.assertNotIn(4,uart.commands)
   self.assertEqual((Path(folder)/'readback.bin').read_bytes(),b'')
 def test_current_application_fits_scratch_exclusion(self):
  check_application_range(SW/'build_multimodal_live/tinyml_yolo_compat.elf',(SW/'build_multimodal_live/tinyml_yolo_compat.bin').read_bytes())

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LoaderTests))
 out=ROOT/'fusion/ti60_yolo_auto/validation/uart_download';out.mkdir(exist_ok=True)
 files=[Path(__file__),SW/'yolo_auto_uart.py',ROOT/'delivery/uart_loader/build/result.json',ROOT/'delivery/uart_loader/build/uart_loader.bin']
 report=dict(complete=True,passed=result.wasSuccessful(),board_accessed=False,compiled_rv32_executed=True,tests_run=result.testsRun,
             inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');sys.exit(not result.wasSuccessful())
