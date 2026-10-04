"""Fingerprint a completed run without modifying its raw data or source snapshot."""
from pathlib import Path
import sys,json,hashlib
p=Path(sys.argv[1]).resolve();assert p.is_dir() and p.name.startswith('run_')
manifest={f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
 for f in sorted(p.rglob('*')) if f.is_file() and f.name!='archive_sha256.json'}
(p/'archive_sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Archived',len(manifest),'files:',p)
