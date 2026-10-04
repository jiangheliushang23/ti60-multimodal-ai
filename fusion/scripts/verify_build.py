"""Check current source fingerprints, pin assignments, tests and constrained timing."""
from pathlib import Path
import csv,io,json,re,hashlib
root=Path(__file__).resolve().parents[2];fusion=root/'fusion';project=fusion/'ti60_multimodal'
out=project/'outflow';evidence=project/'validation';name='Ti60_Multimodal'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pins(p):
 t=p.read_text(encoding='utf-8');return {r['Pin Number']:r for r in csv.DictReader(io.StringIO(t[t.index('Pin Number,'):]))}
new=pins(out/(name+'.pinout.csv'))
old=pins(root/'task2_ai/soc_hdmi/outflow/Ti60F225_tinyml_helloworld.pinout.csv')
sensor=pins(root/'sensors/ir_thermal_hdmi_v3_20260930/validation/IR_Thermal_HDMI.pinout.csv')
checks=[]
for ball,row in old.items():
 if not row['Signal Name'].startswith(('ddr_','verf','system_uart_','clk_25m','tmds_','CLK_27M')):continue
 for field in ['Signal Name','I/O Standard','I/O Bank Voltage']:assert new[ball][field]==row[field],(ball,field)
 checks.append(ball)
for ball,sig in [('C5','sht_scl'),('A4','sht_sda'),('B3','ir_scl'),('C3','ir_sda')]:
 assert new[ball]['Signal Name']==sig and new[ball]['I/O Standard']=='3.3 V LVCMOS'
 for field in ['Signal Name','I/O Standard','I/O Bank Voltage']:assert new[ball][field]==sensor[ball][field]
 checks.append(ball)
camera=pins(root/'camera/sc431hai_hdmi/outflow/ti60f225_oob.pinout.csv')
for ball,row in camera.items():
 if not row['Signal Name'].startswith(('cam_','io_cam_','o_cam_rst')):continue
 for field in ['Signal Name','I/O Standard','I/O Bank Voltage']:assert new[ball][field]==row[field],(ball,field)
 checks.append(ball)
assert all(new[b]['Signal Name']==sig for b,sig in [('D12','io_cam_scl'),('B14','io_cam_sda'),('C12','o_cam_rst_p')])
# Pin placement alone does not prove a correct module-level reset polarity.
reference=(root/'camera/sc431hai_hdmi/rtl/ti60f225_oob_top.v').read_text(encoding='utf-8')
adapted=(project/'src/fusion/fusion_camera.v').read_text(encoding='utf-8')
for source in [reference,adapted]:
 assert re.search(r'assign\s+o_cam_rst_p\s*=\s*~cam_enable\s*;',source)
 assert re.search(r'\.cam_enable\(cam_enable\)',source)
place=(out/(name+'.place.rpt')).read_text()
if 'IO Placement Summary (begin)' in place:
 io_section=place.split('IO Placement Summary (begin)')[1].split('IO Placement Summary (end)')[0]
 assert not re.search(r'\b(?:sht_|ir_)',io_section),'Unassigned sensor pins'
 assert not re.search(r'\b(?:cam_|io_cam_|o_cam_)',io_section),'Unassigned camera pins'
timing=(out/(name+'.timing.rpt')).read_text()
summary=timing.split('Clock Relationship Summary (begin)')[1].split('Clock Relationship Summary (end)')[0]
rows=[];kind=None
for line in summary.splitlines():
 if 'Setup (Max)' in line:kind='setup'
 if 'Hold (Min)' in line:kind='hold'
 m=re.match(r'(\S+)\s+(\S+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\([RF]-[RF]\))',line)
 if m:rows.append({'kind':kind,'launch':m[1],'capture':m[2],'slack_ns':float(m[4])})
assert len(rows)>=20 and all(r['slack_ns']>=0 for r in rows),rows
resources={}
for label in ['XLRs','Memory Blocks','DSP Blocks']:
 m=re.search(re.escape(label)+r':\s+(\d+)\s+/\s+(\d+)',place)
 if m:resources[label]={'used':int(m[1]),'total':int(m[2])}
tests=json.loads((evidence/'rtl_tests.json').read_text())
assert len(tests)==4 and all(t['passed'] for t in tests)
for test in tests:
 for path,digest in test['sources'].items():assert sha(root/path)==digest,path
video_tests=['camera_line_bridge_tb','camera_rgb_pack_tb','video_ddr_tb','fusion_page_tb']
for test_name in video_tests:
 test=json.loads((evidence/(test_name+'.json')).read_text());assert test['passed'],test_name
 for path,digest in test['sources'].items():assert sha(root/path)==digest,path
