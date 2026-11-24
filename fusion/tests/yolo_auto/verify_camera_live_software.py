"""Execute the real RV32 preprocessing/lease/overlay code against golden data."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import argparse
import numpy as np

sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC

ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/camera_live'
TEST=Path(__file__).with_name('camera_live_software_test.cc')

def model_contract():
    blob=(SW/'optimized/raw96x192/model.tflite').read_bytes()
    u32=lambda off:struct.unpack_from('<I',blob,off)[0]
    def field(table,index):
        vt=table-struct.unpack_from('<i',blob,table)[0]
        return table+struct.unpack_from('<H',blob,vt+4+2*index)[0]
    ref=lambda off:off+u32(off)
    def vector(off):
        start=ref(off);return [start+4+i*4 for i in range(u32(start))]
    sub=ref(vector(field(u32(0),2))[0])
    index=u32(vector(field(sub,1))[0]);tensor=ref(vector(field(sub,0))[index])
    shape=[u32(p) for p in vector(field(tensor,0))]
    q=ref(field(tensor,4));scale=struct.unpack_from('<f',blob,ref(field(q,2))+4)[0]
    zp=struct.unpack_from('<q',blob,ref(field(q,3))+4)[0]
    assert shape==[1,96,192,3] and blob[field(tensor,1)]==9
    assert abs(scale-1/255)<1e-9 and zp==-128,(shape,scale,zp)
    return dict(shape=shape,scale=scale,zero_point=zp)

def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--multimodal-live',action='store_true')
    args=parser.parse_args()
    if args.multimodal_live:OUT=ROOT/'fusion/ti60_yolo_auto/validation/multimodal_live'
    OUT.mkdir(parents=True,exist_ok=True)
    result=dict(complete=False,passed=False,board_accessed=False,model_input=model_contract(),checks=[])
    dest=OUT/'software_result.json'
    save=lambda:dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
    save()
    elf=OUT/'camera_live_software_test.elf'
    vendor=SW/'runtime'
    include=[SW/'compat_include',SW/'replay_src',SW/'src',SW/'compat_src',SW/'compatibility',SW/'optimized/raw96x192/generated',vendor,vendor/'platform/interrupt',vendor/'platform/tinyml/ops']
    command=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O2',
      '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffunction-sections','-fdata-sections','-msmall-data-limit=0','-nostdlib',
      *['-I'+str(p) for p in include],str(TEST),'-Wl,-Ttext=0x1000,-e,run_prepare,--gc-sections',
      *['-Wl,--undefined='+n for n in ('run_capture','run_monitor','run_overlay','run_overlay_pair','run_rectangle','run_prepare_view','run_capture_views','run_map_view')],'-lc','-lgcc','-o',str(elf)]
    if args.multimodal_live:command.insert(1,'-DYOLO_MULTIMODAL')
    r=subprocess.run(command,capture_output=True,text=True)
    (OUT/'software_compile.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x800000);uc.mem_map(0x06000000,0x600000);uc.mem_map(0xf8100000,0x10000)
    with elf.open('rb') as stream:
        e=ELFFile(stream)
        for segment in e.iter_segments():
            if segment['p_type']=='PT_LOAD':uc.mem_write(segment['p_vaddr'],segment.data())
        symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
    def put(addr,value):uc.mem_write(addr,struct.pack('<I',value&0xffffffff))
    def get(addr):return struct.unpack('<I',uc.mem_read(addr,4))[0]
    def call(name):
        uc.reg_write(UC_RISCV_REG_SP,0x7f0000);uc.reg_write(UC_RISCV_REG_RA,0)
        if '__global_pointer$' in symbols:uc.reg_write(UC_RISCV_REG_GP,symbols['__global_pointer$'])
        uc.emu_start(symbols[name],0,count=20000000)
        assert uc.reg_read(UC_RISCV_REG_PC)==0,'RV32 test did not return'
    state=dict(ms=0,ack_lease=True,release=True,expire=False,reads=0,pixel_reads=0,delay=0,ack_box=True,commits=[])
    def read_hook(_,__,addr,size,value,___):
        if addr==0xf8103ff0:state['ms']+=1;put(addr,state['ms'])
        if 0x06000000<=addr<0x06600000:state['pixel_reads']+=1
        if addr==0xf8105108:
            state['reads']+=1
            if state['expire'] and state['reads']>=2:put(addr,5)
        if addr==0xf8101070 and state['delay']:
            state['delay']-=1
            if not state['delay']:
                put(addr,4)
                if state['ack_box']:put(0xf810107c,get(0xf8101078))
    def write_hook(_,__,addr,size,value,___):
        if addr==0xf8105104:
            if value and state['ack_lease']:put(0xf8105108,7)
            elif not value and state['release']:put(0xf8105108,0)
        if addr in (0xf8101060,0xf8101064,0xf8101068,0xf8101078,0xf810106c,0xf8101098,0xf810109c,0xf81010a0):
            assert get(0xf8101070)==4,'wrote mailbox while busy'
            if addr==0xf810106c:
                state['commits'].append([get(p) for p in (0xf8101060,0xf8101064,0xf8101068,0xf8101078)])
                put(0xf8101070,5);state['delay']=3
    uc.hook_add(UC_HOOK_MEM_READ,read_hook);uc.hook_add(UC_HOOK_MEM_WRITE,write_hook)
    put(0xf8105100,0x59465233 if args.multimodal_live else 0x59465232);put(0xf8101058,0x59415539 if args.multimodal_live else 0x59434d32)
    put(0xf810512c,123456)
    for off,value in [(20,1280),(24,720),(28,0x565),(32,0x20000)]:put(0xf8105100+off,value)
    pixels=(np.arange(1280*720,dtype=np.uint32)*7919+17).astype(np.uint16).reshape(720,1280)
    rng=np.random.default_rng(1040)
    patterns=[pixels,rng.integers(0,65536,(720,1280),dtype=np.uint16)]
    patterns += [np.full((720,1280),color,dtype=np.uint16) for color in (0,0xffff,0xf800,0x07e0,0x001f)]
    def expected(p):
        sy=np.floor((np.arange(96)+.5)*720/96).astype(int)
        sx=np.floor((np.arange(171)+.5)*1280/171).astype(int)
        p=p[np.ix_(sy,sx)].astype(np.int32)
        rgb=np.stack([(p>>11)*255//31,((p>>5)&63)*255//63,(p&31)*255//31],axis=-1)
        out=np.full((96,192,3),114,dtype=np.int32);out[:,10:181]=rgb
        return (out-128).astype(np.int8).tobytes()
    for p in patterns:
        uc.mem_write(0x06000000,p.tobytes());call('run_prepare')
        assert bytes(uc.mem_read(symbols['test_image'],55296))==expected(p)
    result['checks'].append('All 55296 input bytes match independent golden data for random, patterned and RGB primary/black/white frames; letterbox 10/11 columns.')
    for bank,count,seq in [(0x06000000,69999,65534),(0x06200000,70000,65535),(0x06400000,70001,0)]:
        uc.mem_write(bank,pixels.tobytes());put(0xf810510c,bank);put(0xf8105110,seq);put(0xf8105128,count)
        state['reads']=state['pixel_reads']=0;call('run_capture')
        assert get(symbols['test_result'])==1 and get(0xf8105108)==0 and state['pixel_reads']==171*96+384+128*72
        assert get(symbols['test_frame'])==seq and get(symbols['test_frame']+4)==count and get(symbols['test_frame']+16)==0
        if args.multimodal_live:assert get(symbols['test_frame']+8)==123456,'frame must retain acquisition timestamp, not CPU copy time'
        assert bytes(uc.mem_read(symbols['test_image'],55296))==expected(pixels)
    state['pixel_reads']=0;call('run_capture');assert get(symbols['test_result'])==0 and not state['pixel_reads']
    put(0xf8105128,70002);put(0xf810510c,0x1000);call('run_capture');assert get(symbols['test_result'])==0
    put(0xf810510c,0x06000000);state['reads']=0;state['expire']=True;call('run_capture');assert get(symbols['test_result'])==0
    state['expire']=False;state['ack_lease']=False;call('run_capture');assert get(symbols['test_result'])==0
    state['ack_lease']=True;state['release']=False;call('run_capture');assert get(symbols['test_result'])==0
    state['release']=True;put(0xf8105108,0)
    result['checks'].append('Lease release before inference, three valid banks, sequence wrap, duplicate rejection, invalid address, expired lease, acquire/release timeouts.')
    def expected_roi(p,rect,turns=0):
        x1,y1,x2,y2=rect;p=np.rot90(p[y1:y2,x1:x2],-turns);h,w=p.shape
        nw=min(192,(96*w+h//2)//h);nh=min(96,(192*h+w//2)//w);px,py=(192-nw)//2,(96-nh)//2
        xs=((2*np.arange(nw)+1)*w)//(2*nw);ys=((2*np.arange(nh)+1)*h)//(2*nh)
        q=p[np.ix_(ys,xs)].astype(np.int32)
        rgb=np.stack(((q>>11)*255//31,((q>>5)&63)*255//63,(q&31)*255//31),-1)
        out=np.full((96,192,3),-14,dtype=np.int8);out[py:py+nh,px:px+nw]=(rgb-128).astype(np.int8)
        return out.tobytes()
    uc.mem_write(0x06000000,pixels.tobytes())
    for rect in ((320,180,960,540),(0,0,960,540),(1,1,1279,719),(600,100,980,650)):
        for turns in range(4):
            uc.mem_write(symbols['test_args'],struct.pack('<5i',*rect,turns));call('run_prepare_view')
            assert bytes(uc.mem_read(symbols['test_image'],55296))==expected_roi(pixels,rect,turns)
    put(0xf8105128,70003);state['reads']=0;call('run_capture_views')
    assert get(symbols['test_result'])==1 and get(0xf8105108)==0
    assert bytes(uc.mem_read(symbols['test_image'],55296))==expected_roi(pixels,(320,180,960,540))
    assert bytes(uc.mem_read(symbols['test_alternate'],55296))==expected(pixels)
    gx=(2*np.arange(24)+1)*1280//48;gy=(2*np.arange(16)+1)*720//32
    q=pixels[np.ix_(gy,gx)].astype(np.int32)
    gray=((77*((q>>11)*255//31)+150*(((q>>5)&63)*255//63)+29*((q&31)*255//31)+128)>>8).astype(np.uint8)
    assert bytes(uc.mem_read(symbols['test_frame']+20,384))==gray.tobytes()
    assert bytes(uc.mem_read(symbols['test_frame']+404,128*72*2))==pixels[5::10,5::10].astype('<u2').tobytes()
    put(0xf8105128,70004);put(0xf810512c,234567);state['pixel_reads']=state['reads']=0
    before_tensor=bytes(uc.mem_read(symbols['test_image'],55296));before_support=bytes(uc.mem_read(symbols['test_frame']+404,128*72*2))
    call('run_monitor')
    assert get(symbols['test_result'])==1 and get(0xf8105108)==0 and state['pixel_reads']==384
    assert bytes(uc.mem_read(symbols['test_frame']+20,384))==gray.tobytes()
    assert bytes(uc.mem_read(symbols['test_image'],55296))==before_tensor
    assert bytes(uc.mem_read(symbols['test_frame']+404,128*72*2))==before_support
    if args.multimodal_live:assert get(symbols['test_frame']+8)==234567
    state['pixel_reads']=0;call('run_monitor');assert get(symbols['test_result'])==0 and not state['pixel_reads']
    result['checks'].append('Low-power monitor reads exactly 384 pixels from one leased frame, preserves acquisition time, rejects duplicates and never writes neural tensors/tracker pixels.')
    result['checks'].append('The full-scene 128x72 RGB565 tracking sample matches independent golden data and shares the model inputs lease.')
    result['checks'].append('Adaptive ROI and all four rotation tensors match independent integer golden pixels, including odd boundaries; both views and the full-scene motion grid use the same leased frame, released before inference.')
    rect=(320,180,960,540);original=(400,250,800,450)
    for turns in range(4):
        x1,y1,x2,y2=rect;w,h=x2-x1,y2-y1
        a,b,c,d=original;a-=x1;c-=x1;b-=y1;d-=y1
        transformed=[(a,b,c,d),(h-d,a,h-b,c),(w-c,h-d,w-a,h-b),(b,w-c,d,w-a)][turns]
        rw,rh=(h,w) if turns&1 else (w,h)
        nw,nh=min(192,(96*rw+rh//2)//rh),min(96,(192*rh+rw//2)//rw)
        px,py=(192-nw)//2,(96-nh)//2
        coords=[px*256+transformed[0]*nw*256//rw,py*256+transformed[1]*nh*256//rh,
                px*256+transformed[2]*nw*256//rw,py*256+transformed[3]*nh*256//rh]
        uc.mem_write(symbols['test_map_args'],struct.pack('<9i',*rect,turns,*coords));call('run_map_view')
        actual=struct.unpack('<4i',uc.mem_read(symbols['test_map_result'],16))
        assert all(abs(a-b)<=1 for a,b in zip(actual,original)),(turns,actual)
    result['checks'].append('All four rotated detector-box coordinates invert to the same original scene rectangle within one pixel.')
    def rectangle(args):
        uc.mem_write(symbols['test_args'],struct.pack('<5i',*args));call('run_rectangle')
        return struct.unpack('<4iB',uc.mem_read(symbols['test_rectangle'],17))
    assert rectangle([1,10*256,0,181*256,96*256])==(0,0,1280,720,1)
    assert rectangle([1,-1000,-1000,999999,999999])==(0,0,1280,720,1)
    assert not rectangle([1,1000,1000,0,0])[-1]
    rectangle([1,10*256,0,181*256,96*256]);put(0xf8101070,4);put(symbols['test_args'],73);call('run_overlay')
    assert get(symbols['test_result'])==1 and state['commits'][-1]==[3,(144<<16)|32,(864<<16)|1312,73]
    put(symbols['test_alarm'],1);put(symbols['test_args'],74);call('run_overlay')
    assert get(symbols['test_result'])==1 and state['commits'][-1]==[7,(144<<16)|32,(864<<16)|1312,74]
    put(symbols['test_alarm'],0);put(symbols['test_args'],75);call('run_overlay')
    assert get(symbols['test_result'])==1 and state['commits'][-1][0]==3
    rectangle([0,0,0,0,0]);put(symbols['test_args'],74);call('run_overlay')
    assert get(symbols['test_result'])==1 and state['commits'][-1]==[0,0,0,74]
    put(symbols['test_alarm'],1);put(symbols['test_args'],76);call('run_overlay')
    assert get(symbols['test_result'])==1 and state['commits'][-1]==[0,0,0,76]
    put(symbols['test_alarm'],0)
    if args.multimodal_live:
        put(0xf8101070,4);put(symbols['test_args'],80)
        uc.mem_write(symbols['test_rectangle'],struct.pack('<4iB',100,100,400,600,1))
        uc.mem_write(symbols['test_second'],struct.pack('<4iB',700,120,1000,650,1))
        before=len(state['commits']);call('run_overlay_pair')
        assert get(symbols['test_result'])==1 and len(state['commits'])==before+1
        assert state['commits'][-1]==[3,(244<<16)|132,(744<<16)|432,80]
        assert [get(p) for p in (0xf8101098,0xf810109c,0xf81010a0)]==[1,(264<<16)|732,(794<<16)|1032]
        # A legacy single-person or clear call must disable the second slot.
        put(symbols['test_args'],81);call('run_overlay')
        assert get(symbols['test_result'])==1 and get(0xf8101098)==get(0xf810109c)==get(0xf81010a0)==0
        result['checks'].append('Two actual RV32 rectangles share one commit/ACK, have independent HDMI offsets, and single/clear calls disable the second slot.')
    put(0xf8101070,5);before=len(state['commits']);call('run_overlay')
    assert get(symbols['test_result'])==0 and len(state['commits'])==before
    put(0xf8101070,4);state['ack_box']=False;put(symbols['test_args'],75);call('run_overlay');assert get(symbols['test_result'])==0
    result['checks'].append('Full-frame and clipped coordinate mapping, HDMI offset, green=3/red=7/recovered green, alarm without valid box clears, blank-time ACK, busy timeout, stale/wrong ACK rejection.')
    sources=[Path(__file__),TEST,SW/'replay_src/camera_live_source.h',SW/'replay_src/person_roi.h',SW/'replay_src/person_visual_track.h',SW/'optimized/raw96x192/generated/fixture.h',SW/'optimized/raw96x192/model.tflite']
    result.update(complete=True,passed=True,inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    save();print(json.dumps(result,indent=2))

if __name__=='__main__':main()
