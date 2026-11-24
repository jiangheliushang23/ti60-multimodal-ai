"""Check actual RV32 track telemetry, corruption rejection and PC presentation."""
from pathlib import Path
import copy,hashlib,json,subprocess,sys,threading
ROOT=Path(__file__).resolve().parents[3]
SW=ROOT/'fusion/demo_multimodal/software/standalone/tinyml_yolo_static'
OUT=ROOT/'fusion/ti60_yolo_auto/validation/two_track'
sys.path.insert(0,str(SW));sys.path.insert(0,str(ROOT/'delivery'))
from yolo_auto_download import identity_output_valid,behavior_output_valid
from two_person_track_viewer import TrackScene,read_live_lines

def main():
 result=json.loads((OUT/'result.json').read_text());assert result['passed']
 rows=result['cases']['two_moving_people_cross_and_change_detector_order']['rows']
 records=[];frames=[];points=[];boxes={};boxes2={};falls=[];lines=['YTRACK_READY algorithm=iou_motion_v1 capacity=2']
 for seq,row in enumerate(rows,1):
  ids=row['ids'];ms=row['ms']
  record=dict(seq=seq,drawn=row['visible']);records.append(record)
  frame=dict(seq=seq,source_seq=seq,ms=ms,visible=row['visible'],active=row['active'],primary_id=ids[0],secondary_id=ids[1],processing_ms=0)
  frames.append(frame);falls.append(dict(seq=seq,alarm=row['fall_alarm']))
  lines.append('YTRACK_FRAME '+' '.join(f'{k}={v}' for k,v in frame.items()))
  for i,b in enumerate((row['a'],row['b'])):
   identity=ids[i]
   if not identity:continue
   slot,t=next((i,t) for i,t in enumerate(row['tracks']) if t[0]==identity)
   p=dict(seq=seq,id=identity,lane=slot,ms=ms,cx=(b[0]+b[2])//2,cy=(b[1]+b[3])//2,
    x1=b[0],y1=b[1],x2=b[2],y2=b[3],vx=t[8] if t[8]<0x80000000 else t[8]-0x100000000,
    vy=t[9] if t[9]<0x80000000 else t[9]-0x100000000,history=t[6],primary=int(i==0),alarm=int(i==0 and row['fall_alarm']))
   points.append(p);(boxes if i==0 else boxes2)[seq]=dict(zip(('x1','y1','x2','y2'),b))
   lines.append('YTRACK_POINT '+' '.join(f'{k}={v}' for k,v in p.items()))
 assert identity_output_valid(records,frames,points,boxes,boxes2,falls)
 tests=['RV32-produced two-person crossing telemetry accepted']
 for change in ('duplicate_id','wrong_box','wrong_alarm','extra_frame','missing_point','wrong_count'):
  f,p=copy.deepcopy(frames),copy.deepcopy(points)
  if change=='duplicate_id':f[0]['secondary_id']=f[0]['primary_id']
  elif change=='wrong_box':p[0]['x1']+=1
  elif change=='wrong_alarm':p[1]['alarm']=1
  elif change=='extra_frame':p[0]['seq']=999
  elif change=='missing_point':p.pop()
  elif change=='wrong_count':f[0]['visible']=1
  assert not identity_output_valid(records,f,p,boxes,boxes2,falls),change
  tests.append('reject '+change)
 scene=TrackScene()
 for line in lines:scene.consume(line)
 ids=rows[0]['ids'];assert set(scene.paths)==set(ids)
 assert all(len(scene.paths[i])==len(rows) for i in ids)
 assert len(scene.points)==2 and scene.points[ids[0]]['cx']>scene.points[ids[1]]['cx']
 behaviors=[]
 for frame in frames:
  for i,identity in enumerate((frame['primary_id'],frame['secondary_id'])):
   if identity:
    alarm=int(i==1);warning=1
    behaviors.append(dict(seq=frame['seq'],index=i,id=identity,alarm=alarm,warning=warning,horizon_ms=500,control=7 if alarm else 11,inside=0,pixels=0))
 newpoints=copy.deepcopy(points)
 for p in newpoints:p['alarm']=int(not p['primary'])
 assert identity_output_valid(records,frames,newpoints,boxes,boxes2,falls,behaviors)
 assert behavior_output_valid(records,frames,behaviors)
 broken=copy.deepcopy(behaviors);broken[1]['control']=11
 assert not behavior_output_valid(records,frames,broken)
 broken=copy.deepcopy(behaviors);broken[0]['id']=999
 assert not behavior_output_valid(records,frames,broken)
 tests.append('Independent secondary alarm and first-slot warning accepted; color priority and wrong ID rejected')
 p=next(iter(scene.points.values()));scene.consume('YBEHAVIOR seq=%d id=%d warning=1 prediction_valid=1 predicted_cx=980 predicted_cy=360' % (p['seq'],p['id']))
 assert scene.points[p['id']]['warning']==1 and scene.points[p['id']]['predicted_cx']==980
 tests.append('Viewer shows two distinct IDs and observed center histories after crossing')
 scene.consume('YTRACK_FRAME seq=999 ms=3000 visible=0 active=2 primary_id=0 secondary_id=0')
 assert not scene.points
 tests.append('Viewer removes boxes immediately on an empty observed frame')
 # A failed open must not leave a dead GUI; a busy port and a later USB error
 # both recover while the same reader stays alive. No board/port is touched.
 stop=threading.Event();received=[];opened=[];sessions=[]
 class MockUART:
  def __init__(self,chunk):self.chunk=chunk
  def __enter__(self):return self
  def __exit__(self,*args):return False
  @property
  def in_waiting(self):return len(self.chunk)
  def read(self,size):
   if self.chunk:
    data=self.chunk;self.chunk=b'';return data
   raise OSError('synthetic USB disconnect')
 def factory(port,*args,**kwargs):
  opened.append(port)
  if len(opened)==1:raise PermissionError(13,'synthetic busy port')
  start=1 if len(opened)==2 else 4
  session=MockUART(('\n'.join(lines[start:start+3])+'\n').encode('gbk'));sessions.append(session);return session
 def post(line):
  received.append(line)
  if sum(s.startswith('YTRACK_FRAME ') for s in received)>=2:stop.set()
  return True
 read_live_lines('COM_TEST',stop,post,serial_factory=factory,retry_seconds=0)
 assert len(opened)==3 and sum(s.startswith('YTRACK_FRAME ') for s in received)==2
 assert sum(s.startswith('__LINK__已连接 COM_TEST，') for s in received)==2
 assert any('未连接' in s for s in received) and not any(s.startswith('__ERROR__') for s in received)
 tests.append('Busy UART and subsequent USB disconnect automatically reconnect without GUI restart')
 demo=OUT/'rv32_synthetic_crossing_uart.log'
 demo.write_text('# SYNTHETIC RV32 ASSOCIATION TEST; NOT A BOARD RECORDING\n'+'\n'.join(lines)+'\n',encoding='utf8')
 command=[sys.executable,'-B','-X','utf8',str(ROOT/'delivery/two_person_track_viewer.py'),
  '--log',str(demo),'--speed','100','--output',str(OUT/'viewer_self_test'),'--self-test']
 r=subprocess.run(command,capture_output=True,text=True,timeout=25)
 (OUT/'viewer_self_test.log').write_text(r.stdout+r.stderr,encoding='utf8');assert not r.returncode,r.stdout+r.stderr
 tests.append('Hidden Tk canvas, recorded-log replay and CSV output execute successfully')
 text=(OUT/'viewer_self_test/trajectories.csv').read_text(encoding='utf-8-sig')
 assert len(text.strip().splitlines())==len(points)+1
 files=[Path(__file__),SW/'yolo_auto_download.py',ROOT/'delivery/two_person_track_viewer.py',OUT/'result.json']
 report=dict(complete=True,passed=True,board_accessed=False,tests=tests,
  inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 (OUT/'tools_result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 print('PASS tracking UART validator and viewer:',len(tests),'checks; no board accessed')
if __name__=='__main__':main()
