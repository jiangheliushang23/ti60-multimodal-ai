from pathlib import Path
import subprocess,random,json,hashlib,os,shutil
REPO=Path(__file__).resolve().parents[3];R=REPO/'fusion'
T=Path(__file__).resolve().parent;S=R/'demo_multimodal/software/standalone/tinyml_pdti8/src';V=R/'ti60_multimodal/validation';V.mkdir(parents=True,exist_ok=True)
GCC=Path(os.environ.get('CXX') or shutil.which('g++') or 'C:/msys64/ucrt64/bin/g++.exe');IV=Path(os.environ.get('IVERILOG') or shutil.which('iverilog') or str(REPO/'tools/iverilog/bin/iverilog.exe'));VVP=Path(os.environ.get('VVP') or shutil.which('vvp') or str(IV.with_name('vvp.exe')))
def run(args):
 c=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=300);assert c.returncode==0,c.stdout+c.stderr;return c.stdout
run([GCC,'-B',str(GCC.resolve().parent)+'/','-std=c++11','-Wall','-Wextra','-Werror','-I',S,T/'control_host.cc','-o',V/'control_host.exe'])
print(run([V/'control_host.exe']).strip(),flush=True)
cases=[];rng=random.Random(431)
def add(mean,clip,rmean,gmean,bmean,exp,gain,r=256,b=256,counts=(8160,16320,8160)):
 rc,gc,bc=counts;cases.append([mean*16320,16320,clip,32640,rmean*rc,rc,gmean*gc,gc,bmean*bc,bc,exp,gain,r,b])
for mean in (0,23,24,47,48,60,64,65,239):
 for clip in (0,255,256,257,510,511,512):
  for exp,gain in ((2989,82),(2989,0),(4,0),(100,18),(2980,81)):
   add(mean,clip,30,60,90,exp,gain)
for i in range(300):
 add(rng.randrange(240),rng.randrange(32641),rng.randrange(232),rng.randrange(232),rng.randrange(232),rng.randrange(4,2990),rng.randrange(83),rng.randrange(128,513),rng.randrange(128,513),tuple(rng.choice((0,1,63,64,8160)) for _ in range(3)))
vectors=V/'control_vectors.txt';vectors.write_text('\n'.join(' '.join(map(str,c)) for c in cases)+'\n')
host=run([V/'control_host.exe',vectors]).splitlines()
reference=T/'reference/rtl/sc431hai'
run([IV,'-g2012','-s','control_reference_tb','-o',V/'control_reference.vvp',T/'control_reference_tb.v',reference/'sc_auto_control.v',reference/'sc_auto_stats.v'])
output=V/'control_rtl_output.txt'
print(run([VVP,V/'control_reference.vvp','+INPUT='+str(vectors),'+OUTPUT='+str(output)]).strip(),flush=True)
ref=output.read_text().splitlines();assert len(ref)==len(host)==len(cases)
for i,(a,b) in enumerate(zip(ref,host)):assert a==b,(i,cases[i],a,b)
(V/'cpu_control_tests.json').write_text(json.dumps(dict(passed=True,reference_cases=len(cases),scheduler=True,sources={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [S/'camera_control.h',S/'camera_auto.h',T/'control_host.cc',T/'control_reference_tb.v',reference/'sc_auto_control.v',reference/'sc_auto_stats.v']}),indent=2))
print('PASS integer CPU decisions exactly match frozen FPGA AE/AWB reference:',len(cases))
