"""PC reference preview: actual INT8 YOLO and the production RV32 fall algorithm.

Video timing is simulated input timing. This does not measure FPGA throughput.
"""
from pathlib import Path
import argparse,ast,hashlib,json,re,struct,sys
import cv2,numpy as np
from ai_edge_litert.interpreter import Interpreter,OpResolverType
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
VALID=ROOT/'fusion/ti60_yolo_auto/validation/fall_detection'
KEYS='state alarm event recovered armed tracked events track w h ratio_milli cx cy dy drop_milli'.split()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video');parser.add_argument('--cadence',type=float,default=3.5)
    parser.add_argument('--right',action='store_true')
    args=parser.parse_args()
    if args.cadence<=0:parser.error('--cadence must be positive')
    dest=ROOT/'YOLO_DSP_测试结果'/'跌倒红框_PC参考预览';dest.mkdir(parents=True,exist_ok=True)
    model=SW/'optimized/raw96x192/model.tflite'
    interpreter=Interpreter(model_path=str(model),num_threads=1,experimental_op_resolver_type=OpResolverType.BUILTIN_REF)
    interpreter.allocate_tensors();inp=interpreter.get_input_details()[0]
    details=sorted(interpreter.get_output_details(),key=lambda x:x['shape'][1])
    header=(SW/'optimized/raw96x192/generated/fixture.h').read_text()
    def table(name):
        raw=re.search(r'\b'+name+r'\[[^;]+?=\s*(\{.*?\});',header,re.S).group(1)
        return np.asarray(ast.literal_eval(raw.replace('{','[').replace('}',']')),dtype=np.int64)
    lut=table('kSigmoid');anchors=table('kAnchorQ8');strides=(32,16,8)
    uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x800000)
    with (VALID/'fall_detection_rv32_test.elf').open('rb') as f:
        elf=ELFFile(f)
        for s in elf.iter_segments():
            if s['p_type']=='PT_LOAD':uc.mem_write(s['p_vaddr'],s.data())
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
    def call(name):
        uc.reg_write(UC_RISCV_REG_SP,0x7f0000);uc.reg_write(UC_RISCV_REG_RA,0)
        if '__global_pointer$' in symbols:uc.reg_write(UC_RISCV_REG_GP,symbols['__global_pointer$'])
        uc.emu_start(symbols[name],0,count=1000000)
        assert uc.reg_read(UC_RISCV_REG_PC)==0
    call('fall_reset')
    def step(ms,box):
        uc.mem_write(symbols['fall_args'],struct.pack('<8I',ms,int(box is not None),*(box or (0,0,0,0,0)),0))
        call('fall_step');return dict(zip(KEYS,struct.unpack('<15i',uc.mem_read(symbols['fall_output'],60))))
    def decode():
        candidates=[]
        for h,detail in enumerate(details):
            raw=interpreter.get_tensor(detail['index']);_,height,width,_=raw.shape
            v=lut[h][raw.reshape(height,width,3,6).astype(np.int64)+128]
            score=(v[...,4]*v[...,5]+16384)>>15
            ys,xs,aa=np.where(score>=8192)
            if not len(ys):continue
            q=v[ys,xs,aa]
            center=(((q[:,:2]*512+16384)>>15)-128+np.column_stack((xs,ys))*256)*strides[h]
            wh=(q[:,2:4]**2*4*anchors[h].reshape(3,2)[aa]+(1<<29))>>30
            lo=np.maximum(0,center-wh//2);hi=np.minimum((192*256,96*256),center+wh//2)
            good=np.all(hi>lo,axis=1)
            candidates.extend(np.column_stack((lo,hi,score[ys,xs,aa]))[good].tolist())
        candidates=sorted(candidates,key=lambda a:-a[4])[:32];kept=[]
        for a in candidates:
            suppress=False
            for b in kept:
                w=max(0,min(a[2],b[2])-max(a[0],b[0]));h=max(0,min(a[3],b[3])-max(a[1],b[1]))
                inter=w*h;union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
                if inter*100>union*45:suppress=True;break
            if not suppress:kept.append(a)
            if len(kept)==8:break
        if not kept:return None
        a=kept[0]
        box=[max(0,min(limit,(value-pad*256)*scale//content//256))
          for value,pad,scale,content,limit in zip(a[:4],(10,0,10,0),(1280,720,1280,720),(171,96,171,96),(1279,719,1280,720))]
        return (*box,a[4])
    video=Path(args.video);capture=cv2.VideoCapture(str(video));assert capture.isOpened()
    fps=capture.get(cv2.CAP_PROP_FPS);count=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    output=dest/('preview_'+str(args.cadence)+'fps.mp4')
    writer=cv2.VideoWriter(str(output),cv2.VideoWriter_fourcc(*'mp4v'),fps,(1280,720));assert writer.isOpened()
    rows=[];frame_id=0;next_time=0;last_box=None;last=None
    sx=((2*np.arange(171)+1)*1280//342).astype(int);sy=((2*np.arange(96)+1)*720//192).astype(int)
    while True:
        good,frame=capture.read()
        if not good:break
        if args.right:frame=frame[:,frame.shape[1]//2:]
        frame=cv2.resize(frame,(1280,720));ms=round(frame_id*1000/fps)
        if ms+1>=next_time:
            rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)[np.ix_(sy,sx)].astype(np.int32)
            rgb=(rgb>>(3,2,3))*255//np.asarray((31,63,31))
            image=np.full((1,96,192,3),-14,dtype=np.int8);image[0,:,10:181]=(rgb-128).astype(np.int8)
            interpreter.set_tensor(inp['index'],image);interpreter.invoke();last_box=decode();last=step(ms,last_box)
            rows.append(dict(ms=ms,frame=frame_id,box=last_box,**last));next_time+=1000/args.cadence
        if last_box:
            x1,y1,x2,y2,score=last_box;color=(64,64,255) if last['alarm'] else (96,255,64)
            cv2.rectangle(frame,(x1,y1),(x2-1,y2-1),color,3)
            cv2.putText(frame,('FALL' if last['alarm'] else 'PERSON')+f' {score/32768:.2f}',(x1,max(55,y1-10)),cv2.FONT_HERSHEY_SIMPLEX,.8,color,2)
        cv2.rectangle(frame,(0,0),(1280,45),(18,18,18),-1)
        cv2.putText(frame,f'PC reference only | INT8 YOLO + RV32 fall logic | simulated {args.cadence:g} detections/s | t={ms/1000:.2f}s',
            (12,28),cv2.FONT_HERSHEY_SIMPLEX,.62,(255,255,255),1)
        writer.write(frame);frame_id+=1
    capture.release();writer.release()
    alarm_times=[r['ms'] for r in rows if r['event']]
    report=dict(complete=True,board_accessed=False,board_speed_measured=False,video=str(video),video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
      model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),algorithm_sha256=hashlib.sha256((SW/'replay_src/fall_detection.h').read_bytes()).hexdigest(),
      source_frames=count,source_fps=fps,simulated_detection_fps=args.cadence,events=len(alarm_times),first_alarm_ms=alarm_times[0] if alarm_times else None,
      output=str(output),rows=rows,note='PC reference detections with production RV32 event code; no real-board speed or visual verification claim.')
    path=dest/('result_'+str(args.cadence)+'fps.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
