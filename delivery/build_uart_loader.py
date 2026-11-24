"""Build the temporary RAM-only transfer helper; no production firmware changes."""
from pathlib import Path
import hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'delivery/uart_loader'
OUT=SRC/'build'
TOOL=Path(os.environ['TI60_RISCV_BIN'])

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sources=[SRC/'start.S',SRC/'loader.c',SRC/'linker.ld',Path(__file__)]
 elf=OUT/'uart_loader.elf'
 cmd=[str(TOOL/'riscv-none-elf-gcc.exe'),'-march=rv32im_zicsr','-mabi=ilp32','-O2',
      '-ffreestanding','-fno-builtin','-nostdlib','-nostartfiles','-msmall-data-limit=0',
      '-Wl,-T,'+str(SRC/'linker.ld'),'-Wl,-Map,'+str(OUT/'uart_loader.map'),
      str(SRC/'start.S'),str(SRC/'loader.c'),'-lgcc','-o',str(elf)]
 r=subprocess.run(cmd,capture_output=True,text=True)
 (OUT/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8')
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 binary=elf.with_suffix('.bin')
 subprocess.run([str(TOOL/'riscv-none-elf-objcopy.exe'),'-O','binary',str(elf),str(binary)],check=True)
 assert binary.stat().st_size<8192
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 report=dict(complete=True,passed=True,entry=0xc00000,scratch_end=0xc10000,baud=500000,block_bytes=4096,
             bytes=binary.stat().st_size,binary_sha256=sha(binary),elf_sha256=sha(elf),
             inputs_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sources})
 (OUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('UART_LOADER_BUILT',binary,report['bytes'])
if __name__=='__main__':main()
