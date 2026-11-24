"""Build the merged FPGA image and record fresh artifacts; never access USB/JTAG."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,subprocess,time,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
HW=ROOT/'fusion/ti60_yolo_auto'
EFX=Path(os.environ['TI60_EFINITY'])

def project_settings(path):
    root=ET.parse(path).getroot()
    for name in ('sw_version','last_change_date','location','last_run_tool'):
        root.attrib.pop(name,None)
    def tree(e):return (e.tag,sorted(e.attrib.items()),(e.text or '').strip(),[tree(c) for c in e])
    return tree(root)


def timing_summary(artifact):
    timing=artifact.read_text(errors='replace')
    if 'Clock Relationship Summary (begin)' not in timing:raise RuntimeError('Missing clock relationship summary')
    summary=timing.split('Clock Relationship Summary (begin)',1)[1].split('Clock Relationship Summary (end)',1)[0]
    setup=summary.split('Setup (Max) Clock Relationship',1)[1].split('Hold (Min) Clock Relationship',1)[0]
    hold=summary.split('Hold (Min) Clock Relationship',1)[1]
    # The numeric columns are Constraint and Slack, not Setup and Hold.
    def slacks(section):
        rows=re.findall(r'^\S+\s+\S+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\([RF]-[RF]\)',section,re.M)
        if not rows:raise RuntimeError('No timing rows')
        return [float(slack) for constraint,slack in rows]
    a,b=slacks(setup),slacks(hold)
    if min(a+b)<0:raise RuntimeError('Negative setup/hold slack')
    return dict(setup_slack_min_ns=min(a),hold_slack_min_ns=min(b),setup_timing_rows=len(a),hold_timing_rows=len(b),
                timing_report_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser();p.add_argument('--flow',choices=('all','interface','map','pnr','pgm'),default='all')
    p.add_argument('--resume-after-map',action='store_true')
    p.add_argument('--resume-after-pnr',action='store_true',help='Finish bit generation from completed, unchanged PNR')
    p.add_argument('--verify-existing',action='store_true',help='Recheck a completed build without running FPGA tools')
    p.add_argument('--pnr-seed',type=int,help='Change only the placement seed after validating the unchanged completed map')
    p.add_argument('--mapped-project-xml',type=Path,help='Saved exact input XML, to prove an Efinity metadata-only rewrite before resuming map')
    p.add_argument('--pnr-optimization-level',choices=('CONGESTION_1','CONGESTION_2','CONGESTION_3','TIMING_1','TIMING_2','TIMING_3'),
                   help='Change only the PNR optimization strategy after validating the unchanged completed map')
    args=p.parse_args()
    if (args.pnr_seed is not None or args.pnr_optimization_level is not None) and (not args.resume_after_map or args.verify_existing or args.flow!='all'):
        raise RuntimeError('PNR option changes require --resume-after-map with the complete flow')
    out=HW/'validation';out.mkdir(exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    report=dict(complete=False,passed=False,board_accessed=False,started_at=datetime.datetime.now().isoformat(),flows={})
    dest=out/'fpga_build_result.json'
    save=lambda:dest.write_text(json.dumps(report,indent=2),encoding='utf-8')
    env=os.environ.copy();env.update(PROCESSOR_ARCHITECTURE='AMD64',EFINITY_HOME=EFX.as_posix(),PYTHONHOME=(EFX/'python311').as_posix(),PYTHONDONTWRITEBYTECODE='1')
    env['PATH']=';'.join(str(EFX/p) for p in ('python311/bin','bin','pgm/bin','debugger/bin','scripts'))+';'+env.get('PATH','')
    env.update(EFXPT_HOME=(EFX/'pt').as_posix(),EFXPGM_HOME=(EFX/'pgm').as_posix(),EFXDBG_HOME=(EFX/'debugger').as_posix(),
               EFINITY_USER_DIR_INI=(Path(env['LOCALAPPDATA'])/'efinity/user_dir.ini').as_posix())
    inputs=[p for folder in ('src','ip','sdc') for p in (HW/folder).rglob('*') if p.is_file() and p.suffix.lower() in ('.v','.sv','.vh','.mem','.hex','.bin','.xml','.json','.sdc','.f')]
    inputs.extend([HW/'Ti60_Multimodal.xml',HW/'Ti60_Multimodal.peri.xml',HW/'debug_top.v',*HW.glob('*.bin')])
    fingerprint=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    initial=fingerprint()
    project_at_start=project_settings(HW/'Ti60_Multimodal.xml')
    if args.verify_existing:
        previous=json.loads(dest.read_text(encoding='utf-8'))
        if not previous.get('complete') or not previous.get('passed'):raise RuntimeError('Existing build is not complete')
        if any(previous['flows'].get(f,{}).get('exit_code')!=0 for f in ('interface','map','pnr','pgm')):raise RuntimeError('Incomplete FPGA flow')
        if previous['inputs_sha256']!=initial:raise RuntimeError('Hardware inputs changed after build')
        bit=HW/'outflow/Ti60_Multimodal.bit'
        if hashlib.sha256(bit.read_bytes()).hexdigest()!=previous['bit_sha256']:raise RuntimeError('Bit changed after build')
        previous.update(timing_summary(HW/'outflow/Ti60_Multimodal.timing.rpt'))
        dest.write_text(json.dumps(previous,indent=2),encoding='utf-8')
        print('EXISTING_BUILD_VERIFIED',dest,flush=True);return
    report['inputs_sha256_at_start']=initial
    if args.resume_after_pnr:
        if args.flow!='all' or args.resume_after_map:raise RuntimeError('PNR resume requires --flow all')
        previous=json.loads(dest.read_text(encoding='utf-8'))
        if not all(previous.get('flows',{}).get(f,{}).get('exit_code')==0 for f in ('interface','map','pnr')):raise RuntimeError('No completed PNR to resume')
        began=datetime.datetime.fromisoformat(previous.get('source_build_started_at',previous['started_at'])).timestamp()
        if previous.get('inputs_sha256_at_start'):
            if previous['inputs_sha256_at_start']!=initial:raise RuntimeError('Hardware source hashes changed')
        else:
            # Older build wrappers did not persist the initial hash manifest.
            # Efinity touches its project XML after each flow. All HDL, IP,
            # pin/SDC files must still predate the completed build.
            newer=[p for p in inputs if p.name!='Ti60_Multimodal.xml' and p.stat().st_mtime>began+1]
            if newer:raise RuntimeError('Sources changed after PNR: '+str(newer))
            project=ET.parse(HW/'Ti60_Multimodal.xml').getroot()
            syn=next(e for e in project if e.tag.endswith('}synthesis'))
            options={e.attrib.get('name'):e.attrib.get('value') for e in syn}
            mapped=(HW/'outflow/Ti60_Multimodal.map.rpt').read_text(errors='replace')
            for key in ('mode','retiming','pack-luts-to-comb4'):
                if not re.search(r'^'+re.escape(key)+r' : '+re.escape(options[key])+r'$',mapped,re.M):raise RuntimeError('Project differs from mapped options')
            report['legacy_resume_input_check']='unchanged HDL/IP/SDC/pin timestamps; mapped synthesis settings checked; project XML touched by Efinity'
        for suffix in ('.map.rpt','.map.v','.timing.rpt','.route.out','.troutingtraces'):
            artifact=HW/'outflow'/('Ti60_Multimodal'+suffix)
            if not artifact.exists() or artifact.stat().st_mtime<began:raise RuntimeError('Stale completed PNR artifact '+str(artifact))
        report.update(timing_summary(HW/'outflow/Ti60_Multimodal.timing.rpt'))
        report['flows']={f:previous['flows'][f] for f in ('interface','map','pnr')}
        report['reused_completed_flows']=['interface','map','pnr'];report['source_build_started_at']=previous.get('source_build_started_at',previous['started_at'])
        flows=('pgm',)
    elif args.resume_after_map:
        if args.flow!='all':raise RuntimeError('Resume requires --flow all')
        previous=json.loads(dest.read_text(encoding='utf-8'))
        if not all(previous.get('flows',{}).get(f,{}).get('exit_code')==0 for f in ('interface','map')):raise RuntimeError('No completed interface/map to resume')
        began=datetime.datetime.fromisoformat(previous.get('source_build_started_at',previous['started_at'])).timestamp()
        if previous.get('inputs_sha256_at_start'):
            if previous['inputs_sha256_at_start']!=initial:
                changed={p for p in initial if initial[p]!=previous['inputs_sha256_at_start'].get(p)}
                project_key=(HW/'Ti60_Multimodal.xml').relative_to(ROOT).as_posix()
                # Efinity rewrites the project after map. For older reports
                # without a settings snapshot, accept only an exact match to
                # the project's previously validated release configuration.
                release_path=HW/'yolo_auto_release.json'
                release=json.loads(release_path.read_text(encoding='utf8')) if release_path.is_file() else {}
                validated_xml=release.get('inputs_sha256',{}).get(project_key)==initial[project_key]
                if args.mapped_project_xml:
                    saved=args.mapped_project_xml.resolve()
                    assert hashlib.sha256(saved.read_bytes()).hexdigest()==previous['inputs_sha256_at_start'][project_key],'Saved XML differs from recorded map input'
                    assert project_settings(saved)==project_settings(HW/'Ti60_Multimodal.xml'),'Project settings changed since map'
                    validated_xml=True
                    report['original_mapped_project_xml']=dict(path=str(saved),sha256=hashlib.sha256(saved.read_bytes()).hexdigest(),canonical_settings_identical=True)
                # The first YAU9 map predates publication. Its independent
                # preservation audit checks XML settings against saved v16,
                # allowing only added voice HDL/SDC and PNR seed/strategy.
                voice_path=HW/'validation/voice_merge/result.json'
                if not validated_xml and voice_path.is_file():
                    voice=json.loads(voice_path.read_text(encoding='utf8'))
                    validated_xml=bool(voice.get('complete') and voice.get('passed') and
                        voice.get('original_functionality_preserved') and
                        voice.get('inputs_sha256',{}).get(project_key)==initial[project_key])
                if changed!={project_key} or not validated_xml:
                    raise RuntimeError('Hardware input hashes changed; run the full build')
                mapped=(HW/'outflow/Ti60_Multimodal.map.rpt').read_text(errors='replace')
                syn=next(e for e in ET.parse(HW/'Ti60_Multimodal.xml').getroot() if e.tag.endswith('}synthesis'))
                for e in syn:
                    key,value=e.attrib.get('name'),e.attrib.get('value')
                    match=re.search(r'^'+re.escape(key or '')+r' : (.*)$',mapped,re.M)
                    if match and match[1].strip()!=value:raise RuntimeError('Mapped synthesis setting differs: '+key)
                report['project_rewrite_review']=dict(previous_hash=previous['inputs_sha256_at_start'][project_key],
                    current_hash=initial[project_key],verified_against='validated release or voice preservation XML and completed map options')
        elif any(p.stat().st_mtime>began+1 for p in inputs):raise RuntimeError('Hardware inputs changed after the previous build began; run the full build')
        for suffix in ('.map.rpt','.map.v','.pt.sdc'):
            artifact=HW/'outflow'/('Ti60_Multimodal'+suffix)
            if not artifact.exists() or artifact.stat().st_mtime<began:raise RuntimeError('Stale previous artifact '+str(artifact))
        report['flows']={f:previous['flows'][f] for f in ('interface','map')}
        report['reused_completed_flows']=['interface','map'];report['source_build_started_at']=previous.get('source_build_started_at',previous['started_at'])
        flows=('pnr','pgm')
    else:flows=('interface','map','pnr','pgm') if args.flow=='all' else (args.flow,)
    if args.pnr_seed is not None or args.pnr_optimization_level is not None:
        # All previous map inputs were checked above before this one intentional
        # PNR-only edit. The mapped netlist and all synthesis/IO/SDC stay intact.
        project=HW/'Ti60_Multimodal.xml';previous_project=project.read_text(encoding='utf8')
        replacement=previous_project
        if args.pnr_seed is not None:
            replacement,n=re.subn(r'(name="seed" value=")\d+(" value_type="e_integer")',
                                 lambda m:m[1]+str(args.pnr_seed)+m[2],replacement)
            if n!=1:raise RuntimeError('Expected one PNR seed')
            report['placement_seed_only_change']=args.pnr_seed
        if args.pnr_optimization_level is not None:
            element='<efx:param name="optimization_level" value="'+args.pnr_optimization_level+'" value_type="e_option" />'
            replacement,n=re.subn(r'<efx:param name="optimization_level"[^>]*/>',element,replacement)
            if n>1:raise RuntimeError('Expected at most one PNR optimization level')
            if n==0:
                replacement,n=re.subn(r'(<efx:place_and_route[^>]*>)',lambda m:m[1]+'\n        '+element,replacement)
                if n!=1:raise RuntimeError('Expected one PNR section')
            report['pnr_optimization_level_only_change']=args.pnr_optimization_level
        project.write_text(replacement,encoding='utf8')
        initial=fingerprint();report['inputs_sha256_at_start']=initial
        project_at_start=project_settings(project)
    save()
    for flow in flows:
        log=out/f'{flow}_{stamp}.log';start=time.time()
        command=[str(EFX/'bin/efx_run.bat'),'Ti60_Multimodal.xml','--flow',flow]
        print('BUILD',flow,'LOG',log,flush=True)
        with log.open('wb') as f:
            proc=subprocess.Popen(command,cwd=HW,env=env,stdout=f,stderr=subprocess.STDOUT)
            while proc.poll() is None:
                try:proc.wait(timeout=30)
                except subprocess.TimeoutExpired:print('BUILD_RUNNING',flow,'elapsed_s',round(time.time()-start),flush=True)
        text=log.read_text(errors='replace')
        report['flows'][flow]=dict(exit_code=proc.returncode,elapsed_s=round(time.time()-start,2),log=str(log.relative_to(ROOT)))
        save()
        if proc.returncode:
            print(text[-9000:]);raise RuntimeError('FPGA '+flow+' failed: '+str(log))
        suffix={'interface':'.pt.sdc','map':'.map.rpt','pnr':'.timing.rpt','pgm':'.bit'}[flow]
        artifact=HW/'outflow'/('Ti60_Multimodal'+suffix)
        if not artifact.is_file() or artifact.stat().st_mtime<start-3:raise RuntimeError('Missing/stale '+str(artifact))
        if flow=='pnr':
            report.update(timing_summary(artifact));save()
        print('BUILD_PASS',flow,flush=True)
    if args.flow=='all':
        report.update(complete=True,passed=True,finished_at=datetime.datetime.now().isoformat())
        bit=HW/'outflow/Ti60_Multimodal.bit';report['bit_sha256']=hashlib.sha256(bit.read_bytes()).hexdigest()
        report['inputs_sha256']=fingerprint()
        if report['inputs_sha256']!=initial:
            changed={p for p in initial if initial[p]!=report['inputs_sha256'].get(p)}
            project_key=(HW/'Ti60_Multimodal.xml').relative_to(ROOT).as_posix()
            if changed!={project_key} or project_settings(HW/'Ti60_Multimodal.xml')!=project_at_start:
                raise RuntimeError('Hardware inputs changed during the build')
            report['project_metadata_or_serialization_rewritten_by_efinity']=True
    save();print(dest,flush=True)

if __name__=='__main__':main()
