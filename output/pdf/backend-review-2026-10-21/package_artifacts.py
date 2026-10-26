"""Package this report's editable sources, diagrams, evidence and visual QA."""
from pathlib import Path
import hashlib, json, zipfile

OUT=Path(__file__).resolve().parent
excluded={'backend-review-source.zip','manifest.json','run_checks.py','local-pytest.pid','pytest-local.log','test-progress.log'}
files=[]
for path in OUT.rglob('*'):
    if not path.is_file() or path.name in excluded or 'pytest-temp' in path.parts or '__pycache__' in path.parts:
        continue
    # Old render passes are retained locally but not included in the delivery.
    if path.parent==OUT/'qa' and path.name.startswith('page-'):
        continue
    files.append(path)
manifest={p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
with zipfile.ZipFile(OUT/'backend-review-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for path in files+[OUT/'manifest.json']:
        archive.write(path,path.relative_to(OUT).as_posix())
with zipfile.ZipFile(OUT/'backend-review-source.zip') as archive:
    assert archive.testzip() is None
print(f'Packaged {len(files)+1} files; archive CRC verified.')
