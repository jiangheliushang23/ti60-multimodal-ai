"""Check complete lines from a saved/passively growing UART capture; no board access."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, statistics

parser=argparse.ArgumentParser()
parser.add_argument('run')
args=parser.parse_args()
run=Path(args.run)
raw=(run/'uart_raw.bin').read_bytes()
parts=raw.split(b'\n')
tail=parts.pop()
lines=[line.decode('ascii',errors='replace').rstrip('\r') for line in parts]
required={
 'CAM': 'ms setup good bad period_ticks overflow published dropped werr rerr underflow seq pixels format de_runs packing',
 'IR': 'seq page min_centi max_centi center_centi ta_bcd read_ms calc_ms update_ms publish_ms display_seq ack',
 'SHT': 'seq status raw t_bcd h_bcd sample_ms age_ms seq_hex seq_check',
 'IR_SERVICE': 'steps max_step_ms max_slice_ms max_init_ms ms',
}
rows={key:[] for key in required}
malformed=[]
for number,line in enumerate(lines,1):
 tag=line.split(' ',1)[0]
 if tag not in required:continue
 fields=dict(re.findall(r'(\w+)=(\S+)',line))
 missing=set(required[tag].split())-fields.keys()
 if missing:
  malformed.append({'line':number,'missing':sorted(missing),'text':line});continue
 try:
  for key,value in fields.items():int(value,16 if key in ['setup','format','packing','raw','t_bcd','h_bcd','ta_bcd','ack','seq_hex','seq_check'] else 10)
 except ValueError:
  malformed.append({'line':number,'invalid_number':line});continue
 rows[tag].append(fields)
cam,ir,sht,service=[rows[k] for k in required]
def consecutive(records,key,base=10):
 return len(records)>1 and all(int(b[key],base)==int(a[key],base)+1 for a,b in zip(records,records[1:]))
def intervals(records,key):
 values=[int(b[key])-int(a[key]) for a,b in zip(records,records[1:])]
 return {'min':min(values),'median':statistics.median(values),'max':max(values)} if values else None
sht_mismatches=[r for r in sht if int(r['seq'])!=int(r['seq_hex'],16) or int(r['seq_hex'],16)!=int(r['seq_check'],16)]
errors=[line for line in lines if line.startswith(('IR_RETRY ','FATAL ','IR_INIT ','FUSION_BOOT ')) or (line.startswith('IR_STATUS ') and re.search(r'\bstatus=(\d+)',line) and re.search(r'\bstatus=(\d+)',line)[1] not in ['0','8'])]
counters=['bad','overflow','dropped','werr','rerr','underflow']
cam_intervals=intervals(cam,'ms');ir_intervals=intervals(ir,'publish_ms');sht_intervals=intervals(sht,'sample_ms')
video=None
if len(cam)>1:
 seconds=(int(cam[-1]['ms'])-int(cam[0]['ms']))/1000
 video={'seconds_between_records':seconds,'camera_fps':(int(cam[-1]['good'])-int(cam[0]['good']))/seconds if seconds>0 else None,'published_fps':(int(cam[-1]['published'])-int(cam[0]['published']))/seconds if seconds>0 else None,'all_reported_error_counters_zero':all(int(r[k])==0 for r in cam for k in counters),'all_samples_advance':all(int(b['good'])>int(a['good']) and int(b['published'])>int(a['published']) for a,b in zip(cam,cam[1:]))}
checks={
 'video_continues':bool(video and video['camera_fps'] and 29.5<=video['camera_fps']<=30.5 and video['all_reported_error_counters_zero'] and video['all_samples_advance'] and cam_intervals and 0<cam_intervals['min']<=cam_intervals['max']<=1100),
 'ir_contiguous':consecutive(ir,'seq'),
 'ir_subpages_alternate':len(ir)>1 and all(a['page']!=b['page'] for a,b in zip(ir,ir[1:])),
 'ir_updates_within_500ms':bool(ir_intervals and 0<ir_intervals['min']<=ir_intervals['max']<=500),
 'ir_display_acknowledged':bool(ir) and all(int(r['ack'],16) in [4,6] for r in ir),
 'sht_hex_contiguous':consecutive(sht,'seq_hex',16),
 'sht_valid':bool(sht) and all(r['status']=='1' for r in sht),
 'sht_age_in_range':bool(sht) and all(0<=int(r['age_ms'])<=20 for r in sht),
 'sht_intervals_in_range':bool(sht_intervals and 1000<=sht_intervals['min']<=sht_intervals['max']<=1500),
 'sht_decimal_contiguous':consecutive(sht,'seq'),
 'sht_decimal_hex_agree':bool(sht) and not sht_mismatches,
 'no_error_or_restart_records':not errors,
 'no_malformed_complete_lines':not malformed,
}
prior=json.loads((run/'run_result.json').read_text())
completed=prior.get('capture_completed',False) and prior.get('elapsed_seconds',0)>=1800
result={'checked_at':datetime.datetime.now().isoformat(),'hardware_access':False,'capture_completed_30min':completed,'uart_snapshot_sha256':hashlib.sha256(raw).hexdigest(),'uart_snapshot_bytes':len(raw),'ignored_unterminated_tail_bytes':len(tail),'record_counts':{k:len(r) for k,r in rows.items()},'checks':checks,'video':video,'camera_log_intervals_ms':cam_intervals,'ir_publish_intervals_ms':ir_intervals,'sht_sample_intervals_ms':sht_intervals,'sht_mismatches':sht_mismatches,'sht_status_or_age_anomalies':[r for r in sht if r['status']!='1' or not 0<=int(r['age_ms'])<=20],'errors_or_restarts':errors,'malformed_complete_lines':malformed,'max_sht_age_ms':max((int(r['age_ms']) for r in sht),default=None),'scheduler_max':{k:max((int(r[k]) for r in service),default=None) for k in ['max_slice_ms','max_step_ms','max_init_ms']},'all_checks_passed':completed and all(checks.values()),'scope':'Only complete UART lines are assessed. Data publication counters cannot replace observing movement on the HDMI display; no live AI is enabled.'}
if len(ir)>1:
 seconds=(int(ir[-1]['publish_ms'])-int(ir[0]['publish_ms']))/1000
 result['ir_published_subpages_per_second']=(len(ir)-1)/seconds if seconds>0 else None
(run/'complete_line_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
