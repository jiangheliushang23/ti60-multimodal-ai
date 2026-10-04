"""Observe the already-running board without JTAG, reset, or serial writes."""
from pathlib import Path
import datetime,hashlib,json,re,time,winreg
import serial,serial.tools.list_ports
root=Path(__file__).resolve().parents[2]
validation=root/'fusion/ti60_multimodal/validation'
reference=validation/'restore_20261004_162900'
dest=validation/('observe_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));dest.mkdir()
live={p.device for p in serial.tools.list_ports.comports() if (p.vid,p.pid)==(0x403,0x6011)}
matches=[]
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Enum\FTDIBUS') as bus:
 for i in range(winreg.QueryInfoKey(bus)[0]):
  instance=winreg.EnumKey(bus,i)
  if not instance.startswith('VID_0403+PID_6011+') or not instance.endswith('&3'):continue
  try:
   with winreg.OpenKey(bus,instance+r'\0000\Device Parameters') as key:port=winreg.QueryValueEx(key,'PortName')[0]
   if port in live:matches.append(port)
  except FileNotFoundError:pass
assert len(matches)==1,matches
prior=json.loads((reference/'run_result.json').read_text())
result={'mode':'UART receive only; no JTAG, reset, programming or serial writes',
 'expected_running_image_from':str(reference.relative_to(root)),
 'expected_firmware_sha256':prior['firmware_sha256'],'port':matches[0],
 'requested_seconds':1800,'capture_completed':False,'passed':False}
def save():(dest/'run_result.json').write_text(json.dumps(result,indent=2))
(dest/'observe_running_sensors.py').write_bytes(Path(__file__).read_bytes())
save();print('OBSERVE:',dest,flush=True)
raw=bytearray();start=time.monotonic();last_report=start
try:
 with serial.Serial(matches[0],115200,timeout=.2,rtscts=False,dsrdtr=False) as uart:
  with (dest/'uart_raw.bin').open('wb') as output:
   while time.monotonic()-start<1800:
    chunk=uart.read(max(1,uart.in_waiting));raw.extend(chunk);output.write(chunk);output.flush()
    if time.monotonic()-last_report>=60:
     lines=raw.decode('ascii',errors='replace').splitlines()
     cam=[l for l in lines if l.startswith('CAM ')]
     ir=[l for l in lines if l.startswith('IR ')]
     print(f'OBSERVED {time.monotonic()-start:.0f}s CAM={len(cam)} IR={len(ir)}',flush=True)
     last_report=time.monotonic()
 result['capture_completed']=True
except (serial.SerialException,KeyboardInterrupt) as exc:result['capture_error']=str(exc) or 'Interrupted'
result['elapsed_seconds']=round(time.monotonic()-start,2)
text=raw.decode('ascii',errors='replace');(dest/'uart.log').write_text(text)
def rows(prefix):return [dict(re.findall(r'(\w+)=(\S+)',l)) for l in text.splitlines() if l.startswith(prefix)]
cam=rows('CAM ');ir=rows('IR ');sht=rows('SHT ');service=rows('IR_SERVICE ')
result.update(camera_records=len(cam),ir_records=len(ir),sht_records=len(sht),
 ir_retries=rows('IR_RETRY '),ir_errors=[r for r in rows('IR_STATUS ') if r['status'] not in ('0','8')],
 unexpected_initializations=text.count('IR_INIT '),fatal_seen='FATAL ' in text,
 sht_mismatches=[r for r in sht if int(r['seq'])!=int(r['seq_hex'],16) or int(r['seq_hex'],16)!=int(r['seq_check'],16)])
def contiguous(records,key,base=10):
 return len(records)>1 and all(int(b[key],base)==int(a[key],base)+1 for a,b in zip(records,records[1:]))
checks={'ir_contiguous':contiguous(ir,'seq'),'ir_subpages_alternate':all(a['page']!=b['page'] for a,b in zip(ir,ir[1:])),
 'sht_hex_contiguous':contiguous(sht,'seq_hex',16),'sht_decimal_contiguous':contiguous(sht,'seq'),
 'sht_decimal_hex_agree':not result['sht_mismatches']}
result['sequence_checks']=checks
if len(cam)>1:
 first,last=cam[0],cam[-1];seconds=(int(last['ms'])-int(first['ms']))/1000
 result['video_measurements']={'camera_fps':(int(last['good'])-int(first['good']))/seconds,
 'published_fps':(int(last['published'])-int(first['published']))/seconds,
 'counter_deltas':{k:int(last[k])-int(first[k]) for k in ['bad','overflow','dropped','werr','rerr','underflow']}}
 result['camera_passed']=29.5<=result['video_measurements']['camera_fps']<=30.5 and all(v==0 for v in result['video_measurements']['counter_deltas'].values())
if service:
 result['scheduler_measurements']={key:max(int(r[key]) for r in service) for key in ['max_slice_ms','max_step_ms','max_init_ms']}
if sht:result['max_sht_age_ms']=max(int(r['age_ms']) for r in sht)
result['passed']=result['capture_completed'] and result.get('camera_passed',False) and all(checks.values()) and len(ir)>6000 and len(sht)>1700 and not result['ir_errors'] and not result['ir_retries'] and not result['unexpected_initializations'] and not result['fatal_seen']
save();print(json.dumps(result,indent=2),flush=True)
