"""Validate the exact imported camera setup and ISP, including its two-cycle line RAM."""
from pathlib import Path
import subprocess,hashlib,json,sys
root=Path(__file__).resolve().parents[2];project=root/'fusion/ti60_multimodal';tests=root/'fusion/tests';src=project/'src/camera'
iv=root/'tools/iverilog/bin/iverilog.exe';vvp=iv.with_name('vvp.exe');logs=[];cases=[]
def run(args):
 p=subprocess.run(list(map(str,args)),cwd=project,capture_output=True,text=True);logs.append(p.stdout+p.stderr)
 assert p.returncode==0,logs[-1]
 return p.stdout
setup=[tests/'setup_tb.v',src/'sc431hai/sc431hai_setup.v',src/'sc431hai/i2c_reg16.v']
isp=[tests/'debayer_tb.v',*[src/'debayer'/n for n in ['debayer_top_2to1.v','raw_to_rgb.v','line_buffer.v','rgb_gain_v1.v','true_dual_port_ram.v','camera_line_ram.v']]]
run([iv,'-g2012','-I',src/'sc431hai','-s','stream_check_tb','-o','validation/camera_setup.vvp',*setup])
for n in range(14):
 out=run([vvp,'validation/camera_setup.vvp',f'+CASE={n}']);assert 'PASS' in out;cases.append('setup_'+str(n))
for n in range(2):
 run([iv,'-g2012',f'-Pdebayer_tb.GAIN_CASE={n}','-s','debayer_tb','-o','validation/camera_isp.vvp',*isp])
 assert 'PASS' in run([vvp,'validation/camera_isp.vvp']);cases.append('bggr_gain_'+str(n))
run([sys.executable,'-B',tests/'camera_spatial.py']);cases.append('spatial_79128_components')
files=set(setup+isp+[src/'sc431hai/sc_sequence.vh',tests/'spatial_tb.v',tests/'camera_spatial.py',Path(__file__)])
r={'passed':True,'cases':cases,'sources':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
(project/'validation/camera_reuse_tests.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
(project/'validation/camera_reuse_tests.log').write_text('\n'.join(logs),encoding='utf-8')
print('PASS',len(cases),'camera setup/ISP scenarios; exact source fingerprints saved.')
