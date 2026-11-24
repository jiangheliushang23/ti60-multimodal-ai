"""Exercise production RV32 IOU association and unchanged fall inputs. No USB."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_CODE
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/two_track'
HEADER=SW/'replay_src/two_person_tracker.h'
TEST=Path(__file__).with_name('two_person_tracker_rv32_test.cc')

def main():
 OUT.mkdir(parents=True,exist_ok=True);elf=OUT/'two_person_tracker.elf'
 cmd=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O3',
  '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-msmall-data-limit=0','-nostdlib',
  '-I'+str(HEADER.parent),str(TEST),'-Wl,-Ttext=0x1000,-e,tracking_reset','-lc','-lgcc','-o',str(elf)]
 r=subprocess.run(cmd,capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr)
 assert not r.returncode,r.stdout+r.stderr
 with elf.open('rb') as f:
  e=ELFFile(f);segments=[(s['p_vaddr'],s.data()) for s in e.iter_segments() if s['p_type']=='PT_LOAD']
  symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 report=dict(complete=False,passed=False,board_accessed=False,algorithm='iou_motion_v1',cases={},max_test_step_rv32_instructions=0)
 save=lambda:(OUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 save()
 class Run:
  def __init__(self,offset=0):
   self.uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);self.uc.mem_map(0,0x800000)
   for a,b in segments:self.uc.mem_write(a,b)
   self.instructions=0;self.uc.hook_add(UC_HOOK_CODE,self.count);self.offset=offset;self.rows=[];self.call('tracking_reset')
  def count(self,*_):self.instructions+=1
  def call(self,name):
   self.instructions=0;self.uc.reg_write(UC_RISCV_REG_SP,0x7f0000);self.uc.reg_write(UC_RISCV_REG_RA,0)
   self.uc.reg_write(UC_RISCV_REG_GP,symbols.get('__global_pointer$',0))
   self.uc.emu_start(symbols[name],0,count=1000000);assert self.uc.reg_read(UC_RISCV_REG_PC)==0
  def step(self,ms,a=None,b=None,fresh=True,pixels=False):
   def args(v):return [int(v is not None),*(v or (0,0,0,0)),0 if pixels else 25000]
   values=[(ms+self.offset)&0xffffffff,*args(a),*args(b),int(fresh),int(pixels)]
   self.uc.mem_write(symbols['tracking_args'],struct.pack('<15I',*values));self.call('tracking_step')
   o=list(struct.unpack('<32I',self.uc.mem_read(symbols['tracking_output'],128)))
   unchanged,equal,alarm=struct.unpack('<3I',self.uc.mem_read(symbols['fall_comparison'],12))
   assert unchanged and equal,'Tracker mutated detection or changed fall outputs'
   report['max_test_step_rv32_instructions']=max(report['max_test_step_rv32_instructions'],self.instructions)
   row=dict(ms=ms,a=a,b=b,ids=o[:2],active=o[2],visible=o[3],tracks=[o[4:18],o[18:32]],fall_alarm=alarm)
   self.rows.append(row);return row
  def finish(self,name):report['cases'][name]=dict(passed=True,rows=self.rows);save();print('PASS RV32 tracking',name,flush=True)
 def box(x,y=120,w=140,h=480):return (x,y,x+w,y+h)
 left,right=box(100),box(900)
 r=Run();assert r.step(0)['visible']==0
 one=r.step(200,left);one_id=one['ids'][0];assert one_id
 two=r.step(400,left,right);two_id=two['ids'][1];assert two['visible']==2 and two_id!=one_id
 for t in range(600,3000,200):
  o=r.step(t,right,left);assert o['ids']==[two_id,one_id]
 r.finish('one_then_two_score_order_reversal')
 r=Run();a=r.step(0,left,right)['ids']
 o=r.step(200,left);assert o['visible']==1 and o['active']==2 and o['ids']==[a[0],0]
 o=r.step(800,left,right);assert o['ids']==a
 o=r.step(2200,left,right);assert o['ids'][1]!=a[1]
 r.finish('brief_occlusion_keeps_id_but_never_draws_predicted_person')
 r=Run();initial=r.step(0,left)['ids'][0]
 o=r.step(1300,left);assert o['ids'][0]!=initial
 r.uc.mem_write(symbols['tracking_reset_mode'],struct.pack('<I',0));r.call('tracking_reset')
 assert r.step(1500,left)['ids'][0]>o['ids'][0]
 r.finish('expired_or_reset_identity_never_reused')
 r=Run();ids=r.step(0,box(200),box(850))['ids']
 for i in range(1,10):
  a,b=box(200+i*65),box(850-i*65,y=400,h=300)
  # Scores alternate primary/secondary order. People pass with distinct y.
  o=r.step(i*200,b,a) if i%2 else r.step(i*200,a,b)
  assert o['ids']==(ids[::-1] if i%2 else ids),(i,o,ids)
 r.finish('two_moving_people_cross_and_change_detector_order')
 r=Run();ids=r.step(0,left,right)['ids']
 assert r.step(200,left,left)['visible']==1
 assert r.step(400,left,right)['ids']==ids
 assert r.step(600,(0,0,2000,900))['visible']==0
 assert r.step(800,left,right,fresh=False)['visible']==0
 assert r.step(1000,left,right)['ids']==ids
 r.finish('duplicate_invalid_and_stale_observations_do_not_create_people')
 r=Run();identity=r.step(0,left)['ids'][0]
 assert r.step(200,right)['ids'][0]!=identity
 r.finish('distant_new_person_does_not_inherit_departed_identity')
 r=Run();stand=(520,150,680,650);lying=(430,450,830,650)
 for t in (0,280,560,840):o=r.step(t,stand,right)
 identity=o['ids'][0]
 for t in (1120,1400):o=r.step(t,lying,right,pixels=True);assert o['ids'][0]==identity
 assert o['fall_alarm']
 for t in range(1680,65000,280):
  o=r.step(t,lying,right,pixels=True);assert o['ids'][0]==identity and o['fall_alarm']
 assert all(x[6]==32 for x in o['tracks'])
 r.finish('fall_and_motionless_pixel_supported_lying_preserve_id_and_alarm')
 r=Run(offset=0xffffff00);ids=r.step(0,left,right)['ids']
 assert r.step(200,left,right)['ids']==ids
 assert r.step(400,left,right)['ids']==ids
 r.finish('millisecond_wrap')
 r=Run();ids=r.step(100,left,right)['ids']
 assert not r.step(100,left,right)['visible'];assert not r.step(50,left,right)['visible']
 o=r.step(300,left,right);assert o['ids']==ids and all(x[4]==2 for x in o['tracks'])
 r.finish('duplicate_and_out_of_order_time_does_not_extend_history')
 # v16 intentionally extends HDMI metadata and per-ID fall ownership.
 baseline=json.loads((OUT.parent/'dual_behavior/baseline.json').read_text(encoding='utf8'))
 before=Path(baseline['backup'])/'before'
 protected=['person_roi.h','person_pair.h','fall_detection.h']
 for name in protected:
  p=SW/'replay_src'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==baseline['sha256'][p.relative_to(ROOT).as_posix()],name
 import re
 p=SW/'replay_src/person_visual_track.h'
 strip=lambda s:re.sub(r'  // Keep learned background.*?  Result update', '  Result update',s,flags=re.S)
 assert strip(p.read_text())==(before/p.relative_to(ROOT)).read_text(), 'Pixel core changed beyond identity-reset addition'
 report['original_fall_detector_unchanged']=True;report['pixel_tracker_core_unchanged']=True
 report['hardware_bit_changed']=True;report['per_id_state_owner']='two_person_analysis::Manager'
 paths=[Path(__file__),TEST,HEADER,SW/'replay_src/main.cc',*[SW/'replay_src'/n for n in protected],OUT.parent/'dual_behavior/baseline.json']
 report['inputs_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 report.update(complete=True,passed=True,limitation='Synthetic RV32 association tests; not hardware FPS or identity accuracy under full occlusion.')
 save();print(OUT/'result.json')
if __name__=='__main__':main()
