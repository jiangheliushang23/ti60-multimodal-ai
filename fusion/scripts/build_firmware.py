"""Build the isolated multimodal firmware. Never program a device."""
from pathlib import Path
import subprocess, os, json, time

root=Path(__file__).resolve().parents[1]/'demo_multimodal'
p=root/'software/standalone/tinyml_pdti8'
if not p.is_dir(): raise SystemExit('Run prepare_project.py to create the isolated copy first')
for source in list((p/'src').rglob('*'))+list((p.parent/'common').glob('*')):
    if source.suffix in ('.c','.cc','.cpp','.S','.s'):
        (p/'build/out'/Path(os.path.relpath(source,p)).with_suffix('.o')).parent.mkdir(parents=True,exist_ok=True)
tc='C:/Efinity/efinity-riscv-ide-2026.1/toolchain/bin/riscv-none-elf-'
args=['C:/Efinity/efinity-riscv-ide-2026.1/build_tools/bin/make.exe','-B','-o','build/out','-j4','all',
      'BSP=efinix/EfxSapphireSoc','RISCV_BIN='+tc,'RISCV_CXX='+tc+'g++','MARCH=rv32im_zicsr']
start=time.time()
with (root/'build.log').open('w',encoding='utf-8') as log:
    r=subprocess.run(args,cwd=p,stdout=log,stderr=subprocess.STDOUT)
result=dict(command=args,cwd=str(p),exit_code=r.returncode,elapsed_s=round(time.time()-start,2),hardware_access=False)
if r.returncode==0:
    elf=p/'build/tinyml_pdti8.elf'
    for exe,opts,name in [('size',[str(elf)],'size.txt'),('readelf',['-h','-A',str(elf)],'elf_attributes.txt')]:
        res=subprocess.run([tc+exe+'.exe',*opts],capture_output=True,text=True,encoding='utf-8',errors='replace')
        (root/name).write_text(res.stdout+res.stderr,encoding='utf-8')
(root/'build_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
print('\n'.join((root/'build.log').read_text(encoding='utf-8',errors='replace').splitlines()[-16:]))
raise SystemExit(r.returncode)
