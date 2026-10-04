"""Restore a frozen sensor/video run with full DDR verification. Never write Flash."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess,time,winreg
import serial,serial.tools.list_ports
root=Path(__file__).resolve().parents[2]
project=root/'fusion/ti60_multimodal'
source=project/'validation/run_20261004_161512'
snapshot=source/'snapshot'
verified=json.loads((snapshot/'build_verified.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in verified['sources_sha256'].items():
 assert sha(snapshot/name)==digest,name
bit=snapshot/'Ti60_Multimodal.bit';binary=source/'firmware.bin'
assert sha(bit)==verified['bitstream_sha256'] and sha(binary)==verified['firmware_sha256']
dest=project/'validation'/('restore_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
dest.mkdir()
for name in ['v4_jtag.cfg','cpu0.yaml','firmware.bin','firmware.elf']:
 shutil.copy2(source/name,dest/name)
shutil.copy2(Path(__file__),dest/'restore_sensor_run.py')
shutil.copy2(bit,dest/bit.name)
ports=list(serial.tools.list_ports.comports())
live={p.device for p in ports if (p.vid,p.pid)==(0x403,0x6011)}
matches=[]
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Enum\FTDIBUS') as bus:
 for i in range(winreg.QueryInfoKey(bus)[0]):
  instance=winreg.EnumKey(bus,i)
  if not instance.startswith('VID_0403+PID_6011+') or not instance.endswith('&3'):continue
  try:
   with winreg.OpenKey(bus,instance+r'\0000\Device Parameters') as key:
    port=winreg.QueryValueEx(key,'PortName')[0]
   if port in live:matches.append(port)
  except FileNotFoundError:pass
assert len(matches)==1,matches
env=os.environ.copy();env['PROCESSOR_ARCHITECTURE']='AMD64'
programmer='C:/Efinity/2026.1/pgm/bin/ftdi_pgm.bat'
r=subprocess.run([programmer,'-l'],capture_output=True,env=env,timeout=30)
(dest/'usb_inventory.log').write_bytes(r.stdout+r.stderr)
urls=set(re.findall(r'ftdi://0x0403:0x6011:\d+:\d+/2',r.stdout.decode(errors='replace')))
assert r.returncode==0 and len(urls)==1,urls
result={'restored_from':str(source.relative_to(root)),'bitstream_sha256':sha(bit),
 'firmware_sha256':sha(binary),'flash_written':False,'capture_completed':False,'runtime_checks_passed':False}
def save():(dest/'run_result.json').write_text(json.dumps(result,indent=2))
save();print('RESTORE:',dest,flush=True)
r=subprocess.run([programmer,'-m','jtag','-u',next(iter(urls)),'-b','Generic Board Profile Using FT4232H',
 '--jtag_clock_freq','1000000','Ti60_Multimodal.bit'],cwd=dest,env=env,capture_output=True,timeout=60)
log=r.stdout+r.stderr;(dest/'program_jtag.log').write_bytes(log)
assert r.returncode==0 and b'0x10660A79' in log and b'finished with JTAG programming' in log
def ocd(name,commands):
 args=['C:/Efinity/efinity-riscv-ide-2026.1/openocd/bin/openocd.exe','-f','v4_jtag.cfg']
 for command in commands:args.extend(['-c',command])
 r=subprocess.run(args,cwd=dest,capture_output=True,timeout=300)
 (dest/name).write_bytes(r.stdout+r.stderr);assert r.returncode==0
ocd('load.log',['init','halt','soft_reset_halt','load_image firmware.bin 0x1000 bin',
 f'dump_image ddr_readback.bin 0x1000 {binary.stat().st_size}','shutdown'])
assert (dest/'ddr_readback.bin').read_bytes()==binary.read_bytes()
result['full_binary_readback_verified']=True;save()
raw=bytearray()
try:
 with serial.Serial(matches[0],115200,timeout=.15,rtscts=False,dsrdtr=False) as uart:
  uart.reset_input_buffer()
  ocd('start.log',['init','halt','soft_reset_halt','resume 0x1000','shutdown'])
  print('Verified previous firmware loaded; observing 120 seconds.',flush=True)
  start=time.monotonic();last_report=start
  with (dest/'uart_raw.bin').open('wb') as output:
   while time.monotonic()-start<120:
    chunk=uart.read(max(1,uart.in_waiting));raw.extend(chunk);output.write(chunk);output.flush()
    if time.monotonic()-last_report>=10:
     lines=raw.decode('ascii',errors='replace').splitlines()
     print('\n'.join([x for x in lines if x.startswith(('CAM ','IR ','FATAL '))][-2:]) or 'No UART data yet.',flush=True)
     last_report=time.monotonic()
  result['capture_completed']=True
except serial.SerialException as exc:result['capture_error']=str(exc)
text=raw.decode('ascii',errors='replace');(dest/'uart.log').write_text(text)
def records(prefix):
 return [dict(re.findall(r'(\w+)=(\S+)',line)) for line in text.splitlines() if line.startswith(prefix)]
ir=records('IR ');cam=records('CAM ');sht=records('SHT ')
errors=[r for r in records('IR_STATUS ') if r['status'] not in ('0','8')]
sht_ok=all(int(r['seq'])==int(r['seq_hex'],16)==int(r['seq_check'],16) for r in sht)
result.update(boot_seen='FUSION_BOOT stage=2' in text,ir_records=len(ir),camera_records=len(cam),
 sht_records=len(sht),ir_errors=errors,ir_retries=len(records('IR_RETRY ')),sht_decimal_hex_agree=sht_ok,
 fatal_seen='FATAL ' in text)
result['runtime_checks_passed']=result['capture_completed'] and result['boot_seen'] and len(ir)>100 and len(cam)>100 and len(sht)>100 and not errors and not result['ir_retries'] and sht_ok and not result['fatal_seen']
save();print(json.dumps(result,indent=2),flush=True)
