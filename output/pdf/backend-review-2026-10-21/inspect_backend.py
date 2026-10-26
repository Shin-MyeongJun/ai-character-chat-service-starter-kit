"""Read-only source/ORM/HTTP inventory. Run with repository .venv Python."""
import ast, hashlib, inspect, json, os, subprocess, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'apps/api'))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
files = []
for base in ['apps/api/app', 'apps/api/tests', 'apps/api/alembic', 'infra/postgres/init']:
    for p in sorted((ROOT/base).rglob('*')):
        if p.suffix not in {'.py','.sql','.md','.json'} or '__pycache__' in p.parts: continue
        raw = p.read_bytes(); s = raw.decode('utf-8-sig')
        f = dict(path=p.relative_to(ROOT).as_posix(), lines=len(s.splitlines()), sha256=hashlib.sha256(raw).hexdigest())
        if p.suffix == '.py':
            t = ast.parse(s)
            f['symbols'] = [{'name':n.name,'line':n.lineno,'end':n.end_lineno,'kind':type(n).__name__} for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
            f['imports'] = [{'module':n.module or '', 'names':[a.name for a in n.names], 'line':n.lineno} for n in ast.walk(t) if isinstance(n,ast.ImportFrom)]
        files.append(f)
import app.db.models
from app.db.base import Base
tables = []
for t in sorted(Base.metadata.tables.values(), key=lambda x:x.name):
    tables.append(dict(name=t.name, columns=[dict(name=c.name,type=str(c.type),nullable=c.nullable,pk=c.primary_key,default=str(getattr(c.server_default,'arg',c.server_default)) if c.server_default is not None else None) for c in t.columns],
        fks=[dict(columns=[e.parent.name for e in fk.elements], target=fk.referred_table.name, target_columns=[e.column.name for e in fk.elements], ondelete=fk.ondelete or 'NO ACTION',onupdate=fk.onupdate or 'NO ACTION') for fk in t.foreign_key_constraints],
        constraints=[dict(kind=type(c).__name__, name=c.name, columns=[x.name for x in c.columns],sql=str(c.sqltext) if hasattr(c,'sqltext') else None) for c in t.constraints],
        indexes=[dict(name=x.name,unique=x.unique,columns=[str(e) for e in x.expressions],where=str(x.dialect_options['postgresql'].get('where'))) for x in t.indexes]))
from app.main import create_app
app = create_app()
routes = []
def deps(d):
    result=[]
    for sub in d.dependencies:
        fn=sub.call
        result.append(getattr(fn,'__module__','')+'.'+getattr(fn,'__name__',str(fn)))
        result.extend(deps(sub))
    return result
def flatten(routes, prefix=''):
    for r in routes:
        if hasattr(r,'original_router'):
            yield from flatten(r.original_router.routes, prefix+r.include_context.prefix)
        else:yield r,prefix
for r,prefix in flatten(app.routes):
    if not hasattr(r,'dependant'):continue
    routes.append(dict(path=prefix+r.path, methods=sorted(r.methods), function=r.endpoint.__name__,file=Path(inspect.getfile(r.endpoint)).relative_to(ROOT).as_posix(),line=inspect.getsourcelines(r.endpoint)[1],dependencies=deps(r.dependant)))
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()
data=dict(date='2026-10-21',branch=git('branch','--show-current'),commit=git('rev-parse','HEAD'),status=git('status','--porcelain','--untracked-files=no').splitlines(),files=files,tables=tables,routes=routes,overrides=[x.__module__+'.'+x.__name__ for x in app.dependency_overrides])
(OUT/'inventory.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files), python=sum(f['path'].endswith('.py') for f in files),tables=len(tables),routes=len(routes),app_lines=sum(f['lines'] for f in files if f['path'].startswith('apps/api/app/')))))
