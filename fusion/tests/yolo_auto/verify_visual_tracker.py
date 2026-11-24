"""Execute production RV32 pixel continuity on controlled scenes; not accuracy/FPS."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
import numpy as np
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_PC
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/lying_v5_port'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    test=Path(__file__).with_name('person_visual_track_rv32_test.cc');elf=OUT/'visual_unit.elf'
    cmd=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O3',
      '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-msmall-data-limit=0','-nostdlib',
      '-I'+str(SW/'replay_src'),str(test),'-Wl,-Ttext=0x1000,-e,visual_reset','-lc','-lgcc','-o',str(elf)]
    subprocess.run(cmd,check=True,capture_output=True)
    uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x800000)
    with elf.open('rb') as f:
        e=ELFFile(f)
        for seg in e.iter_segments():
            if seg['p_type']=='PT_LOAD':uc.mem_write(seg['p_vaddr'],seg.data())
        symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
    def call(name):
        uc.reg_write(UC_RISCV_REG_SP,0x7f0000);uc.reg_write(UC_RISCV_REG_RA,0)
        uc.emu_start(symbols[name],0,count=20000000)
        assert uc.reg_read(UC_RISCV_REG_PC)==0
    now=0
    def step(rect=None,model=False,rgb=(35,90,180),bg=(90,100,110),extra=None,tail=None):
        nonlocal now
        image=np.full((72,128,3),bg,np.uint16)
        for box,color in [(rect,rgb),(extra,(200,35,30)),(tail,rgb)]:
            if box is not None:
                x1,y1,x2,y2=box;image[y1//10:y2//10,x1//10:x2//10]=color
        words=((image[:,:,0]>>3)<<11)|((image[:,:,1]>>2)<<5)|(image[:,:,2]>>3)
        uc.mem_write(symbols['visual_pixels'],words.astype('<u2').tobytes())
        uc.mem_write(symbols['visual_model'],struct.pack('<6i',*(rect or (0,0,0,0)),25000 if model else 0,int(model)))
        uc.mem_write(symbols['roi_args'],struct.pack('<3I',now,0,0));now+=450
        call('visual_direct')
        return struct.unpack('<16i',uc.mem_read(symbols['visual_info'],64)),struct.unpack('<32i',uc.mem_read(symbols['roi_output'],128))
    checks=[]
    call('visual_reset')
    lying=(420,500,920,650);stand=(590,180,710,650)
    for _ in range(12):assert not step()[0][5]
    for _ in range(10):assert not step(lying)[0][5]
    checks.append('Moving/lying foreground without a genuine YOLO identity never creates a person.')
    call('visual_reset')
    for _ in range(12):step()
    for _ in range(4):assert step(stand,True)[0][5]
    for r in [(550,250,760,650),(510,350,820,650),lying,lying]:
        v,f=step(r);assert v[5] and v[6],v
    for _ in range(140):
        v,f=step(lying);assert v[5] and v[6],v
    assert f[1],f
    checks.append('After YOLO-confirmed standing, descent and 63 seconds of motionless lying retain CURRENT-pixel boxes and trigger the existing red alarm.')
    for _ in range(6):assert not step()[0][5]
    checks.append('An empty current image clears the box immediately; alarm state alone cannot draw a box.')
    for _ in range(6):assert not step(extra=lying)[0][5]
    checks.append('A differently colored object cannot inherit an expired person identity.')
    call('visual_reset')
    for _ in range(12):step()
    for _ in range(4):step(stand,True)
    for _ in range(4):
        v,_=step(stand,rgb=(55,110,200),bg=(110,120,130));assert v[5] and v[6],v
    checks.append('Uniform illumination shift is compensated instead of changing the entire scene to foreground.')
    v,_=step(bg=(220,30,40));assert not v[5]
    checks.append('A major scene change without person evidence produces no retained box.')
    call('visual_reset')
    for _ in range(12):step()
    for _ in range(4):step(stand,True)
    for _ in range(20):assert not step(extra=lying)[0][5]
    checks.append('Different current foreground appearance cannot continue a YOLO-confirmed person.')
    call('visual_reset')
    for _ in range(12):step()
    for _ in range(4):step(stand,True)
    for rect in [(550,250,760,650),(510,350,820,650),lying]:step(rect)
    for _ in range(5):
        v,_=step(lying,tail=(650,300,670,500))
        assert v[5] and v[6],v
        assert v[1]>=480 and v[3]<=660,v
        assert v[0]<=lying[0] and v[2]>=lying[2],v
    checks.append('A thin vertical foreground connection is trimmed from the lying-person box while the observed horizontal body extent is preserved.')
    files=[Path(__file__),test,test.with_name('person_roi_rv32_test.cc'),SW/'replay_src/person_visual_track.h',SW/'replay_src/person_roi.h',SW/'replay_src/fall_detection.h']
    report=dict(complete=True,passed=True,board_accessed=False,weights_retrained=False,tests=checks,
      inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (OUT/'tracker_result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
