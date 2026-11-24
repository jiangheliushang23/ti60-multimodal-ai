"""Production RV32 per-ID fall with future prediction removed; no hardware access."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
import numpy as np
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/no_prediction/dual_fall'

def main():
 OUT.mkdir(parents=True,exist_ok=True);test=Path(__file__).with_name('no_prediction_rv32_test.cc');elf=OUT/'dual_behavior.elf'
 cmd=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O3','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-msmall-data-limit=0','-nostdlib','-I'+str(SW/'replay_src'),str(test),'-Wl,-Ttext=0x1000,-e,dual_reset','-lc','-lgcc','-o',str(elf)]
 c=subprocess.run(cmd,capture_output=True,text=True);(OUT/'compile.log').write_text(c.stdout+c.stderr);assert c.returncode==0,c.stderr
 with elf.open('rb') as f:
  e=ELFFile(f);segments=[(s['p_vaddr'],s.data()) for s in e.iter_segments() if s['p_type']=='PT_LOAD'];symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 report=dict(complete=False,passed=False,board_accessed=False,cases={})
 save=lambda:(OUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 save()
 class Run:
  def __init__(self):
   self.uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);self.uc.mem_map(0,0x1000000)
   for a,b in segments:self.uc.mem_write(a,b)
   self.rows=[];self.call('dual_reset')
  def call(self,name):
   self.uc.reg_write(UC_RISCV_REG_SP,0xf00000);self.uc.reg_write(UC_RISCV_REG_RA,0);self.uc.reg_write(UC_RISCV_REG_GP,symbols.get('__global_pointer$',0));self.uc.emu_start(symbols[name],0,count=30000000);assert self.uc.reg_read(UC_RISCV_REG_PC)==0
  def step(self,ms,a=None,b=None,pixels=False,fresh=True,age=0,image=None,score=25000):
   def box(x,p=False):return [int(x is not None),*(x or (0,0,0,0)),0 if p else score]
   self.uc.mem_write(symbols['dual_image_enabled'],struct.pack('<I',int(image is not None)))
   if image is not None:self.uc.mem_write(symbols['dual_image'],image.astype('<u2').tobytes())
   values=[ms&0xffffffff,(ms+age)&0xffffffff,*box(a,pixels),*box(b),int(fresh),int(pixels)]
   self.uc.mem_write(symbols['dual_args'],struct.pack('<16I',*values));self.call('dual_step');o=struct.unpack('<64I',self.uc.mem_read(symbols['dual_out'],256));assert o[3],'production per-ID fall differs from original Detector'
   people=[]
   for i in range(2):
    p=o[4+i*20:4+(i+1)*20];people.append(dict(zip(('id','valid','state','alarm','event','armed','warning','prediction_valid','inside','current_x','predicted_x','predicted_y','flags','events','pixels','rescued'),p)))
   row=dict(ms=ms,visible=o[0],active=o[1],any_alarm=o[2],people=people);self.rows.append(row);return row
  def finish(self,name):report['cases'][name]=dict(passed=True,rows=self.rows);save();print('PASS RV32 dual behavior',name,flush=True)
 stand=(210,150,370,650);lie=(120,450,520,650);stand2=(900,150,1060,650);lie2=(810,450,1210,650)
 for which in (0,1,2):
  r=Run()
  for ms in (0,280,560,840):o=r.step(ms,stand,stand2)
  ids=[p['id'] for p in o['people']];assert all(p['armed'] for p in o['people'])
  for ms in (1120,1400):
   aa=lie if which in (0,2) else stand;bb=lie2 if which in (1,2) else stand2
   # Alternate confidence order: state must follow identity, never output slot.
   o=r.step(ms,bb,aa)
   assert [p['id'] for p in o['people']]==ids[::-1]
  by={p['id']:p for p in o['people']}
  assert bool(by[ids[0]]['alarm'])==(which in (0,2));assert bool(by[ids[1]]['alarm'])==(which in (1,2))
  for p in o['people']:
   assert p['flags']&15==(7 if p['alarm'] else 3)
  r.finish(('first_falls_second_normal','second_falls_first_normal','both_fall_independently')[which])
 r=Run()
 for ms in (0,280,560,840):o=r.step(ms,stand)
 identity=o['people'][0]['id']
 for ms in range(1120,10000,280):o=r.step(ms,lie,pixels=True);assert o['people'][0]['id']==identity
 assert o['people'][0]['alarm'];assert o['people'][0]['flags']&15==7
 r.finish('single_person_pixel_supported_fall_matches_original_all_fields')
 r=Run()
 for ms in (0,280,560,840):r.step(ms,stand,stand2)
 for ms in (1120,1400):o=r.step(ms,lie,stand2)
 old=o['people'][0]['id'];assert o['people'][0]['alarm']
 o=r.step(2800,stand,stand2);assert o['people'][0]['id']!=old and not o['people'][0]['alarm'];r.finish('new_identity_does_not_inherit_alarm')
 r=Run();r.step(0,stand,stand2);o=r.step(200,stand,stand);assert o['visible']==1
 o=r.step(400,stand,stand2,fresh=False);assert o['visible']==0 and not any(p['valid'] for p in o['people']);r.finish('duplicate_and_stale_inputs_not_displayed')
 # Both identities must be continued by current pixels, including a missed
 # SECOND person. Test the actual production Manager and all fall fields.
 r=Run()
 def picture(a=None,b=None):
  im=np.full((72,128),(90>>3)<<11|(100>>2)<<5|(110>>3),dtype=np.uint16)
  for rect,color in ((a,(35,90,180)),(b,(190,60,50))):
   if rect is not None:
    x1,y1,x2,y2=rect;rr,gg,bb=color
    im[y1//10:(y2+9)//10,x1//10:(x2+9)//10]=(rr>>3)<<11|(gg>>2)<<5|(bb>>3)
  return im
 for ms in range(0,2400,200):r.step(ms,image=picture())
 for ms in range(2400,3600,200):o=r.step(ms,stand,stand2,image=picture(stand,stand2))
 ids=[p['id'] for p in o['people']]
 for k,(aa,bb) in enumerate(((stand,stand2),((200,250,430,650),(890,250,1110,650)),((160,350,480,650),(850,350,1160,650)),(lie,lie2))):
  o=r.step(3600+k*200,image=picture(aa,bb))
  assert o['visible']==2,(k,o)
  assert {p['id'] for p in o['people']}==set(ids)
  assert all(p['pixels'] and p['rescued'] for p in o['people'])
 for ms in range(4400,6400,200):
  o=r.step(ms,image=picture(lie,lie2));assert o['visible']==2 and all(p['alarm'] for p in o['people']),o
 o=r.step(6600,image=picture());assert o['visible']==0
 r.finish('both_lying_current_pixel_rescue_independent_alarms_and_empty_clear')
 # Replay original single-person fall traces through the new ownership layer.
 # The manually reset case has a separate explicit reset not encoded in rows.
 old=json.loads((OUT.parents[1]/'fall_detection/fall_result.json').read_text())
 compatible=[]
 for name,case in old['cases'].items():
  if name in ('manual_reset','sampled_frame_difference_and_centroid'):continue
  r=Run()
  for row in case['rows']:
   v=row['input'];box=tuple(v[2:6]) if v[1] else None
   o=r.step(v[0],box,pixels=bool(v[7]),score=v[6])
   assert bool(o['any_alarm'])==bool(row['alarm']),(name,row,o)
  compatible.append(name)
 report['single_person_trace_regressions']=compatible
 # Safe, right-quarter and fast rightward motion all remain green unless
 # the unchanged per-ID fall classifier asserts alarm.
 r=Run()
 for ms,x in ((0,800),(200,900),(400,980),(600,1100),(800,1080),(1000,950)):
  o=r.step(ms,(x-60,100,x+60,650),age=200)
  assert o['visible']==1
  assert o['people'][0]['flags']&15==3
  assert not any(p['warning'] or p['prediction_valid'] for p in o['people'])
 r.finish('right_quarter_and_rightward_motion_never_yellow')
 r=Run();colors=[]
 for valid in (0,1):
  for identity in (0,1,9,10,99,100,1234,9999):
   for alarm in (0,1):
    r.uc.mem_write(symbols['risk_args'],struct.pack('<13I',valid,identity,alarm,*([0]*10)));r.call('risk_step')
    f,bcd=struct.unpack('<2I',r.uc.mem_read(symbols['risk_out'],8))
    assert f&15==((7 if alarm else 3) if valid else 0)
    assert (f>>5)==(bcd if valid else 0)
    assert not (f&8)
    colors.append(dict(valid=valid,id=identity,alarm=alarm,flags=f))
 report['cases']['normal_green_fall_red_ids_preserved']=dict(passed=True,rows=colors)
 baseline=json.loads((OUT.parents[1]/'dual_behavior/baseline.json').read_text(encoding='utf8'))
 for name in ('fall_detection.h','person_roi.h','person_pair.h'):
  p=SW/'replay_src'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==baseline['sha256'][p.relative_to(ROOT).as_posix()],name
 report.update(complete=True,passed=True,independent_per_id_fall=True,original_fall_detector_unchanged=True,prediction_enabled=False,yellow_warning_enabled=False,colors=['green','red'],limitations='Synthetic production RV32 execution, not board FPS or real-camera identity accuracy.')
 paths=[Path(__file__),test,*[SW/'replay_src'/n for n in ('two_person_tracker.h','two_person_analysis.h','person_visual_track.h','fall_detection.h','main.cc')],OUT.parents[1]/'dual_behavior/baseline.json',OUT.parents[1]/'fall_detection/fall_result.json']
 report['inputs_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};save();print(OUT/'result.json')
if __name__=='__main__':main()
