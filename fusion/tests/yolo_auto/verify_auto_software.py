"""Execute the production AE/AWB headers as RV32; compare with frozen RTL."""
from pathlib import Path
import hashlib,json,random,struct,subprocess,sys
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_CODE
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_A0,UC_RISCV_REG_A1,UC_RISCV_REG_A3,UC_RISCV_REG_PC,UC_RISCV_REG_GP
ROOT=Path(__file__).resolve().parents[3];A=ROOT/'fusion/tests/camera_auto'
S=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static/sensor_src'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/auto_software';SIM=Path('D:/modelsim/modelsim_ase/win32aloem')
def run(command,label):
 r=subprocess.run(list(map(str,command)),cwd=OUT,capture_output=True,text=True,timeout=240)
 text=r.stdout+r.stderr;(OUT/(label+'.log')).write_text(text,encoding='utf-8')
 assert r.returncode==0 and '** Error:' not in text and '** Fatal:' not in text,text[-3000:]
 return text
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 wrapper=OUT/'auto_test.cc'
 scheduler=OUT/'scheduler.cc'
 original=(A/'control_host.cc').read_text();before,last=original.rsplit('}',1)
 scheduler.write_text(before+'return 0;\n}'+last)
 wrapper.write_text('#define main camera_scheduler_test\n#include "'+scheduler.as_posix()+'"\n#undef main\nextern "C" int test_scheduler(){return camera_scheduler_test(1,nullptr);}\n'
 'extern "C" void test_decide(unsigned *v,unsigned *o){CameraStats s={1,v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],v[8],v[9]};'
 'CameraDecision d=camera_decide(s,v[10],v[11],v[12],v[13]);o[0]=d.exposure;o[1]=d.gain_index;o[2]=d.gain_r;o[3]=d.gain_b;o[4]=d.sensor_update;}\n')
 elf=OUT/'auto_test.elf'
 run(['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im_zicsr','-mabi=ilp32','-std=c++11','-O2','-fno-exceptions','-fno-rtti',
 '-fno-threadsafe-statics','-msmall-data-limit=0','-nostartfiles','-specs=nosys.specs','-I'+str(S),wrapper,'-Wl,-Ttext=0x1000,-e,test_scheduler','-lm','-lc','-lgcc','-o',elf],'compile')
 with elf.open('rb') as stream:
  e=ELFFile(stream);segments=[(p['p_vaddr'],p.data()) for p in e.iter_segments() if p['p_type']=='PT_LOAD']
  symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x1000000)
 for address,data in segments:uc.mem_write(address,data)
 def hook(uc,address,size,_):
  if address==symbols.get('__assert_func'):
   expression=bytes(uc.mem_read(uc.reg_read(UC_RISCV_REG_A3),200)).split(b'\0')[0].decode()
   raise AssertionError('Production CameraAuto scheduler: '+expression+' line='+str(uc.reg_read(UC_RISCV_REG_A1)))
  if address==symbols.get('puts'):uc.reg_write(UC_RISCV_REG_PC,uc.reg_read(UC_RISCV_REG_RA))
 uc.hook_add(UC_HOOK_CODE,hook)
 def call(name,a0=0,a1=0):
  uc.reg_write(UC_RISCV_REG_SP,0xf00000);uc.reg_write(UC_RISCV_REG_RA,0xe00000)
  uc.reg_write(UC_RISCV_REG_GP,symbols.get('__global_pointer$',0));uc.reg_write(UC_RISCV_REG_A0,a0);uc.reg_write(UC_RISCV_REG_A1,a1)
  uc.emu_start(symbols[name],0xe00000,count=2000000)
  assert uc.reg_read(UC_RISCV_REG_PC)==0xe00000,'RV32 instruction budget exceeded'
 call('test_scheduler');print('PASS RV32 AE/AWB scheduling, I2C ACK/NACK/readback/timeout, frame-safe gains',flush=True)
 cases=[];rng=random.Random(431)
 def add(mean,clip,rmean,gmean,bmean,exp,gain,r=256,b=256,counts=(8160,16320,8160)):
  rc,gc,bc=counts;cases.append([mean*16320,16320,clip,32640,rmean*rc,rc,gmean*gc,gc,bmean*bc,bc,exp,gain,r,b])
 for mean in (0,23,24,47,48,60,64,65,239):
  for clip in (0,255,256,257,510,511,512):
   for exp,gain in ((2989,82),(2989,0),(4,0),(100,18),(2980,81)):add(mean,clip,30,60,90,exp,gain)
 for _ in range(300):add(rng.randrange(240),rng.randrange(32641),rng.randrange(232),rng.randrange(232),rng.randrange(232),rng.randrange(4,2990),rng.randrange(83),rng.randrange(128,513),rng.randrange(128,513),tuple(rng.choice((0,1,63,64,8160)) for _ in range(3)))
 vectors=OUT/'vectors.txt';vectors.write_text('\n'.join(' '.join(map(str,v)) for v in cases)+'\n')
 ref=OUT/'reference.txt'
 files=[A/'control_reference_tb.v',A/'reference/rtl/sc431hai/sc_auto_control.v',A/'reference/rtl/sc431hai/sc_auto_stats.v']
 if not (OUT/'work').exists():run([SIM/'vlib.exe','work'],'vlib')
 run([SIM/'vlog.exe','-sv',*files],'reference_compile')
 text=run([SIM/'vsim.exe','-c','-quiet','work.control_reference_tb','+INPUT='+vectors.as_posix(),'+OUTPUT='+ref.as_posix(),'-do','run -all; quit -f'],'reference_sim')
 expected=ref.read_text().splitlines();assert len(expected)==len(cases)
 for i,(v,line) in enumerate(zip(cases,expected)):
  uc.mem_write(0x900000,struct.pack('<14I',*v));call('test_decide',0x900000,0x900100)
  actual=struct.unpack('<5I',uc.mem_read(0x900100,20));assert actual==tuple(map(int,line.split())),(i,v,actual,line)
 inputs=[Path(__file__),wrapper,A/'control_host.cc',S/'camera_auto.h',S/'camera_control.h',S/'camera_auto_service.h',*files]
 report=dict(complete=True,passed=True,board_accessed=False,scheduler_passed=True,reference_cases=len(cases),
  inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
 (OUT/'software_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('PASS AE/AWB production RV32 matches frozen RTL:',len(cases),'cases',flush=True)
if __name__=='__main__':main()
