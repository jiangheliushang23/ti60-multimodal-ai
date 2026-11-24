"""Build an isolated RV32 reference validation target using local TFLM sources."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
VENDOR=HERE/'runtime'
TOOLCHAIN=Path(os.environ['TI60_RISCV_BIN'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--multimodal-live',action='store_true',help='YOLO camera plus original SHT30/MLX90640 on shared HDMI')
    parser.add_argument('--camera-live',action='store_true',help='Auto-start the camera with acknowledged HDMI boxes; match YCM2 hardware')
    parser.add_argument('--qemu',action='store_true')
    parser.add_argument('--compat',action='store_true',help='Separate hardware compatibility and timing target')
    parser.add_argument('--optimize',action='store_true',help='Isolated DSP/tiled YOLO target (implies --compat)')
    parser.add_argument('--dsp8x4',action='store_true',help='Match 8x4 DSP bit with MUL disabled')
    parser.add_argument('--dsp16',action='store_true',help='Match 16x4 DSP bit with ADD and MUL disabled')
    parser.add_argument('--realtime',action='store_true',help='Match 16x4 DSP + ADD + 32 KiB cache bit')
    parser.add_argument('--cache32',action='store_true',help='Match 16x4 DSP + 32 KiB cache with software ADD')
    parser.add_argument('--replay',help='Build raw-head UART/video replay firmware for an optimized variant')
    args=parser.parse_args()
    if args.multimodal_live:args.camera_live=True
    if args.camera_live:args.replay='raw96x192';args.cache32=True
    if args.cache32:args.realtime=True
    if args.realtime:args.dsp16=True
    if args.dsp16 and args.dsp8x4: parser.error('Select a single hardware configuration')
    if args.replay: args.optimize=True
    if args.optimize: args.compat=True
    generated=None
    if args.replay:
        if args.camera_live:
            generated=HERE/'optimized'/args.replay/'generated'
            for name in ('fixture.h','assets.S','input.bin','expected.bin'):
                if not (generated/name).is_file():raise RuntimeError('Missing verified fixture: '+str(generated/name))
        else:
            from prepare_fast_fixture import main as prepare_fast_fixture
            generated=prepare_fast_fixture(args.replay)
    if args.compat and args.qemu: parser.error('Real accelerator validation cannot run in QEMU')
    if not args.camera_live and not (HERE/'generated/fixture.h').exists():
        subprocess.run([sys.executable,'-B','-X','utf8',str(HERE/'prepare_fixture.py')],check=True)
    if args.compat and not args.camera_live:
        subprocess.run([sys.executable,'-B','-X','utf8',str(HERE/'audit_operators.py')],check=True,
                       stdout=subprocess.DEVNULL)
    output_name='build_'+args.replay if args.replay else 'build_fast' if args.optimize else 'build_compat' if args.compat else 'build_qemu' if args.qemu else 'build'
    if args.cache32: output_name+='_cache32'
    elif args.realtime: output_name+='_realtime'
    elif args.dsp16: output_name+='_dsp16'
    if args.camera_live:output_name='build_camera_live'
    if args.multimodal_live:output_name='build_multimodal_live'
    output=HERE/output_name
    output.mkdir(exist_ok=True)
    (output/'build_result.json').write_text('{"complete": false}',encoding='utf-8')
    source=[]
    for pattern in ('tensorflow/lite/*.cc','tensorflow/lite/c/*.cc','tensorflow/lite/c/*.c','tensorflow/lite/core/api/*.cc',
                    'tensorflow/lite/kernels/*.cc','tensorflow/lite/kernels/internal/*.cc',
                    'tensorflow/lite/micro/*.cc','tensorflow/lite/micro/memory_planner/*.cc','tensorflow/lite/schema/*.cc'):
        source.extend(VENDOR.glob(pattern))
    source=[p for p in source if not p.name.endswith('_test.cc') and p.name not in ('debug_log.cc','micro_time.cc','test_helpers.cc')]
    kernels=['add','concatenation','conv','conv_common','pad','pooling','resize_nearest_neighbor','logistic',
             'transpose','reshape','split_v','mul','quantize','quantize_common','kernel_util']
    source.extend(VENDOR/'tensorflow/lite/micro/kernels'/f'{name}.cc' for name in kernels)
    source.extend((HERE/'src').glob('*.cc'))
    source.extend((HERE/'src').glob('*.S'))
    if args.compat:
        source=[p for p in source if p not in (HERE/'src/main.cc',HERE/'src/start.S')]
        source.extend((HERE/'compat_src').glob('*.cc'))
        source.extend((HERE/'compat_src').glob('*.S'))
        source.append(HERE/'compatibility/driver_dispatch.cc')
        if args.optimize: source.extend((HERE/'opt_src').glob('*.cc'))
        if args.replay:
            source=[p for p in source if p not in (HERE/'compat_src/main.cc',HERE/'src/assets.S')]
            source.extend((HERE/'replay_src').glob('*.cc'))
            source.append(generated/'assets.S')
    if args.multimodal_live:
        source.extend((HERE/'sensor_src').glob('*.cc'));source.extend((HERE/'sensor_src').glob('*.cpp'))
        source.extend((HERE/'http_src').glob('*.cc'));source.extend((HERE/'http_src').glob('*.c'))
        for pattern in ('core/*.c','core/ipv4/*.c','netif/ethernet.c'):
            source.extend((HERE/'http_src/lwip').glob(pattern))
    source=sorted(set(source))
    flags=['-march=rv32im_zicsr','-mabi=ilp32','-O3','-g','-ffunction-sections','-fdata-sections',
           '-fno-common','-fno-strict-aliasing','-fno-unroll-loops','-fno-builtin','-fno-rtti','-fno-exceptions',
           '-fno-threadsafe-statics','-std=c++11','-DTF_LITE_STATIC_MEMORY','-DTF_LITE_USE_GLOBAL_CMATH_FUNCTIONS',
           '-DTF_LITE_USE_GLOBAL_MIN','-DTF_LITE_USE_GLOBAL_MAX','-DTF_LITE_DISABLE_X86_NEON',
           '-I'+str(HERE/'include'),'-I'+str(HERE/'generated'),'-I'+str(HERE/'src'),'-I'+str(VENDOR),
           '-I'+str(VENDOR/'tensorflow/third_party/flatbuffers/include'),
           '-I'+str(VENDOR/'tensorflow/third_party/gemmlowp'),'-I'+str(VENDOR/'tensorflow/third_party/ruy')]
    if args.qemu: flags.append('-DYOLO_QEMU')
    if args.optimize: flags.extend(['-DYOLO_OPT','-I'+str(HERE/'opt_src')])
    if args.dsp8x4: flags.append('-DYOLO_DSP8X4')
    if args.dsp16: flags.append('-DYOLO_DSP16')
    if args.realtime: flags.append('-DYOLO_REALTIME')
    if args.cache32: flags.append('-DYOLO_CACHE32')
    if args.replay: flags.append('-DYOLO_RAW_REPLAY')
    if args.camera_live:flags.append('-DYOLO_CAMERA_LIVE')
    if args.multimodal_live:flags.extend(['-DYOLO_MULTIMODAL','-DYOLO_CAMERA_AUTO','-DYOLO_BOARD_HTTP','-I'+str(HERE/'sensor_src'),'-I'+str(HERE/'http_src'),'-I'+str(HERE/'http_src/lwip/include')])
    if args.compat:
        flags.remove('-I'+str(HERE/'include'))
        flags[:0]=['-I'+str(HERE/'compat_include'),'-I'+str(HERE/'compatibility'),
                   '-I'+str(HERE/'compat_src'),'-I'+str(VENDOR/'platform/interrupt'),
                   '-I'+str(VENDOR/'platform/tinyml/ops')]
        flags.append('-DYOLO_COMPAT')
    if generated: flags.insert(0,'-I'+str(generated))
    compiler=str(TOOLCHAIN/'riscv-none-elf-g++.exe')
    commands=[]
    for p in source:
        label=('local/'+str(p.relative_to(HERE))) if p.is_relative_to(HERE) else ('runtime/'+str(p.relative_to(VENDOR)))
        obj=output/'out'/Path(label).with_suffix('.o')
        obj.parent.mkdir(parents=True,exist_ok=True)
        if p.suffix=='.c':
            cflags=[f for f in flags if f not in ('-std=c++11','-fno-rtti','-fno-exceptions','-fno-threadsafe-statics')]
            commands.append([str(TOOLCHAIN/'riscv-none-elf-gcc.exe'),*cflags,'-c',str(p),'-o',str(obj)])
        else:
            commands.append([compiler,*flags,'-c',str(p),'-o',str(obj)])
    start=time.monotonic()
    print(f'Compiling {len(commands)} files, qemu={args.qemu}',flush=True)
    def compile_one(command):
        result=subprocess.run(command,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        return result.returncode,result.stdout.decode('utf-8',errors='replace')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(compile_one,commands))
    log='\n'.join(text for _,text in results if text)
    (output/'build.log').write_text(log,encoding='utf-8')
    if any(code for code,_ in results):
        print(log[-20000:]); raise SystemExit('Compilation failed: see build.log')
    elf=output/('tinyml_yolo_compat.elf' if args.compat else 'tinyml_yolo_static.elf')
    link=[compiler,'-march=rv32im_zicsr','-mabi=ilp32','-nostartfiles','-specs=nosys.specs',
          '-Wl,--gc-sections','-Wl,--defsym,YOLO_RAM_ORIGIN='+('0x80000000' if args.qemu else '0x1000'),
          '-Wl,--defsym,YOLO_RAM_LENGTH='+('0x4000000' if args.qemu else '0x00dff000' if args.camera_live else '0x3fff000'),
          '-Wl,-T,'+str(HERE/'linker.ld'),'-Wl,-Map,'+str(output/'tinyml_yolo_static.map'),
          '-Wl,--print-memory-usage',*[c[-1] for c in commands],
          *([str(HERE/'lib/tinyml_lib.a')] if args.compat else []),
          '-lm','-lc','-lgcc','-o',str(elf)]
    linked=subprocess.run(link,cwd=HERE,capture_output=True,text=True)
    (output/'build.log').write_text(log+'\n'+linked.stdout+linked.stderr,encoding='utf-8')
    print(linked.stdout+linked.stderr)
    if linked.returncode: raise SystemExit('Link failed: see build.log')
    subprocess.run([str(TOOLCHAIN/'riscv-none-elf-objcopy.exe'),'-O','binary',str(elf),str(elf.with_suffix('.bin'))],check=True)
    for tool,options,name in [('size',[], 'size.txt'),('readelf',['-h','-l','-A'],'elf_layout.txt'),('nm',['-n'],'symbols.txt')]:
        result=subprocess.run([str(TOOLCHAIN/f'riscv-none-elf-{tool}.exe'),*options,str(elf)],capture_output=True,text=True,check=True)
        (output/name).write_text(result.stdout,encoding='utf-8')
    report=dict(complete=True,backend='VERIFIED_HYBRID' if args.compat else 'RV32_CPU_REFERENCE',
                qemu_target=args.qemu,hardware_access=args.compat,
                elapsed_s=time.monotonic()-start,elf=str(elf),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                binary_bytes=elf.with_suffix('.bin').stat().st_size,compiler=compiler,flags=flags,
                source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source},
                model_sha256=hashlib.sha256((generated.parent/'model.tflite' if generated else HERE/'generated/model.tflite').read_bytes()).hexdigest())
    (output/'build_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'Built: {elf}',flush=True)


if __name__=='__main__': main()
