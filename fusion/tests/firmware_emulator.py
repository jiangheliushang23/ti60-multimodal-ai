"""Execute the linked Sapphire firmware against independent MMIO/sensor models.

This is ISA/algorithm verification, not a measurement of FPGA execution time.
"""
from pathlib import Path
import sys,struct,json,time,hashlib,re
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tools/thermal_python'))
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_PC
from elftools.elf.elffile import ELFFile
legacy=root/'sensors/ir_thermal_hdmi_v3_20260930/tests'
build=root/'fusion/demo_multimodal/software/standalone/tinyml_pdti8/build'
out=root/'fusion/ti60_multimodal/validation'
uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32)
uc.mem_map(0,0x4000000);uc.mem_map(0xf8100000,0x10000);uc.mem_map(0xf8010000,0x1000)
uc.mem_write(0x1000,(build/'tinyml_pdti8.bin').read_bytes())
ee=[int(x,16) for x in (legacy/'eeprom.hex').read_text().split()]
frame=[int(x,16) for x in (legacy/'frame.hex').read_text().split()]
expected=json.loads((legacy/'expected.json').read_text())
def put(a,v):uc.mem_write(a,struct.pack('<I',v&0xffffffff))
def get(a):return struct.unpack('<I',uc.mem_read(a,4))[0]
case=sys.argv[1] if len(sys.argv)>1 else 'normal'
expected_status={'nack':2,'overrun':3,'bus_timeout':4,'no_new_data':5,'bad_eeprom':6,'bad_math':7}.get(case,1)
if case=='bad_eeprom':ee[48]=0
if case=='bad_math':frame[778]=0
if case in ('cold','hot'):
 lo,hi=(-30,5) if case=='cold' else (80,250)
 alpha=108/2**30;emiss=.95;ta=25;tr=17
 tatr=(tr+273.15)**4-((tr+273.15)**4-(ta+273.15)**4)/emiss
 expected['temperatures']=[]
 for i in range(768):
  target=lo+(hi-lo)*(i%32)/31
  raw=round(1000+emiss*alpha*((target+273.15)**4-tatr));frame[i]=raw&65535
  expected['temperatures'].append((((raw-1000)/emiss/alpha+tatr)**.25)-273.15)
data_blocked=case in ('no_new_data','recover_no_data')
control=0x1981;fresh=0 if data_blocked else 1;page=0
timer=0xfffffc00 if case=='timer_wrap' else 0
bus_busy=0;bus_wait_sht_reads=0;display_wait_sht_reads=0;calculation_yields=set()
with (build/'tinyml_pdti8.elf').open('rb') as f:
 symbols={s.name:s['st_value'] for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols()}
pixel_cursor_addr=next(v for k,v in symbols.items() if k.endswith('pixel_cursor'))
commits=[];transactions=0;pending=0;ack=0;display_busy=0;image_writes=0;uart=bytearray()
put(0xf8100000,0x4d4d4631);put(0xf8100004,0x10000);put(0xf8101000,0x46555331)
put(0xf8102000,1);put(0xf8102004,0x66667777);put(0xf8102008,0x2500);put(0xf8102010,0x5000);put(0xf8102014,1)
if case=='wrong_id':put(0xf8101000,0x50445449)
def read_hook(uc,access,address,size,value,data):
 global timer,fresh,page,pending,ack,display_busy,bus_busy,bus_wait_sht_reads,display_wait_sht_reads
 if address in (0xf8100008,0xf8103014):timer=(timer+10)&0xffffffff;put(address,timer)
 if address==0xf8010004:put(address,16<<16)
 if address==0xf8102014:
  if bus_busy:bus_wait_sht_reads+=1
  if display_busy:display_wait_sht_reads+=1
  cursor=get(pixel_cursor_addr)
  if 0<cursor<768:calculation_yields.add(cursor)
 if address==0xf8103000:
  busy=case=='bus_timeout' or (case=='recover_timeout' and transactions==1) or bus_busy>0
  put(address,int(busy))
  if bus_busy:bus_busy-=1
 if address==0xf8101004:
  if display_busy:
   display_busy-=1
   if not display_busy:ack^=1
  put(address,4|(ack<<1)|bool(display_busy))
 if address==0xf8104000 and pending:
  if not data_blocked:fresh=1;page^=1
  pending=0
