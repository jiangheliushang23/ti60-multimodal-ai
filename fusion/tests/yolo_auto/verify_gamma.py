"""Exhaustively compare the actual LUT masks/ROM with the original ISP curve."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[3];HW=ROOT/'fusion/ti60_yolo_auto'
def main():
 p=HW/'src/camera/gamma_conrrection/gamma_correction.v';s=p.read_text()
 small=HW/'src/camera/gamma_conrrection/linear_to_display_2p2_u8.mem'
 original=ROOT/'fusion/ti60_multimodal/src/camera/gamma_conrrection/linear_to_display_2p2.mem'
 reference=[int(x,16) for x in original.read_text().split()]
 expected=[reference[(v<<2)|(v>>6)]>>2 for v in range(256)]
 assert [int(x,16) for x in small.read_text().split()]==expected
 cells=re.findall(r'EFX_LUT4 #\(\.LUTMASK\(16\'h([0-9a-f]+)\)\) \w+\(\.I0\(([^)]+)\),\.I1\(([^)]+)\),\.I2\(([^)]+)\),\.I3\(([^)]+)\),\.O\(([^)]+)\)\);',s)
 assert len(cells)==2*8*31,len(cells)
 for pixel in range(2):
  for value in range(256):
   wires={f'a{pixel}[{i}]':(value>>i)&1 for i in range(8)};wires["1'b0"]=0;wires["1'b1"]=1
   for mask,*ports in cells:
    if not ports[-1].startswith(f'p{pixel}_'):continue
    index=sum(wires[pin]<<i for i,pin in enumerate(ports[:-1]));wires[ports[-1]]=(int(mask,16)>>index)&1
   actual=sum(wires[f'p{pixel}_b{i}[30]']<<i for i in range(8))
   assert actual==expected[value],(pixel,value,actual,expected[value])
 out=HW/'validation/gamma';out.mkdir(parents=True,exist_ok=True)
 files=[Path(__file__),p,small,original]
 (out/'result.json').write_text(json.dumps(dict(complete=True,passed=True,board_accessed=False,logic_cases=512,rom_cases=256,
  inputs_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2),encoding='utf-8')
 print('PASS gamma: all 512 pixel/LUT combinations and 256 ROM entries match original 10-bit ISP curve')
if __name__=='__main__':main()
