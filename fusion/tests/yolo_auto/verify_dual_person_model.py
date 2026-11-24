"""Actual INT8 model -> production RV32 decoder/pair on a real two-person image.

No USB access. PC inference and RV32 emulation do not measure board throughput.
"""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
import cv2,numpy as np
from ai_edge_litert.interpreter import Interpreter,OpResolverType
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/dual_person'
sys.path.insert(0,str(ROOT/'delivery'))
from yolo_fixed_reference import decode_fixed_reference
sys.path.insert(0,str(SW))
from yolo_auto_download import people_output_valid
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 source=OUT/'zidane_source.jpg'
 assert hashlib.sha256(source.read_bytes()).hexdigest()=='356dad2107bb0254e4e4a81bc1d9c7140043e88569d546e5b404b19bffa77d0a'
 production=SW/'replay_src/main.cc';test=Path(__file__).with_name('dual_person_model_test.cc')
 text=production.read_text();decoder=text.split('using Box=person_roi::Box;',1)[1].split('bool read_bytes(',1)[0]
 (OUT/'decoder_under_test.inc').write_text('using Box=person_roi::Box;'+decoder)
 elf=OUT/'dual_person_model.elf'
 cmd=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O2',
  '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-msmall-data-limit=0','-nostdlib',
  '-I'+str(SW/'replay_src'),'-I'+str(SW/'optimized/raw96x192/generated'),'-I'+str(OUT),str(test),
  '-Wl,-Ttext=0x1000,-e,run_pair_model','-lc','-lgcc','-o',str(elf)]
 r=subprocess.run(cmd,capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr);assert not r.returncode,r.stderr
 with elf.open('rb') as f:
  e=ELFFile(f);segments=[(p['p_vaddr'],p.data()) for p in e.iter_segments() if p['p_type']=='PT_LOAD']
  symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x1000000)
 for address,data in segments:uc.mem_write(address,data)
 def call(heads,fresh):
  uc.mem_write(symbols['pair_heads'],b''.join(h.tobytes() for h in heads));uc.mem_write(symbols['pair_fresh'],struct.pack('<I',fresh))
  uc.reg_write(UC_RISCV_REG_SP,0xf00000);uc.reg_write(UC_RISCV_REG_RA,0);uc.reg_write(UC_RISCV_REG_GP,symbols.get('__global_pointer$',0))
  uc.emu_start(symbols['run_pair_model'],0,count=20000000);assert uc.reg_read(UC_RISCV_REG_PC)==0
  actual=list(struct.unpack('<14i',uc.mem_read(symbols['pair_output'],56)))
  n=actual[0];boxes=[list(struct.unpack('<4iI',uc.mem_read(symbols['boxes']+i*20,20))) for i in range(n)]
  return actual,boxes
 variant=SW/'optimized/raw96x192';meta=json.loads((variant/'metadata.json').read_text())
 runtime=Interpreter(model_path=str(variant/'model.tflite'),num_threads=1,experimental_op_resolver_type=OpResolverType.BUILTIN_REF);runtime.allocate_tensors()
 image=cv2.imread(str(source));assert image.shape==(720,1280,3)
 def infer(image):
  b,g,r=[image[:,:,c].astype(np.uint16) for c in range(3)];words=((r>>3)<<11)|((g>>2)<<5)|(b>>3)
  nw,nh,px,py=171,96,10,0
  q=words[((2*np.arange(nh)+1)*720//(2*nh))[:,None],((2*np.arange(nw)+1)*1280//(2*nw))[None,:]].astype(np.int32)
  t=np.full((1,96,192,3),-14,np.int8);t[0,py:py+nh,px:px+nw]=np.stack(((q>>11)*255//31,((q>>5)&63)*255//63,(q&31)*255//31),-1)-128
  runtime.set_tensor(runtime.get_input_details()[0]['index'],t);runtime.invoke()
  return [runtime.get_tensor(o['index']) for o in runtime.get_output_details()]
 report=dict(complete=False,passed=False,board_accessed=False,reference_inference_on_pc=True,production_postprocess_rv32=True,
  source_url='https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/zidane.jpg',cases={})
 dest=OUT/'result.json';save=lambda:dest.write_text(json.dumps(report,indent=2),encoding='utf8');save()
 heads=infer(image);actual,raw_boxes=call(heads,1)
 assert raw_boxes==decode_fixed_reference(heads,meta),'production decoder differs from independent integer reference'
 assert actual[1]==2,actual
 slots=[dict(valid=actual[i],x1=actual[i+1],y1=actual[i+2],x2=actual[i+3],y2=actual[i+4],score_q15=actual[i+5]) for i in (2,8)]
 for slot in slots:
  assert slot['valid'] and slot['score_q15']>=8192 and 0<=slot['x1']<slot['x2']<=1280 and 0<=slot['y1']<slot['y2']<=720
 assert slots[0]['x2']<slots[1]['x2'] and slots[0]['x1']<slots[1]['x1'],'expected distinct left/right people'
 preview=image.copy()
 for slot in slots:cv2.rectangle(preview,(slot['x1'],slot['y1']),(slot['x2'],slot['y2']),(96,255,64),3)
 cv2.putText(preview,'PC MODEL + RV32 POSTPROCESS | NOT A BOARD CAPTURE',(16,28),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
 cv2.imwrite(str(OUT/'two_people_PC_reference.jpg'),preview)
 report['cases']['real_two_people']=dict(passed=True,raw_boxes=raw_boxes,slots=slots)
 stale,_=call(heads,0);assert stale[1]==0
 report['cases']['stale_two_people']=dict(passed=True,display_count=stale[1])
 empty_heads=infer(np.full_like(image,114));empty,_=call(empty_heads,1);assert empty[1]==0
 report['cases']['empty_scene']=dict(passed=True,display_count=empty[1])
 # Download parser must accept 2/1/0 as well as reject merged or stale boxes.
 rows=[dict(seq=i+1,drawn=n,present=int(bool(n))) for i,n in enumerate((2,1,0))]
 people=[dict(seq=i+1,count=n,primary=int(n>0),secondary=int(n>1),full_scene=1,stale=0) for i,n in enumerate((2,1,0))]
 primary={1:slots[0],2:slots[0]};secondary={1:slots[1]}
 assert people_output_valid(rows,people,primary,secondary)
 assert not people_output_valid(rows,people,primary,{1:slots[0]})
 people[0]['stale']=1;assert not people_output_valid(rows,people,primary,secondary);people[0]['stale']=0
 assert not people_output_valid(rows,people[:-1],primary,secondary)
 report['cases']['download_parser']=dict(passed=True)
 files=[Path(__file__),test,production,SW/'replay_src/person_pair.h',SW/'replay_src/person_roi.h',SW/'optimized/raw96x192/model.tflite',SW/'optimized/raw96x192/metadata.json',SW/'optimized/raw96x192/generated/fixture.h',ROOT/'delivery/yolo_fixed_reference.py',SW/'yolo_auto_download.py',source]
 report.update(complete=True,passed=True,limitation='One real two-person image and a uniform empty scene; no annotated box IoU, video accuracy or hardware FPS claim.',
  inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 save();print('PASS actual INT8 YOLO, exact production RV32 decoder, two mapped slots, stale/empty clear and download parser');print(dest)
if __name__=='__main__':main()
