"""Run real INT8 YOLO and the compiled production RV32 ROI/fall logic on a video.

PC reference only. No trained weights, annotations, or board performance claims.
"""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,sys
import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter,OpResolverType
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/lying_v5_port'
sys.path.insert(0,str(ROOT/'delivery'))
from yolo_fixed_reference import decode_fixed_reference
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--repeat-first',dest='tail_empty',type=int,default=0,help='Diagnostic repeat of first frame; only empty if manually verified')
    p.add_argument('--view',choices=['full','right'],default='full')
    p.add_argument('--stride',type=int,default=1);p.add_argument('--phase',type=int,default=0)
    args=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    elf=OUT/'person_roi_rv32_test.elf';test=Path(__file__).with_name('person_visual_track_rv32_test.cc')
    command=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O3',
      '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffunction-sections','-fdata-sections','-msmall-data-limit=0','-nostdlib',
      '-I'+str(SW/'replay_src'),str(test),'-Wl,-Ttext=0x1000,-e,roi_reset,--gc-sections',
      *['-Wl,--undefined='+n for n in ('roi_plan','roi_alternate','roi_pick','visual_commit','visual_reset','visual_observe','visual_finish')],'-lc','-lgcc','-o',str(elf)]
    r=subprocess.run(command,capture_output=True,text=True);(OUT/'roi_compile.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x800000)
    with elf.open('rb') as stream:
        e=ELFFile(stream)
        for s in e.iter_segments():
            if s['p_type']=='PT_LOAD':uc.mem_write(s['p_vaddr'],s.data())
        symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
    def call(name,count=0,secondary=0):
        uc.mem_write(symbols['roi_args'],struct.pack('<3I',now,count,secondary))
        uc.reg_write(UC_RISCV_REG_SP,0x7f0000);uc.reg_write(UC_RISCV_REG_RA,0)
        if '__global_pointer$' in symbols:uc.reg_write(UC_RISCV_REG_GP,symbols['__global_pointer$'])
        uc.emu_start(symbols[name],0,count=20000000)
        assert uc.reg_read(UC_RISCV_REG_PC)==0
        return list(struct.unpack('<32i',uc.mem_read(symbols['roi_output'],128)))
    variant=SW/'optimized/raw96x192';meta=json.loads((variant/'metadata.json').read_text())
    runtime=Interpreter(model_path=str(variant/'model.tflite'),num_threads=1,experimental_op_resolver_type=OpResolverType.BUILTIN_REF);runtime.allocate_tensors()
    index=runtime.get_input_details()[0]['index'];outputs=runtime.get_output_details()
    def infer(words,v):
        x1,y1,x2,y2,nw,nh,px,py,zoom,turns=v[:10]
        source=np.rot90(words[y1:y2,x1:x2],-turns);h,w=source.shape
        xs=((2*np.arange(nw)+1)*w)//(2*nw)
        ys=((2*np.arange(nh)+1)*h)//(2*nh)
        q=source[ys[:,None],xs[None,:]].astype(np.int32)
        rgb=np.stack(((q>>11)*255//31,((q>>5)&63)*255//63,(q&31)*255//31),-1)
        t=np.full((1,96,192,3),-14,np.int8);t[0,py:py+nh,px:px+nw]=(rgb-128).astype(np.int8)
        runtime.set_tensor(index,t);runtime.invoke()
        return decode_fixed_reference([runtime.get_tensor(o['index']) for o in outputs],meta)
    cap=cv2.VideoCapture(str(args.video));fps=cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened():raise RuntimeError('Cannot open '+str(args.video))
    tag=f'{args.video.stem}_s{args.stride}_p{args.phase}'
    writer=cv2.VideoWriter(str(OUT/(tag+'_PC_only.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),fps/args.stride,(640,400))
    rows=[];previews=[];now=0;call('visual_reset');frame_index=0;last_image=None;tail_index=0
    while True:
        ok,frame=cap.read()
        is_tail=not ok
        if is_tail:
            if tail_index>=args.tail_empty or last_image is None:break
            frame=last_image.copy();tail_index+=1
        elif last_image is None:last_image=frame.copy()
        i=frame_index;frame_index+=1
        if i%args.stride!=args.phase:continue
        now=round(i*1000/fps)
        if args.view=='right':frame=frame[:,frame.shape[1]//2:]
        scale=min(1280/frame.shape[1],720/frame.shape[0]);w,h=round(frame.shape[1]*scale),round(frame.shape[0]*scale)
        image=np.full((720,1280,3),114,np.uint8);x,y=(1280-w)//2,(720-h)//2
        image[y:y+h,x:x+w]=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA)
        b,g,r=[image[:,:,c].astype(np.uint16) for c in range(3)];words=((r>>3)<<11)|((g>>2)<<5)|(b>>3)
        view=call('roi_plan');passes=0
        uc.mem_write(symbols['visual_pixels'],words[5::10,5::10].astype('<u2').tobytes())
        for attempt in range(2):
            boxes=infer(words,view);passes+=1
            uc.mem_write(symbols['roi_boxes'],b''.join(struct.pack('<4iI',*b) for b in boxes))
            selected=call('roi_pick',len(boxes))
            if not attempt:
                call('visual_observe')
                t=list(struct.unpack('<16i',uc.mem_read(symbols['visual_info'],64)))
            if selected[5] or attempt:break
            secondary_view=call('roi_alternate')
            if not view[8] and not secondary_view[8]:break
            if t[5] and len(rows)%4!=0:break
            view=secondary_view
        model_present=bool(selected[5])
        state=call('visual_finish',secondary=passes==2)
        tracking=list(struct.unpack('<16i',uc.mem_read(symbols['visual_info'],64)))
        selected=tracking[:6]
        rows.append(dict(frame=i,ms=now,present=bool(selected[5]),box=selected[:5],view=view[:10],passes=passes,state=state[0],alarm=bool(state[1]),event=bool(state[2]),model_present=model_present,fallback=bool(tracking[6]),bg_ready=bool(tracking[7]),fg=tracking[8],support=tracking[9],known=tracking[10],scene_change=tracking[11],appearance=tracking[12],tail_diagnostic=is_tail))
        picture=cv2.resize(image,(640,360))
        if selected[5]:
            a,b,c,d,score=selected[:5];cv2.rectangle(picture,(a//2,b//2),(c//2,d//2),(0,0,255) if state[1] else (0,255,0),2)
        banner=np.full((40,640,3),35,np.uint8)
        cv2.putText(banner,f'PC ONLY | frame={i} score={selected[4]/32768:.2f} alarm={state[1]} src={'PIX' if tracking[6] else 'YOLO'}',(5,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
        annotated=np.vstack((banner,picture));writer.write(annotated)
        if len(rows)==1 or len(rows)%8==0:previews.append(annotated)
        if len(rows)%30==0:print('processed',len(rows),'missing',sum(not r['present'] for r in rows),flush=True)
    cap.release();writer.release()
    report=dict(complete=True,passed=bool(rows),board_accessed=False,weights_retrained=False,
        model_sha256=hashlib.sha256((variant/'model.tflite').read_bytes()).hexdigest(),source=str(args.video),source_sha256=hashlib.sha256(args.video.read_bytes()).hexdigest(),
        stride=args.stride,phase=args.phase,frames=len(rows),detected_frames=sum(r['present'] for r in rows),missing=[r['frame'] for r in rows if not r['present']],
        fall_events=[r['frame'] for r in rows if r['event']],red_frames=sum(r['present'] and r['alarm'] for r in rows),
        inference_passes=sum(r['passes'] for r in rows),ground_truth_boxes_available=False,tail_is_first_frame_repeat_not_empty_ground_truth=bool(args.tail_empty),model_frames=sum(r['model_present'] for r in rows),fallback_frames=sum(r['fallback'] for r in rows),rows=rows,inputs_sha256={})
    for path in (Path(__file__),test,Path(__file__).with_name('person_roi_rv32_test.cc'),SW/'replay_src/person_visual_track.h',SW/'replay_src/person_roi.h',SW/'replay_src/fall_detection.h',ROOT/'delivery/yolo_fixed_reference.py'):
        report['inputs_sha256'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT/(tag+'.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
    if previews:
        while len(previews)%3:previews.append(np.zeros_like(previews[0]))
        cv2.imwrite(str(OUT/(tag+'_contact.jpg')),np.vstack([np.hstack(previews[i:i+3]) for i in range(0,len(previews),3)]))
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','inputs_sha256')},indent=2))
if __name__=='__main__':main()
