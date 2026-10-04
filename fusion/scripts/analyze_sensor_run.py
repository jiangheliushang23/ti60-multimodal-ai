"""Summarize recorded real-board sensor data without accessing hardware."""
from pathlib import Path
import argparse,json,statistics
p=argparse.ArgumentParser();p.add_argument('run');args=p.parse_args()
run=Path(args.run);result=json.loads((run/'run_result.json').read_text())
ir=result['ir_records'];sht=result['sht_records'];assert ir and sht
summary={'ir_records':len(ir),'sht_records':len(sht),'hardware_measurements':True,
 'nack_retries':len(result.get('retry_records',[])),
 'ir_errors':[r for r in result['status_records'] if r['status'] not in ('0','8')],
 'ir_initializations':result.get('ir_initializations'),
 'scope':('Stage-2 Sapphire firmware and camera/DDR/HDMI hardware; camera success is reported separately. No AI inference. Millisecond resolution.'
          if result.get('stage')==2 else 'Sensor-only Sapphire firmware; no concurrent inference or camera. Millisecond resolution.')}
if result.get('stage')==2:
 summary['video_measurements']=result.get('video_measurements')
 summary['camera_stage_passed']=result.get('camera_stage_passed',False)
for field in ['read_ms','calc_ms','update_ms']:
 values=[int(x[field]) for x in ir if int(x[field])>0]
 summary[field]={'min':min(values),'median':statistics.median(values),'max':max(values)}
summary['ir_sequence_contiguous']=all(int(b['seq'])==int(a['seq'])+1 for a,b in zip(ir,ir[1:]))
summary['ir_alternates_subpages']=all(a['page']!=b['page'] for a,b in zip(ir,ir[1:]))
summary['sht_sequence_contiguous']=all(int(b['seq'])==int(a['seq'])+1 for a,b in zip(sht,sht[1:]))
summary['sht_all_valid']=all(x['status']=='1' for x in sht)
summary['display_ack_verified']=result['display_ack_verified']
summary['observed_subpages_per_second']=1000*(len(ir)-1)/(int(ir[-1]['publish_ms'])-int(ir[0]['publish_ms']))
summary['estimated_complete_pairs_per_second']=summary['observed_subpages_per_second']/2
summary['sht_intervals_ms']=[int(b['sample_ms'])-int(a['sample_ms']) for a,b in zip(sht,sht[1:])]
summary['sensor_validation_passed']=all(summary[k] for k in ['ir_sequence_contiguous','ir_alternates_subpages','sht_sequence_contiguous','sht_all_valid','display_ack_verified']) and not summary['ir_errors'] and summary['ir_initializations']==1
(run/'measurement_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='sht_intervals_ms'},indent=2))
raise SystemExit(0 if summary['sensor_validation_passed'] else 2)
