"""Compare production RV32 LUT/cached compensation to unchanged vendor equations.

Instruction counts are emulated RV32IM instructions, NOT board milliseconds/FPS.
"""
from pathlib import Path
import hashlib,json,math,random,struct,subprocess,sys
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_BLOCK
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
T=Path(__file__).resolve().parent;OUT=ROOT/'fusion/ti60_yolo_auto/validation/thermal_fast'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sources=[T/'thermal_compute_test.cc',SW/'sensor_src/thermal_compute.cc',SW/'sensor_src/MLX90640_API.cpp']
 elf=OUT/'thermal_compute_test.elf';exports=['test_extract','test_scenario','test_calibrate','test_reference','test_fast','test_roots','test_rate']
 command=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im_zicsr','-mabi=ilp32','-std=c++11','-O3',
  '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffunction-sections','-fdata-sections','-msmall-data-limit=0','-nostdlib',
  '-I'+str(SW/'sensor_src'),*map(str,sources),'-Wl,-Ttext=0x1000,-e,test_extract,--gc-sections',
  *['-Wl,--undefined='+e for e in exports],'-lm','-lc','-lgcc','-o',str(elf)]
 p=subprocess.run(command,capture_output=True,text=True);(OUT/'compile.log').write_text(p.stdout+p.stderr);assert not p.returncode,p.stderr
 uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x1000000)
 with elf.open('rb') as f:
  e=ELFFile(f)
  for seg in e.iter_segments():
   if seg['p_type']=='PT_LOAD':uc.mem_write(seg['p_vaddr'],seg.data())
  sym={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 def write(name,values,fmt):uc.mem_write(sym[name],struct.pack('<'+str(len(values))+fmt,*values))
 def read(name,n=1,fmt='I'):return struct.unpack('<'+str(n)+fmt,uc.mem_read(sym[name],struct.calcsize(fmt)*n))
 instructions=[0]
 def count(_,address,size,data):instructions[0]+=size//4
 def call(name,measure=False):
  uc.reg_write(UC_RISCV_REG_SP,0xff0000);uc.reg_write(UC_RISCV_REG_RA,0)
  if '__global_pointer$' in sym:uc.reg_write(UC_RISCV_REG_GP,sym['__global_pointer$'])
  instructions[0]=0;hook=uc.hook_add(UC_HOOK_BLOCK,count) if measure else None
  uc.emu_start(sym[name],0,count=100000000)
  if hook is not None:uc.hook_del(hook)
  assert uc.reg_read(UC_RISCV_REG_PC)==0,name+' exceeded instruction budget'
  return instructions[0]
 fix=T/'fixtures/thermal';ee=[int(x,16) for x in (fix/'eeprom.hex').read_text().split()]
 frame=[int(x,16) for x in (fix/'frame.hex').read_text().split()]+[0x1981,0]
 write('ee',ee,'H');write('frame',frame,'H');call('test_extract');assert read('math_status')[0]==0
 call('test_rate');assert read('math_status')[0]==0,'rate/pair/duplicate/timer-wrap test'
 # Exponent and mantissa sweep covers the full positive-normal float32 domain;
 # include subnormals, exact powers and the smallest/largest normal values.
 rng=random.Random(40640);roots=[2.0**e for e in range(-149,128)]
 roots += [struct.unpack('<f',struct.pack('<I',rng.randrange(1,0x7f800000)))[0] for _ in range(3600)]
 roots += [0.0,1.0,2.0,16.0,81.0]
 write('root_count',[len(roots)],'I');write('root_in',roots,'f');call('test_roots')
 errors=[abs(q-x**.25)/(x**.25) if x else abs(q) for x,q in zip(roots,read('root_out',len(roots),'f'))]
 assert max(errors)<6e-7,max(errors)
 report=dict(complete=False,passed=False,board_accessed=False,algorithm='thermal_fast_v1',root_cases=len(roots),
  root_max_relative_error=max(errors),rate_pair_duplicate_wrap_passed=True,cases=[],inputs_sha256={})
 max_error=0;ref_count=fast_count=0
 for k in range(96):
  write('frame',frame,'H');call('test_extract');write('scenario',[k],'I');call('test_scenario')
  # Sweep sensor raw radiance; most samples are within [-40,300] C. The driver
  # separately rejects values outside its validated measurement range.
  samples=[(1000+round(7000*((i%32)/31)**2)-150 if k&16 else 1000+round(2000*(i%32)/31))&65535 for i in range(768)]
  uc.mem_write(sym['frame'],struct.pack('<768H',*samples));call('test_calibrate')
  rc=call('test_reference',k==0);fc=call('test_fast',k==0);assert read('math_status')[0]==0
  if k==0:ref_count,fast_count=rc,fc
  reference=read('reference_out',768,'f');fast=read('fast_out',768,'f');active=[]
  for i,(a,b) in enumerate(zip(reference,fast)):
   pattern=((i//32)&1)^((i&1) if k&1 else 0)
   if pattern!=((k>>2)&1):continue
   assert math.isfinite(a) and math.isfinite(b),(k,i,a,b)
   active.append(abs(a-b))
  err=max(active);max_error=max(err,max_error);assert err<.02,(k,err)
  report['cases'].append(dict(scenario=k,pixels=len(active),max_error_c=err))
  if k%8==7:print('PASS thermal compensation scenarios',k+1,flush=True)
 assert fast_count<ref_count*.5,(ref_count,fast_count)
 inputs=[Path(__file__),*sources,SW/'sensor_src/thermal_compute.h',SW/'sensor_src/thermal_root_lut.inc',SW/'sensor_src/thermal_range.h',SW/'sensor_src/thermal_rate.h',SW/'sensor_src/MLX90640_API.h',*fix.glob('*')]
 report['inputs_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
 report.update(complete=True,passed=True,max_compensation_error_c=max_error,rv32_reference_instructions=ref_count,
  rv32_fast_instructions=fast_count,rv32_instruction_reduction_ratio=ref_count/fast_count,
  instruction_scope='one 384-pixel subpage; old 24x32-index batches vs new 4x192-index batches; EEPROM caching excluded; not cycles or FPS')
 dest=OUT/'compute_result.json';dest.write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k not in ('cases','inputs_sha256')},indent=2));print(dest)
if __name__=='__main__':main()