isp=json.loads((evidence/'camera_reuse_tests.json').read_text());assert isp['passed']
for path,digest in isp['sources'].items():assert sha(root/path)==digest,path
cases=['normal','cold','hot','timer_wrap','steady','nack','transient_nack','overrun','bus_timeout','no_new_data','bad_eeprom','bad_math','wrong_id','delayed_bus','delayed_display','display_timeout','recover_nack','recover_timeout','recover_no_data']
fw=fusion/'demo_multimodal/software/standalone/tinyml_pdti8/build/tinyml_pdti8.bin'
for case in cases:
 test=json.loads((evidence/f'firmware_emulator_{case}.json').read_text())
 assert test['passed'] and test['firmware_sha256']==sha(fw),case
 assert test['test_source_sha256']==sha(fusion/'tests/firmware_emulator.py'),case
assert json.loads((fusion/'demo_multimodal/build_result.json').read_text())['exit_code']==0
sources={}
for base in [project/'src',project/'ip',project/'sdc',fusion/'demo_multimodal/bsp',fusion/'demo_multimodal/software/standalone/common']:
 for p in base.rglob('*'):
  if p.is_file() and p.suffix in ('.v','.sv','.vh','.f','.json','.mem','.hex','.xml','.sdc','.c','.cc','.h','.cpp','.S','.ld','.mk'):
   sources[p.relative_to(root).as_posix()]=sha(p)
sw=fusion/'demo_multimodal/software/standalone/tinyml_pdti8'
for p in [project/(name+'.xml'),project/(name+'.peri.xml'),sw/'makefile',*[(sw/'src'/n) for n in ['main.cc','MLX90640_API.cpp','MLX90640_API.h','MLX90640_I2C_Driver.h','thermal_display.h']]]:
 sources[p.relative_to(root).as_posix()]=sha(p)
for p in (sw/'src/model').glob('*'):
 assert not any(x in p.name for x in ['person_image','people1','people2']),p
assert 'person_image' not in (sw/'src/main.cc').read_text()
warnings=[l for l in (out/(name+'.route.out')).read_text().splitlines() if 'WARNING' in l]
result={'stage':2,'pin_checks':len(checks),'sensor_pins':{'sht_scl':'C5','sht_sda':'A4','ir_scl':'B3','ir_sda':'C3'},
 'setup_min_ns':min(r['slack_ns'] for r in rows if r['kind']=='setup'),
 'hold_min_ns':min(r['slack_ns'] for r in rows if r['kind']=='hold'),'timing_rows':rows,'resources':resources,
 'rtl_tests':4,'video_tests':video_tests,'camera_reuse_tests':isp['cases'],'firmware_cases':cases,'sources_sha256':sources,
 'bitstream_sha256':sha(out/(name+'.bit')),'firmware_sha256':sha(fw),'firmware_bytes':fw.stat().st_size,
 'warnings':warnings,'hardware_access':False,
 'limitations':['Constrained timing only; inherited clock-domain exclusions and protected vendor loops remain.',
 'Stage 2 camera and sensor display; no live AI inference. Preprocessing/alignment and alarms remain incomplete.',
 'RTL and ISA simulations do not certify the physical HDMI screen or sensor performance.']}
# This bitstream predates the module split in the current workspace. Keep
# the frozen source provenance distinct from a fresh hash of unbuilt sources.
known_build=evidence/'run_20261003_224853/snapshot/build_verified.json'
if known_build.is_file():
 frozen=json.loads(known_build.read_text())
 if result['bitstream_sha256']==frozen['bitstream_sha256']:
  prefix='fusion/ti60_multimodal/'
  built={k:v for k,v in frozen['sources_sha256'].items() if k.startswith(prefix)}
  present={k:v for k,v in sources.items() if k.startswith(prefix)}
  differences=sorted(k for k in set(built)|set(present) if built.get(k)!=present.get(k))
  result['hardware_source_matches_bitstream']=not differences
  result['hardware_source_reference']=known_build.relative_to(root).as_posix()
  result['hardware_source_differences']=differences
  result['bitstream_hardware_sources_sha256']=built
  if differences:
   result['limitations'].append('Current hardware source has unbuilt edits; only the frozen bitstream has the reported timing and board evidence.')
(evidence/'build_verified.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ['sources_sha256','bitstream_hardware_sources_sha256','timing_rows','warnings']},indent=2))

if result.get('hardware_source_matches_bitstream') is False:
 raise SystemExit('Hardware source differs from the frozen build. Preserve edits and rebuild/validate before loading current sources; firmware-only ISA checks passed.')
