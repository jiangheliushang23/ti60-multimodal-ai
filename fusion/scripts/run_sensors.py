"""Temporary JTAG configuration, full DDR readback and real sensor capture. No Flash."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,subprocess,time,winreg
import serial,serial.tools.list_ports
parser=argparse.ArgumentParser();parser.add_argument('--capture-seconds',type=int,default=45)
capture_seconds=parser.parse_args().capture_seconds
assert 10<=capture_seconds<=1800
root=Path(__file__).resolve().parents[2];project=root/'fusion/ti60_multimodal'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
verified=json.loads((project/'validation/build_verified.json').read_text())
assert verified.get('hardware_source_matches_bitstream') is not False, 'Current hardware source is not built; see hardware_source_differences. Do not load it as a verified current build.'
for path,digest in verified['sources_sha256'].items():assert sha(root/path)==digest,path
bit=project/'outflow/Ti60_Multimodal.bit'
binary=root/'fusion/demo_multimodal/software/standalone/tinyml_pdti8/build/tinyml_pdti8.bin'
assert sha(bit)==verified['bitstream_sha256'] and sha(binary)==verified['firmware_sha256']
dest=project/'validation'/('run_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));dest.mkdir()
ports=list(serial.tools.list_ports.comports())
live={p.device for p in ports if (p.vid,p.pid)==(0x403,0x6011)}
inventory=[{'port':p.device,'vid':p.vid,'pid':p.pid,'serial':p.serial_number,'location':p.location} for p in ports]
(dest/'serial_inventory.json').write_text(json.dumps(inventory,indent=2))
# Windows enumerates channel C as interface 3; intersect registry history with live ports.
matches=[]
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Enum\FTDIBUS') as bus:
 for i in range(winreg.QueryInfoKey(bus)[0]):
  instance=winreg.EnumKey(bus,i)
  if not instance.startswith('VID_0403+PID_6011+') or not instance.endswith('&3'):continue
  try:
   with winreg.OpenKey(bus,instance+r'\0000\Device Parameters') as key:port=winreg.QueryValueEx(key,'PortName')[0]
   if port in live:matches.append({'port':port,'registry_instance':instance})
  except FileNotFoundError:pass
assert len(matches)==1,('Ambiguous live FT4232 channel C',matches)
port_name=matches[0]['port'];(dest/'uart_selection.json').write_text(json.dumps(matches[0],indent=2))
programmer='C:/Efinity/2026.1/pgm/bin/ftdi_pgm.bat';env=os.environ.copy();env['PROCESSOR_ARCHITECTURE']='AMD64'
p=subprocess.run([programmer,'-l'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=30)
(dest/'usb_inventory.log').write_bytes(p.stdout)
urls=set(re.findall(r'ftdi://0x0403:0x6011:\d+:\d+/2',p.stdout.decode(errors='replace')))
assert p.returncode==0 and len(urls)==1,urls
url=next(iter(urls))
snapshot=dest/'snapshot';snapshot.mkdir()
for path in verified['sources_sha256']:
 target=snapshot/path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/path,target)
for source in [bit,project/'validation/build_verified.json',project/'validation/rtl_tests.json',project/'outflow/Ti60_Multimodal.timing.rpt',project/'outflow/Ti60_Multimodal.pinout.csv']:
 shutil.copy2(source,snapshot/source.name)
shutil.copy2(binary,dest/'firmware.bin')
shutil.copy2(binary.with_suffix('.elf'),dest/'firmware.elf')
for source in [*Path(__file__).parent.glob('*.py'),*Path(__file__).parent.glob('*.ps1')]:
 target=snapshot/'scripts'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
for source in project.joinpath('validation').glob('firmware_emulator_*'):
 target=snapshot/'tests'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
for source in project.joinpath('validation').glob('*_tb.log'):
 target=snapshot/'tests'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
for name in ['v4_jtag.cfg','cpu0.yaml']:shutil.copy2(root/'task2_ai/hdmi_20261002'/name,dest/name)
for source in project.joinpath('validation').glob('*_tb.json'):
 target=snapshot/'tests'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
for source in (root/'fusion/tests').glob('*'):
 if source.is_file() and source.suffix in ('.v','.py'):
  target=snapshot/'test_sources'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
for source in [project/'validation/camera_reuse_tests.json',project/'validation/spatial_result.json']:
 if source.exists():shutil.copy2(source,snapshot/source.name)
stage=verified['stage']
result={'stage':stage,'port':port_name,'jtag_url':url,'flash_written':False,'bitstream_sha256':sha(bit),
 'firmware_sha256':sha(binary),'firmware_bytes':binary.stat().st_size,'physical_screen_verified':False,
 'capture_requested_seconds':capture_seconds,'capture_completed':False,'stage_passed':False}
def save(): (dest/'run_result.json').write_text(json.dumps(result,indent=2))
save();print('EVIDENCE:',dest,flush=True)
p=subprocess.run([programmer,'-m','jtag','-u',url,'-b','Generic Board Profile Using FT4232H','--jtag_clock_freq','1000000','outflow/Ti60_Multimodal.bit'],cwd=project,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
(dest/'program_jtag.log').write_bytes(p.stdout);log=p.stdout.decode(errors='replace')
result['programmed']=p.returncode==0 and '0x10660A79' in log and 'finished with JTAG programming' in log
save();assert result['programmed'],log
print('JTAG ID/configuration verified. Loading Sapphire firmware...',flush=True)
openocd='C:/Efinity/efinity-riscv-ide-2026.1/openocd/bin/openocd.exe'
def ocd(log_name,instructions):
 args=[openocd,'-f','v4_jtag.cfg']
 for instruction in instructions:args.extend(['-c',instruction])
 with (dest/log_name).open('w') as f:r=subprocess.run(args,cwd=dest,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 assert r.returncode==0,log_name
ocd('openocd_load.log',['init','halt','soft_reset_halt','load_image firmware.bin 0x1000 bin',f'dump_image ddr_readback.bin 0x1000 {binary.stat().st_size}','shutdown'])
result['full_binary_readback_verified']=(dest/'ddr_readback.bin').read_bytes()==binary.read_bytes();save()
assert result['full_binary_readback_verified']
raw=bytearray();capture_error=None;start=None
try:
 with serial.Serial(port_name,115200,timeout=.15,rtscts=False,dsrdtr=False) as uart:
  uart.reset_input_buffer()
  ocd('openocd_run.log',['init','halt','soft_reset_halt','resume 0x1000','shutdown'])
  print(f'DDR bytes verified; CPU running. Capturing {capture_seconds} seconds...',flush=True)
  start=time.monotonic()
  with (dest/'uart_raw.bin').open('wb') as f:
   while time.monotonic()-start<capture_seconds:
    data=uart.read(max(1,uart.in_waiting));raw.extend(data);f.write(data);f.flush()
except serial.SerialException as exc:
 capture_error=str(exc)
result['capture_completed']=capture_error is None
if capture_error is not None:
 (dest/'uart.log').write_text(raw.decode('ascii',errors='replace'))
 result.update(capture_error=capture_error,capture_seconds=round(time.monotonic()-start,2) if start is not None else 0)
 save();raise SystemExit('Serial capture interrupted; this run is not a stability PASS: '+capture_error)
text=raw.decode('ascii',errors='replace');(dest/'uart.log').write_text(text)
boot=text.find(f'FUSION_BOOT stage={stage}');assert boot>=0,'Missing new firmware boot marker'
text=text[boot:];ir=[];sht=[];status=[];retries=[];camera=[];camera_registers=[];service=[]
for line in text.splitlines():
 values=dict(re.findall(r'(\w+)=(\S+)',line))
 if line.startswith('IR_SERVICE '):service.append(values)
 elif line.startswith('IR '):ir.append(values)
 elif line.startswith('SHT '):sht.append(values)
 elif line.startswith('IR_STATUS '):status.append(values)
 elif line.startswith('IR_RETRY '):retries.append(values)
 elif line.startswith('CAM '):camera.append(values)
 elif line.startswith('CAM_REGS '):camera_registers.append(values)
result.update(boot_seen=True,ir_init_verified='IR_INIT eeprom_double_read=OK calibration=OK' in text,
 ir_records=ir,sht_records=sht,status_records=status,retry_records=retries,fatal_seen='FATAL ' in text,
 display_ack_verified=bool(ir) and all(int(r['ack'],16)&5==4 for r in ir),capture_seconds=round(time.monotonic()-start,2))
print_checks=re.findall(r'PRINT_CHECK decimal=(-?\d+) hex=([0-9a-f]+)',text)
result['decimal_format_checks']={'count':len(print_checks),'passed':len(print_checks)==18 and all((int(a)&0xffffffff)==int(b,16) for a,b in print_checks)}
if print_checks:assert result['decimal_format_checks']['passed'],'Startup integer self-check failed'
result['ir_service_records']=service
if 'ir_service=1' in text.splitlines()[0]:
 result['ir_service_measurements']={
  'records':len(service),
  'max_slice_ms':max((int(r['max_slice_ms']) for r in service),default=0),
  'max_step_ms_excluding_eeprom':max((int(r['max_step_ms']) for r in service),default=0),
  'max_eeprom_extraction_ms':max((int(r['max_init_ms']) for r in service),default=0),
  'max_sht_log_age_ms':max((int(r['age_ms']) for r in sht),default=0)}
 result['ir_service_passed']=len(service)>=2 and all(int(r['max_slice_ms'])<=10 and int(r['max_step_ms'])<=25 for r in service)
result['camera_records']=camera
result['camera_registers']=camera_registers
result['ir_errors']=[r for r in status if r['status'] not in ('0','8')]
result['ir_initializations']=text.count('IR_INIT ')
result['sequence_checks']={
 'ir_contiguous':all(int(b['seq'])==int(a['seq'])+1 for a,b in zip(ir,ir[1:])),
 'ir_subpages_alternate':all(a['page']!=b['page'] for a,b in zip(ir,ir[1:])),
 'sht_contiguous':all(int(b['seq'])==int(a['seq'])+1 for a,b in zip(sht,sht[1:])),
 'sht_decimal_hex_agree':all(int(r['seq'])==int(r['seq_hex'],16)==int(r['seq_check'],16) for r in sht if 'seq_hex' in r)}
result['sensor_stage_passed']=len(ir)>=8 and len(sht)>=5 and result['ir_init_verified'] and result['display_ack_verified'] and not result['fatal_seen'] and all(r['status']=='1' for r in sht) and not result['ir_errors'] and result['ir_initializations']==1
result['sensor_stage_passed']=result['sensor_stage_passed'] and all(result['sequence_checks'].values())
if stage==2:
 steady=[c for c in camera if int(c['ms'])>=10000]
 result['camera_stage_passed']=False
 if len(steady)>=5:
  first,last=steady[0],steady[-1];dt=(int(last['ms'])-int(first['ms']))/1000
  camera_fps=(int(last['good'])-int(first['good']))/dt
  publish_fps=(int(last['published'])-int(first['published']))/dt
  errors={k:int(last[k])-int(first[k]) for k in ['bad','overflow','dropped','werr','rerr','underflow']}
  result['video_measurements']={'camera_fps':camera_fps,'published_fps':publish_fps,'counter_deltas':errors,
   'camera_period_ticks_50MHz':int(last['period_ticks']),'window_seconds':dt,'hdmi_refresh_hz':60}
  result['camera_stage_passed']=29.5<=camera_fps<=30.5 and publish_fps>=29.5 and all(v==0 for v in errors.values()) and all(int(c['setup'],16)&0xff==0x1f for c in steady)
result['stage_passed']=result['capture_completed'] and result['sensor_stage_passed'] and (stage==1 or result['camera_stage_passed']) and result.get('ir_service_passed',True)
save();print('\n'.join(text.splitlines()[:9]+text.splitlines()[-5:]))
print(json.dumps({k:v for k,v in result.items() if k not in ['ir_records','sht_records','status_records','retry_records','camera_records','ir_service_records']},indent=2),flush=True)
raise SystemExit(0 if result['stage_passed'] else 2)
