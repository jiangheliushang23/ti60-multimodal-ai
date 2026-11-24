"""Execute production alignment, power and camera-rate code as RV32, no board."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.path.insert(0,str(Path.home()/'.codex/tmp/tinyml_debug_python_20261007'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32
from unicorn.riscv_const import UC_RISCV_REG_SP,UC_RISCV_REG_RA,UC_RISCV_REG_GP,UC_RISCV_REG_PC,UC_RISCV_REG_A0
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/power_sync'
def main():
 OUT.mkdir(parents=True,exist_ok=True);elf=OUT/'power_sync_test.elf'
 cases=('alignment','power','thermal_wake','scene','motion','rate','service','pair')
 cmd=['D:/Efinity/toolchain/bin/riscv-none-elf-g++.exe','-march=rv32im','-mabi=ilp32','-std=c++11','-O2',
  '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-msmall-data-limit=0','-nostdlib',
  '-ffunction-sections','-fdata-sections','-I'+str(SW/'sensor_src'),'-I'+str(SW/'src'),'-I'+str(SW/'replay_src'),
  str(Path(__file__).with_name('power_sync_test.cc')),'-Wl,-Ttext=0x1000,-e,test_alignment,--gc-sections',
  *['-Wl,--undefined=test_'+n for n in cases],'-lc','-lgcc','-o',str(elf)]
 r=subprocess.run(cmd,capture_output=True,text=True);(OUT/'compile.log').write_text(r.stdout+r.stderr)
 assert r.returncode==0,r.stderr
 with elf.open('rb') as f:
  e=ELFFile(f);segments=[(p['p_vaddr'],p.data()) for p in e.iter_segments() if p['p_type']=='PT_LOAD']
  symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
 report=dict(complete=False,passed=False,board_accessed=False,cases={},inputs_sha256={})
 dest=OUT/'result.json';save=lambda:dest.write_text(json.dumps(report,indent=2),encoding='utf8');save()
 for case in cases:
  uc=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);uc.mem_map(0,0x1000000);uc.mem_map(0xf8100000,0x10000)
  for address,data in segments:uc.mem_write(address,data)
  uc.reg_write(UC_RISCV_REG_SP,0xf00000);uc.reg_write(UC_RISCV_REG_RA,0)
  uc.reg_write(UC_RISCV_REG_GP,symbols.get('__global_pointer$',0))
  uc.emu_start(symbols['test_'+case],0,count=20000000)
  assert uc.reg_read(UC_RISCV_REG_PC)==0,'instruction budget exceeded '+case
  assert uc.reg_read(UC_RISCV_REG_A0)==0,case+' failed at C++ line '+str(uc.reg_read(UC_RISCV_REG_A0))
  checks=struct.unpack('<I',uc.mem_read(symbols['checks'],4))[0]
  report['cases'][case]=dict(passed=True,assertions=checks);save();print('PASS RV32',case,checks,flush=True)
 # Integration audit: production services execute before the sleep gate, which
 # always continues before tensor capture and Invoke. No test-only sleep path.
 main=(SW/'replay_src/main.cc').read_text()
 loop=main.split('POWER_READY',1)[1].split('for(;;)',1)[1]
 gate=loop.index('if(!power.inference_allowed())')
 assert loop.index('camera_auto_service::service();')<gate and loop.index('multimodal_sensors::service();')<gate
 assert gate<loop.index('capture_monitor')<loop.index('continue;',gate)<loop.index('capture_views')<loop.index('invoke(interpreter')
 assert 'power.observe(frame.started_ms,any_present,people.any_alarm)' in main
 assert 'multimodal_sensors::observe_visual_presence(frame.started_ms,any_present||people.any_alarm)' in main
 assert 'const auto primary=person_roi::full();' in main and 'frame_people.add(primary,boxes,box_count)' in main
 assert 'frame_people.second(selected,fresh)' in main and 'cam::overlay_metadata(++sequence,r,r2,first_flags,second_flags)' in main
 assert 'wake_motion.update' not in main and 'reason=thermal_region' in main
 assert 'set_low_power_monitor(power.mode==scene_power::Sleep)' in main
 assert 'cam::hdmi[0x1094/4]=scene_power::display_status(power.mode,camera_fps_x10,camera_fps_valid)' in main
 assert 'power.tick(power_now)' in main and 'multimodal_sensors::reject_thermal_candidate(power_now)' in main
 port=(SW/'src/port.cc').read_text();assert '0xf8103014' in port.lower()
 files=[Path(__file__),Path(__file__).with_name('power_sync_test.cc'),SW/'replay_src/main.cc',SW/'replay_src/person_pair.h',SW/'src/port.cc',
  *[SW/'sensor_src'/n for n in ('multimodal_alignment.h','scene_power.h','thermal_wake.h','camera_rate.h','camera_auto_service.h','camera_auto.h','camera_control.h')]]
 report.update(complete=True,passed=True,assertions=sum(c['assertions'] for c in report['cases'].values()),
  inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 save();print(dest)
if __name__=='__main__':main()