def write_hook(uc,access,address,size,value,data):
 global control,fresh,page,transactions,pending,display_busy,image_writes,bus_busy,data_blocked
 if address==0xf8010000:
  uart.append(value&255)
  if b'FATAL ' in uart and value==10:uc.emu_stop()
 elif 0xf8106000<=address<0xf8106c00:
  assert not display_busy,'Image modified before ACK';image_writes+=1
 elif 0xf8101020<=address<0xf8101058:assert not display_busy,'Record modified before ACK'
 elif address==0xf8103000:
  reg=get(0xf8103004);w=get(0xf8103008);n=get(0xf810300c);read=bool(value&2)
  transactions+=1;put(0xf8103018,transactions);put(0xf810301c,timer)
  bus_busy=12 if case=='delayed_bus' else 0
  if case=='nack' or (case=='transient_nack' and transactions==1) or (case=='recover_nack' and transactions<=3):
   put(0xf8103010,2);return
  if read:
   if reg==0x2400:assert n==832;words=ee
   elif reg==0x800d:assert n==1;words=[control]
   elif reg==0x8000:words=[(8 if fresh else 0)|page]
   elif reg==0x0400:
    assert n==832;words=frame
    if case=='overrun':fresh=1
   else:raise AssertionError(f'Unexpected read {reg:04x}')
   for i,x in enumerate(words):put(0xf8104000+4*i,x)
   if reg==0x8000 and not fresh:pending=1
   elif reg==0x8000 and pending:pending=0
  else:
   assert n==1
   if reg==0x800d:assert w==0x1981;control=w
   elif reg==0x8000:assert w==0x30;fresh=0
   else:raise AssertionError('Forbidden sensor write')
  put(0xf8103010,1)
 elif address==0xf8101018:
  assert not display_busy,'Commit while busy'
  record=[get(0xf8101020+4*i) for i in range(14)];commits.append(record)
  put(0xf8101010,len(commits))
  display_busy=100000 if case=='display_timeout' else 12 if case=='delayed_display' else 3
  if case=='recover_no_data' and record[0]==5:data_blocked=False;fresh=1
  if record[0]==expected_status:
   if case!='steady' or sum(r[0]==1 for r in commits)>=5:uc.emu_stop()
  elif record[0] not in (0,1,8):
   recovery_status={'recover_nack':2,'recover_timeout':4,'recover_no_data':5}.get(case)
   assert record[0]==recovery_status,f'Firmware error {record}'
uc.hook_add(UC_HOOK_MEM_READ,read_hook,begin=0xf8000000,end=0xf81fffff)
uc.hook_add(UC_HOOK_MEM_WRITE,write_hook,begin=0xf8000000,end=0xf81fffff)
start=time.time()
try:uc.emu_start(0x1000,0x4000000,count=100_000_000)
except Exception:
 pc=uc.reg_read(UC_RISCV_REG_PC)
 print('Emulator exception at',hex(pc),'bytes',uc.mem_read(pc,16).hex(),'UART',uart)
 raise
(out/('firmware_emulator_'+case+'.log')).write_bytes(uart)
report={'case':case,'hardware_measurements':False,'transactions':transactions,'image_writes':image_writes,
 'firmware_sha256':hashlib.sha256((build/'tinyml_pdti8.bin').read_bytes()).hexdigest()}
if case=='display_timeout':
 assert b'FATAL display_timeout' in uart and image_writes==0 and transactions==0
 assert display_wait_sht_reads>0,'Display ACK wait starved SHT service'
elif case=='wrong_id':
 assert b'FATAL register_id_mismatch' in uart and not commits and not transactions
elif expected_status!=1:
 assert commits and commits[-1][0]==expected_status,(commits,hex(uc.reg_read(UC_RISCV_REG_PC)))
 assert image_writes==0,'Error published an image'
 if case=='nack':assert transactions==3,'NACK retry must be bounded'
else:
 assert commits and commits[-1][0]==1,(commits,hex(uc.reg_read(UC_RISCV_REG_PC)),uart)
 with (build/'tinyml_pdti8.elf').open('rb') as f:
  symbols={s.name:s['st_value'] for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols()}
 temps_addr=next(v for k,v in symbols.items() if k.endswith('temperatures'))
 temps=struct.unpack('<768f',uc.mem_read(temps_addr,3072))
 error=max(abs(a-b) for a,b in zip(temps,expected['temperatures']));assert error<0.02,error
 centi=[int(t*100+(.5 if t>=0 else -.5)) for t in temps];ordered=sorted(centi)
 low=((ordered[15]+4000)//25)*25-4050;high=((ordered[-16]+4000)//25+1)*25-3950
 if high-low<500:mid=int((low+high)/2);low=mid-250;high=low+500
 def bcd(q):return (0x80000000 if q<0 else 0)|int(str(abs(q)),16)
 assert commits[-1][7:11]==[bcd(low),bcd(high),centi.index(max(centi)),1],commits[-1]
 assert commits[-1][1:4]==[bcd(min(centi)),bcd(max(centi)),bcd(centi[400])],commits[-1]
 assert all((n>>(4*i))&15<10 for n in commits[-1][11:14] for i in range(4))
 if case=='steady':assert commits[-1][13]>0
 image=[get(0xf8106000+4*i) for i in range(768)]
 assert image==[max(0,min(255,int((t-low)*255/(high-low)))) for t in centi]
 report.update(max_error_c=error,record=commits[-1],reference='Independent synthetic inverse radiance model')
 if case=='transient_nack':assert b'IR_RETRY status=2' in uart and transactions==14
 assert calculation_yields==set(range(32,768,32)),'No cooperative yield between temperature slices'
 if case=='delayed_bus':assert bus_wait_sht_reads>=24,'I2C wait starved SHT service'
 if case=='delayed_display':assert display_wait_sht_reads>=12,'Display wait starved SHT service'
 if case.startswith('recover_'):
  failure={'recover_nack':2,'recover_timeout':4,'recover_no_data':5}[case]
  statuses=[r[0] for r in commits]
  assert failure in statuses and statuses[-2:]==[0,1],statuses
  assert image_writes==768,'Recovery published invalid/half-calibrated frames'
 report.update(calculation_yield_points=len(calculation_yields),bus_wait_sht_reads=bus_wait_sht_reads,
               display_wait_sht_reads=display_wait_sht_reads)
report.update(passed=True,elapsed_s=round(time.time()-start,2),
 test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(out/('firmware_emulator_'+case+'.json')).write_text(json.dumps(report,indent=2))
print('PASS exact linked fusion firmware:',json.dumps(report))
