"""Execute production RV32 fall logic against timed positive/negative scenarios.

Synthetic detections verify event logic and time semantics; not accuracy claims
for a camera or a dataset. A separate RTL test verifies actual border colors.
"""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC

ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/fall_detection'
HEADER=SW/'replay_src/fall_detection.h'
TEST=Path(__file__).with_name('fall_detection_rv32_test.cc')
KEYS='state alarm event recovered armed tracked events track w h ratio_milli cx cy dy drop_milli evidence candidate_ms reference_height reference_age_ms drop_age_ms'.split()
STAND=(520,150,680,650)
LYING=(430,450,830,650)

def main():
    OUT.mkdir(parents=True,exist_ok=True);elf=OUT/'fall_detection_rv32_test.elf'
    command=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O3',
      '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-ffunction-sections','-fdata-sections','-msmall-data-limit=0','-nostdlib',
      '-I'+str(HEADER.parent),str(TEST),'-Wl,-Ttext=0x1000,-e,fall_reset,--gc-sections',
      *['-Wl,--undefined='+n for n in ('fall_step','motion_capture','motion_region')],'-lc','-lgcc','-o',str(elf)]
    build=subprocess.run(command,capture_output=True,text=True)
    (OUT/'fall_compile.log').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError(build.stdout+build.stderr)
    with elf.open('rb') as stream:
        e=ELFFile(stream);segments=[(s['p_vaddr'],s.data()) for s in e.iter_segments() if s['p_type']=='PT_LOAD']
        symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
    report=dict(complete=False,passed=False,board_accessed=False,cases={},inputs_sha256={})
    for p in (Path(__file__),HEADER,TEST):report['inputs_sha256'][p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    result_path=OUT/'fall_result.json'
    def save():result_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    save()
    class Run:
        def __init__(self,offset=0):
            self.uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);self.uc.mem_map(0,0x800000)
            for a,data in segments:self.uc.mem_write(a,data)
            self.rows=[];self.offset=offset;self.call('fall_reset')
        def call(self,name):
            self.uc.reg_write(UC_RISCV_REG_SP,0x7f0000);self.uc.reg_write(UC_RISCV_REG_RA,0)
            if '__global_pointer$' in symbols:self.uc.reg_write(UC_RISCV_REG_GP,symbols['__global_pointer$'])
            self.uc.emu_start(symbols[name],0,count=1000000)
            assert self.uc.reg_read(UC_RISCV_REG_PC)==0,'RV32 function did not return'
        def step(self,ms,box=STAND,score=25000,pixels=False):
            args=[(ms+self.offset)&0xffffffff,int(box is not None),*(box or (0,0,0,0)),score,int(pixels)]
            self.uc.mem_write(symbols['fall_args'],struct.pack('<8I',*args));self.call('fall_step')
            row=dict(zip(KEYS,struct.unpack('<20i',self.uc.mem_read(symbols['fall_output'],80))))
            row['ms']=ms;row['input']=args;self.rows.append(row);return row
        def arm(self):
            for t in (0,280,560,840):self.step(t)
            assert self.rows[-1]['armed']==1
        def finish(self,name):
            report['cases'][name]=dict(passed=True,rows=self.rows);save();print('PASS fall RV32',name,flush=True)
    for name,box in [('standing',STAND),('sitting',(500,330,720,650)),('bending',(450,270,790,640))]:
        r=Run();r.arm()
        for t in range(1120,5041,280):assert not r.step(t,box)['alarm']
        r.finish(name)
    for cadence in (200,280,500):
        r=Run();r.arm();a=r.step(1000+cadence,LYING)
        assert a['state']==2 and not a['alarm']
        a=r.step(1000+2*cadence,LYING);assert a['alarm'] and a['event']
        for t in range(1000+3*cadence,5000,cadence):
            a=r.step(t,LYING);assert a['alarm'] and not a['event'] and a['events']==1
        r.finish('fall_cadence_'+str(cadence))
    r=Run();r.arm();assert not r.step(1120,LYING)['alarm'];assert not r.step(1400)['alarm'];r.finish('single_frame_wide_outlier')
    r=Run()
    for t in range(0,5041,280):assert not r.step(t,LYING)['alarm']
    r.finish('lying_at_start_is_not_a_witnessed_fall')
    r=Run();r.arm()
    for t in range(1120,5041,280):assert not r.step(t,(900,450,1270,650))['alarm']
    r.finish('distant_person_switch')
    r=Run();r.arm();r.step(1120,LYING);assert not r.step(1400,None)['alarm'];assert r.step(1680,LYING)['event'];r.finish('brief_miss_preserves_but_cannot_confirm_candidate')
    r=Run();r.arm();r.step(1120,LYING);assert not r.step(1760,None)['alarm'];assert not r.step(1960,LYING)['alarm'];r.finish('long_gap_breaks_confirmation_and_descent_evidence')
    r=Run();r.arm();assert not r.step(2500,LYING)['alarm'];assert not r.step(2800,LYING)['alarm'];r.finish('stale_reference_not_reused')
    r=Run();r.arm()
    for t in range(1120,5041,280):assert not r.step(t,LYING,4000)['alarm']
    r.finish('low_confidence_not_a_fall')
    r=Run();r.arm();r.step(1120,LYING);assert r.step(1400,LYING)['alarm']
    for t in (1680,1960,2240,2520):assert r.step(t)['alarm']
    for t in (2800,3080,3360,3640):a=r.step(t)
    assert not a['alarm'] and any(x['recovered'] for x in r.rows)
    r.finish('standing_recovery_hysteresis')
    r=Run();r.arm();r.step(1120,LYING);r.step(1400,LYING);assert r.step(2000,None)['alarm'];assert not r.step(4600,None)['alarm'];r.finish('lost_target_alarm_timeout')
    r=Run();r.arm();r.step(1120,LYING);r.step(1400,LYING);r.call('fall_reset');assert not r.step(1680,LYING)['alarm'];r.finish('manual_reset')
    r=Run(offset=0xfffffc00);r.arm();r.step(1120,LYING);assert r.step(1400,LYING)['event'];r.finish('millisecond_wrap')
    r=Run();r.arm();r.step(1120,LYING);assert not r.step(1120,LYING)['alarm'];r.finish('duplicate_timestamp_cannot_confirm')
    r=Run();r.step(0);r.step(280,None);assert not r.step(560)['armed'];assert not r.step(840)['armed'];assert r.step(1120)['armed'];r.finish('missing_frame_breaks_initial_arming')
    r=Run();r.step(0);r.step(280,LYING);assert not r.step(560)['armed'];assert not r.step(840)['armed'];assert r.step(1120)['armed'];r.finish('nonupright_frame_breaks_initial_arming')
    r=Run();r.arm()
    for t in (1120,1400,1680):assert not r.step(t,(0,0,2000,900))['alarm']
    r.finish('invalid_coordinates_cannot_alarm')
    r=Run();r.arm()
    for i,t in enumerate(range(1040,3641,200)):
        a=min(i+1,12);box=tuple((s*(12-a)+l*a)//12 for s,l in zip(STAND,LYING))
        assert not r.step(t,box)['alarm']
    r.finish('gradual_recline_is_not_a_rapid_fall')
    r=Run();r.arm();r.step(1120,(500,330,720,650))
    for t in (1400,1680,1960,2240,2520,2800):assert not r.step(t,(500,330,720,650))['alarm']
    for t in (3080,3360,3640):assert not r.step(t,LYING,0,True)['alarm']
    r.finish('settled_seated_pose_then_recline_has_no_recent_drop')
    r=Run();r.arm();r.step(1120,LYING,0,True);assert r.step(1400,LYING,0,True)['alarm']
    for t in range(1680,61681,280):assert r.step(t,LYING,0,True)['alarm']
    r.finish('witnessed_pixel_supported_fall_remains_alarm_while_motionless')
    # New positive cases describe specific weaknesses of the old conjunction.
    r=Run();r.arm();oblique=(440,330,840,650)
    assert r.step(1120,oblique)['state']==2
    assert r.step(1400,oblique)['event'];r.finish('oblique_fall_with_moderate_descent')
    r=Run();r.arm();compact=(510,430,690,650)
    assert r.step(1120,compact)['state']==2
    assert r.step(1400,compact)['event'];r.finish('foreshortened_forward_or_backward_collapse')
    r=Run();r.arm()
    for t,b in [(1040,(500,200,700,650)),(1240,(480,250,720,650)),(1440,(460,300,760,650)),(1640,(440,350,800,650)),(1840,(430,400,830,650)),(2040,LYING)]:a=r.step(t,b)
    assert a['alarm'];r.finish('one_second_progressive_collapse')
    r=Run();edge=(520,220,680,720)
    for t in (0,280,560,840):r.step(t,edge,9000)
    assert r.rows[-1]['armed']
    r.step(1120,(430,520,830,720));assert r.step(1400,(430,520,830,720))['event']
    r.finish('upright_touching_bottom_edge_can_arm')
    r=Run();r.arm()
    for t in (1120,1400,1680,1960,2240):r.step(t,STAND,0,True)
    r.step(2520,LYING,0,True);assert r.step(2800,LYING,0,True)['event']
    r.finish('current_pixels_bridge_short_yolo_dropout_before_collapse')
    r=Run();r.arm()
    for t in (1120,1400,1680,1960):assert not r.step(t,(450,120,850,630))['alarm']
    r.finish('wide_localization_without_downward_compression_is_not_a_fall')
    r=Run();r.arm()
    for t in (1120,1400,1680,1960):assert not r.step(t,(520,390,680,650))['alarm']
    r.finish('narrow_crouch_above_compact_posture_threshold')
    r=Run();r.arm();fragment=(520,500,680,650)
    for t in (1120,1400,1680,1960):assert not r.step(t,fragment,0,True)['alarm']
    r.finish('narrow_pixel_fragment_cannot_imply_full_body_collapse')
    r=Run()
    for t in (0,280,560,840):assert not r.step(t,STAND,0,True)['armed']
    for t in (1120,1400,1680):assert not r.step(t,LYING,0,True)['alarm']
    r.finish('pixel_continuation_alone_cannot_establish_upright_identity')
    r=Run();r.arm()
    for t,b in [(1040,(500,190,700,650)),(1240,(480,230,720,650)),(1440,(450,270,750,650)),(1640,(430,310,830,650)),(1840,(430,350,830,650)),(2040,(430,390,830,650))]:a=r.step(t,b,0,True)
    assert a['alarm'];r.finish('progressive_pixel_supported_fall_beyond_old_velocity_window')
    r=Run();r.arm();seated=(500,330,720,650)
    for t in (1040,1240,1440,1640,1840,2040,2120):assert not r.step(t,seated)['alarm']
    for t in (2320,2520):assert not r.step(t,LYING,0,True)['alarm']
    r.finish('first_descent_deadline_is_not_renewed_by_later_low_posture')
    r=Run();r.arm();assert r.step(1120,LYING)['state']==2
    assert not r.step(1320,(440,250,840,650))['alarm']
    assert r.step(1520,LYING)['event'];r.finish('one_ambiguous_localization_does_not_erase_witnessed_fall')
    r=Run();r.arm();r.step(1120,LYING)
    for t in (1320,1520,1720):assert not r.step(t,(440,250,840,650))['alarm']
    assert not r.step(1920,LYING)['alarm'];r.finish('ambiguous_localizations_alone_cannot_confirm_or_bridge_long_gap')
    r=Run();r.arm();r.step(1120,LYING,0,True)
    assert not r.step(1320,(440,250,840,650),0,True)['alarm']
    assert not r.step(1520,LYING,0,True)['alarm'];r.finish('ambiguous_pixel_fragment_does_not_receive_yolo_grace')
    r=Run();raw=bytearray([0]*55296);r.uc.mem_write(symbols['motion_input'],bytes(raw));r.call('motion_capture')
    def region(args):
        r.uc.mem_write(symbols['motion_args'],struct.pack('<4i',*args));r.call('motion_region')
        return struct.unpack('<5i',r.uc.mem_read(symbols['motion_output'],20))
    assert region((0,0,1280,720))[-1]==0
    # A known right-half intensity change, with padding deliberately changing too.
    for y in range(96):
        for x in range(192):
            if x>=96:raw[(y*192+x)*3:(y*192+x)*3+3]=b'\x40\x40\x40'
    r.uc.mem_write(symbols['motion_input'],bytes(raw));r.call('motion_capture')
    a=region((0,0,1280,720));assert a[0]==460800 and a[1]==32 and 950<=a[2]<=970 and a[3]==359 and a[4]==1,a
    assert region((0,0,600,720))[:2]==(0,0)
    r.call('motion_capture');assert region((0,0,1280,720))[:2]==(0,0)
    r.finish('sampled_frame_difference_and_centroid')
    report.update(complete=True,passed=True);save();print(result_path)

if __name__=='__main__':main()
