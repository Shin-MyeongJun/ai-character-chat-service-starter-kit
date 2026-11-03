"""Re-audit evidence; never modifies application or previous audit files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8')

def snapshot():
    prefix = AUDIT.relative_to(ROOT).as_posix() + '/'
    paths = git('ls-files', '-co', '--exclude-standard', '-z').split('\0')
    return {
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'head': git('rev-parse', 'HEAD').strip(),
        'status': git('status', '--porcelain=v1').splitlines(),
        'sha256': {p: sha(ROOT / p) for p in sorted(set(paths))
                   if p and not p.startswith((prefix, '.env')) and (ROOT / p).is_file()},
    }

def main():
    mode = sys.argv[1]
    current = snapshot()
    if mode == 'start':
        with (AUDIT / 'baseline-start.json').open('x', encoding='utf-8') as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        (AUDIT / 'git-diff-stat.txt').write_text(git('diff', '--stat'), encoding='utf-8')
    elif mode == 'end':
        start = json.loads((AUDIT / 'baseline-start.json').read_text(encoding='utf-8'))
        current['comparison'] = {
            'head_unchanged': start['head'] == current['head'],
            'changed': [p for p, h in start['sha256'].items() if p in current['sha256'] and h != current['sha256'][p]],
            'missing': sorted(set(start['sha256']) - set(current['sha256'])),
            'new_outside_audit': sorted(set(current['sha256']) - set(start['sha256'])),
        }
        current['audit_sha256'] = {p.relative_to(AUDIT).as_posix(): sha(p)
            for p in sorted(AUDIT.rglob('*')) if p.is_file() and '__pycache__' not in str(p) and p.name != 'baseline-end.json'}
        (AUDIT / 'baseline-end.json').write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(current['comparison']))
    print(f"baseline_files={len(current['sha256'])} head={current['head']}")

if __name__ == '__main__':
    main()
