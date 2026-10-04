"""Offline stage-2 unit tests. Results bind every source to its SHA256."""
from pathlib import Path
import subprocess,json,hashlib,time,sys
root=Path(__file__).resolve().parents[2];tests=root/'fusion/tests';p=root/'fusion/ti60_multimodal';s=p/'src'
iv=root/'tools/iverilog/bin/iverilog.exe';vvp=iv.with_name('vvp.exe');fifo=s/'camera/frame_buffer_V4/DC_FIFO.v'
cases={
 'camera_line_bridge_tb':[s/'fusion/camera_line_bridge.v',fifo],
 'camera_rgb_pack_tb':[s/'fusion/camera_rgb_pack.v'],
 'video_ddr_tb':[s/'fusion/video_ddr.v',fifo],
 'fusion_page_tb':[s/'fusion/fusion_page.v',s/'hdmi/sht30_font.v'],
}
results=[]
for name,files in cases.items():
 if len(sys.argv)>1 and name not in sys.argv[1:]:continue
 files=[tests/(name+'.v'),*files];binary=tests/(name+'.vvp');start=time.time()
 c=subprocess.run([str(iv),'-g2012','-s',name,'-o',str(binary),*map(str,files)],capture_output=True,text=True)
 log=c.stdout+c.stderr;code=c.returncode
 if code==0:
  c=subprocess.run([str(vvp),str(binary)],cwd=p,capture_output=True,text=True,timeout=180);log+=c.stdout+c.stderr;code=c.returncode
 result={'test':name,'passed':code==0 and 'PASS ' in log,'seconds':time.time()-start,'sources':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
 (p/'validation'/(name+'.log')).write_text(log,encoding='utf-8')
 (p/'validation'/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(log.strip(),flush=True)
 if not result['passed']:raise SystemExit(1)
