"""Run the production RV32 sensor scheduler against asynchronous MMIO models.

Checks calibration against independent synthetic inverse radiance, I2C failures,
bounded service calls, blank-time commits, retry and no-data recovery. No FPGA I/O.
"""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC

ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/multimodal_live'
FIX=ROOT/'fusion/tests/yolo_auto/fixtures/thermal'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sources=[Path(__file__).with_name('multimodal_sensor_software_test.cc'),SW/'sensor_src/multimodal_sensors.cc',SW/'sensor_src/MLX90640_API.cpp',SW/'sensor_src/thermal_compute.cc']
 elf=OUT/'multimodal_sensor_test.elf'
 command=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im_zicsr','-mabi=ilp32','-std=c++11','-O3',
  '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffunction-sections','-fdata-sections','-msmall-data-limit=0','-nostdlib',
  '-I'+str(SW/'sensor_src'),'-I'+str(SW/'src'),*map(str,sources),'-Wl,-Ttext=0x1000,-e,test_initialize,--gc-sections',
  '-Wl,--undefined=test_service','-Wl,--undefined=test_enable_low','-Wl,--undefined=test_reject_heat','-Wl,--undefined=test_metrics','-Wl,--undefined=test_alignment','-lm','-lc','-lgcc','-o',str(elf)]
 result=subprocess.run(command,capture_output=True,text=True)
 (OUT/'sensor_software_compile.log').write_text(result.stdout+result.stderr)
 assert result.returncode==0,result.stderr
 with elf.open('rb') as stream:
  e=ELFFile(stream);segments=[(s['p_vaddr'],s.data()) for s in e.iter_segments() if s['p_type']=='PT_LOAD']
  symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 base_ee=[int(x,16) for x in (FIX/'eeprom.hex').read_text().split()]
 base_frame=[int(x,16) for x in (FIX/'frame.hex').read_text().split()]
 golden=json.loads((FIX/'expected.json').read_text())['temperatures']
 report=dict(complete=False,passed=False,board_accessed=False,cases={},inputs_sha256={})
 files=[*sources,Path(__file__),*list((SW/'sensor_src').glob('*.h')),*list((SW/'sensor_src').glob('*.inc')),*list(FIX.glob('*'))]
 for p in files:report['inputs_sha256'][p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
 dest=OUT/'sensor_software_result.json'
 save=lambda:dest.write_text(json.dumps(report,indent=2),encoding='utf-8');save()
 success_cases=('normal','cold','hot','transient_nack','timer_wrap','slow_reader','slow_service',
  'status_bits','status_after_advance','runtime_bad_sample','runtime_nack','runtime_outage','slow_service_recovery','pipeline_display_wait','thermal_region_wake','thermal_rejected_object')
 for case in (*success_cases,'nack','bus_timeout','no_new_data','bad_eeprom','bad_math','stuck_display'):
  uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x1000000);uc.mem_map(0xf8100000,0x10000)
  for address,data in segments:uc.mem_write(address,data)
  def put(a,v):uc.mem_write(a,struct.pack('<I',v&0xffffffff))
  def get(a):return struct.unpack('<I',uc.mem_read(a,4))[0]
  def cstr(a):return bytes(uc.mem_read(a,200)).split(b'\0')[0].decode()
  state=dict(ms=0xfffffff0 if case=='timer_wrap' else 0,elapsed=0,transaction=None,bus_result=0,transactions=0,
   control=0x1981,fresh=False,page=0,captured_page=0,next_sensor=500,commit=None,ack=0,
   published=[],publish_times=[],errors=[],error_times=[],logs=[],colors={},service_calls=0,retries=0,period=500,rate_changes=[],
   ee_reads=0,injected=0,cleared_at=None,first_error_ms=None,prefetch_reads_during_ack=0)
  ee=base_ee.copy();frame=base_frame.copy();expected=golden
  if case=='bad_eeprom':ee[48]=0
  if case=='bad_math':frame[778]=0
  if case in ('cold','hot'):
   lo,hi=(-30,5) if case=='cold' else (80,250)
   alpha=108/2**30;emiss=.95;ta=25;tr=17;tatr=(tr+273.15)**4-((tr+273.15)**4-(ta+273.15)**4)/emiss
   expected=[]
   for i in range(768):
    target=lo+(hi-lo)*(i%32)/31
    raw=round(1000+emiss*alpha*((target+273.15)**4-tatr));frame[i]=raw&65535
    expected.append((((raw-1000)/emiss/alpha+tatr)**.25)-273.15)
  put(0xf8101000,0x46555331);put(0xf8101058,0x59415539)
  put(0xf8102000,1);put(0xf8102008,0x2500);put(0xf8102010,0x5000);put(0xf8102014,1)
  def complete_transaction():
   tx=state['transaction']
   if tx is None or state['elapsed']<tx['finish'] or case=='bus_timeout':return
   state['transaction']=None
   runtime_nack=case=='runtime_nack' and state['published'] and state['injected']<3 and tx['address']==0x0400
   if runtime_nack:state['injected']+=1
   rc=2 if case=='nack' or runtime_nack or (case=='transient_nack' and state['transactions']==1) else 1
   state['bus_result']=rc;put(0xf8103010,rc);put(0xf810301c,state['ms']);put(0xf8103018,state['transactions'])
   if rc!=1:return
   address=tx['address'];n=tx['n']
   if tx['read']:
    if address==0x2400:assert n==832;words=ee;state['ee_reads']+=1
    elif address==0x800d:assert n==1;words=[state['control']]
    elif address==0x8000:
     page=state['page']^(1 if case=='status_after_advance' and not state['fresh'] else 0)
     words=[(8 if state['fresh'] else 0)|page|(6 if case=='status_bits' else 0)]
    elif address==0x0400:
     assert n==832;words=frame[:832]
     if case=='status_after_advance':
      words=words.copy()
      for i in range(768):
       if (((i//32)&1)^(i&1))!=state['captured_page']:words[i]=0x7fff
     runtime_bad=case in ('runtime_bad_sample','slow_service_recovery') and len(state['published'])>=3 and state['injected']<2
     if runtime_bad:words=words.copy();words[778]=0;state['injected']+=1
     if case=='runtime_outage' and 1200<=state['elapsed']<5000:words=words.copy();words[778]=0;state['injected']+=1
    else:raise AssertionError(hex(address))
    for i,v in enumerate(words[:n]):put(0xf8104000+4*i,v)
   elif address==0x800d:
    state['control']=tx['value'];state['period']=2000/(2**((tx['value']>>7)&7))
    state['next_sensor']=state['elapsed']+state['period'];state['fresh']=False
    state['rate_changes'].append(1000/state['period'])
   elif address==0x8000:state['fresh']=False;state['captured_page']=state['page'];state['cleared_at']=state['elapsed']
   else:raise AssertionError(hex(address))
  def read_hook(_,__,addr,size,value,___):
   if addr==0xf8103ff0:put(addr,state['ms'])
   if addr==0xf8103014:put(addr,state['ms'])
   if addr in (0xf8103000,0xf8103010):
    complete_transaction();put(0xf8103000,1 if state['transaction'] else 0)
   if addr==0xf8101004:
    if state['commit'] is not None and state['elapsed']>=state['commit'] and case!='stuck_display':
     state['ack']^=1;state['commit']=None
    put(addr,4|(state['ack']<<1)|(1 if state['commit'] is not None else 0))
   if addr==0xf8101070:put(addr,4)
  def write_hook(_,__,addr,size,value,___):
   if addr==0xf8103fe0:state['logs'].append(cstr(value))
   if addr==0xf8103000:
    assert state['transaction'] is None,'sensor command issued while busy'
    state['transactions']+=1;n=get(0xf810300c)
    if get(0xf8103004)==0x0400 and value&2 and state['commit'] is not None:
     state['prefetch_reads_during_ack']+=1
    state['transaction']=dict(address=get(0xf8103004),n=n,value=get(0xf8103008),read=bool(value&2),finish=state['elapsed']+((100 if case=='slow_reader' else 38) if n==832 else 1))
   if 0xf8106000<=addr<0xf8106c00:
    assert state['commit'] is None,'heatmap overwritten before display ACK'
    assert 0<=value<=255;state['colors'][(addr-0xf8106000)//4]=value
   if addr==0xf8101018:
    assert state['commit'] is None,'display committed while busy'
    status=get(0xf8101020)
    if status&15==1:
     assert len(state['colors'])==768,'incomplete heatmap published'
     state['published'].append([get(0xf8101020+4*i) for i in range(4)]);state['publish_times'].append(state['elapsed'])
    else:state['errors'].append(status);state['error_times'].append(state['elapsed'])
    state['commit']=state['elapsed']+(80 if case=='pipeline_display_wait' else 16)
  uc.hook_add(UC_HOOK_MEM_READ,read_hook);uc.hook_add(UC_HOOK_MEM_WRITE,write_hook)
  def call(name):
   uc.reg_write(UC_RISCV_REG_SP,0xff0000);uc.reg_write(UC_RISCV_REG_RA,0)
   if '__global_pointer$' in symbols:uc.reg_write(UC_RISCV_REG_GP,symbols['__global_pointer$'])
   uc.emu_start(symbols[name],0,count=30000000)
   assert uc.reg_read(UC_RISCV_REG_PC)==0,'service call blocked or exceeded bounded instruction budget'
  call('test_initialize');call('test_metrics')
  rejected=False
  if case in ('thermal_region_wake','thermal_rejected_object'):call('test_enable_low')
  assert get(0xf8101080)==0x50 and get(0xf8101084)==0x175 and get(0xf8101088)==0x95,'metrics are not BCD'
  tick=20 if case in ('slow_service','slow_service_recovery') else 1
  for step in range(8000//tick):
   state['elapsed']+=tick;state['ms']=(state['ms']+tick)&0xffffffff
   while state['elapsed']>=state['next_sensor']:
    state['next_sensor']+=state['period'];state['page']^=1
    if case!='no_new_data':state['fresh']=True
   call('test_service');state['service_calls']+=1
   if case=='thermal_rejected_object' and not rejected and state['elapsed']>=1300 and get(symbols['test_wake_count'])>0:
    call('test_reject_heat');rejected=True
   if len(state['published'])>=6 and state['elapsed']>=(6500 if case=='runtime_outage' else 3000 if case.startswith('runtime_') or case=='slow_service_recovery' else 2200):break
   if case in ('nack','bus_timeout','no_new_data','bad_eeprom','bad_math','stuck_display') and any(x not in (0,8) for x in state['errors']):break
  if case in success_cases:
   assert len(state['published'])>=3,(case,state)
   if case!='runtime_outage':assert not [x for x in state['errors'] if x not in (0,8)],(case,state['errors'])
   def bcd(n):
    v=0
    for i in range(4,-1,-1):v=v*10+((n>>(i*4))&15)
    return -v if n&0x80000000 else v
   rec=state['published'][-1]
   error=max(abs(bcd(rec[1])/100-min(expected)),abs(bcd(rec[2])/100-max(expected)),abs(bcd(rec[3])/100-expected[12*32+16]))
   assert error<.03,(case,rec,error)
   assert any(x.startswith('MM_IR_INIT') for x in state['logs'])
   assert state['rate_changes'][0]==16,'16-Hz subpage configuration missing'
   if case=='slow_reader':
    assert any(x.startswith('MM_IR_RATE_FALLBACK') for x in state['logs'])
    assert min(state['rate_changes'])<=8,'overrun did not reduce sensor rate'
   if case in ('normal','cold','hot','timer_wrap'):
    assert len(state['published'])>=16,'high-rate scheduler regression'
    assert (rec[0]>>8)&0xfff,'actual update rate never published'
   if case in ('runtime_bad_sample','runtime_nack','runtime_outage','slow_service_recovery'):
    assert state['injected']>=2,(case,'fault not injected')
    assert state['ee_reads']==2,(case,'transient runtime failure re-read EEPROM')
    assert any(x.startswith('MM_IR_ERROR') for x in state['logs']),(case,'recovery not exercised')
    if case!='runtime_outage':
     assert max(b-a for a,b in zip(state['publish_times'],state['publish_times'][1:]))<2000,(case,'unnecessary long blackout')
   if case=='runtime_outage':
    assert 5 in state['errors'],'sustained missing data remained falsely live'
    assert state['publish_times'][-1]>5000,'did not recover after persistent invalid samples'
    assert min(t for t,s in zip(state['error_times'],state['errors']) if s==5)-max(t for t in state['publish_times'] if t<1200)>=3000
   if case=='slow_service_recovery':
    rates=state['rate_changes'];assert min(rates)<16,'slow service never adapted'
    assert all(b<=a for a,b in zip(rates,rates[1:])),'runtime recovery reset safe rate upward'
   if case=='pipeline_display_wait':
    assert state['prefetch_reads_during_ack']>=3,'next sample acquisition did not overlap display ACK wait'
   if case=='thermal_region_wake':
    assert get(symbols['test_wake_count'])>0,'calibrated sensor samples never reached wake gate'
    assert get(symbols['test_thermal_healthy'])==1,'live thermal monitor incorrectly unhealthy'
    assert any(x.startswith('MM_IR_WAKE') for x in state['logs']),'thermal candidate not reported'
   if case=='thermal_rejected_object':
    assert rejected,'warm source never reached visual rejection'
    assert get(symbols['test_wake_count'])==0,'stationary visually rejected heat woke the system again'
    assert any(x.startswith('MM_IR_REJECT') for x in state['logs']),'visual rejection was not applied'

  else:
   expected_error={'nack':2,'bus_timeout':4,'no_new_data':5,'bad_eeprom':6,'bad_math':7,'stuck_display':9}[case]
   # A display stuck busy cannot acknowledge the error record; the driver must
   # still return promptly and report the failure through the diagnostic log.
   assert expected_error in state['errors'] or (case=='stuck_display' and any(x.startswith('MM_IR_ERROR') for x in state['logs'])),(case,state)
   assert not state['published'],(case,'invalid heatmap published')
   error=None
  if case=='transient_nack':assert any(x.startswith('MM_IR_RETRY') for x in state['logs'])
  if case=='normal':
   # Match a real video time against the actual asynchronous driver history,
   # not only the isolated History unit test. SHT hardware sample has its own stamp.
   video=(state['ms']-100)&0xffffffff;put(0xf8103ff4,video)
   put(0xf810200c,(video-20)&0xffffffff);put(0xf8102014,2)
   state['ms']=(state['ms']+501)&0xffffffff;state['elapsed']+=501;call('test_service');call('test_alignment')
   aligned=struct.unpack('<10i',uc.mem_read(symbols['test_aligned'],40))
   assert aligned[0:2]==(1,1) and abs(aligned[2])<=350 and abs(aligned[3])<=350 and aligned[4]==-20,aligned
   assert aligned[8:10]==(123,2500) and abs(aligned[5]/100-min(expected))<.03 and abs(aligned[6]/100-max(expected))<.03,aligned
   assert any(x.startswith('MM_ALIGN') for x in state['logs'])
  report['cases'][case]=dict(passed=True,service_calls=state['service_calls'],transactions=state['transactions'],heatmaps=len(state['published']),max_temperature_error_c=error,configured_subpage_hz=state['rate_changes'],simulated_elapsed_ms=state['elapsed'],eeprom_reads=state['ee_reads'],runtime_faults_injected=state['injected'],prefetch_reads_during_ack=state['prefetch_reads_during_ack'],max_publish_gap_ms=max((b-a for a,b in zip(state['publish_times'],state['publish_times'][1:])),default=0),published_rate_bcd=(state['published'][-1][0]>>8)&0xfff if state['published'] else None)
  save();print('PASS sensor RV32',case,flush=True)
 report.update(complete=True,passed=True);save();print(dest)

if __name__=='__main__':main()
