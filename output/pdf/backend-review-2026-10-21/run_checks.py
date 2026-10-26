"""Local-only verification; does not read .env or enable integration credentials."""
import os, subprocess, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
env=os.environ.copy()
for key in list(env):
    if key.startswith(('TEST_', 'RUN_', 'OPENAI_', 'ANTHROPIC_', 'VOYAGE_', 'AWS_', 'ASSET_', 'AUTH_', 'BILLING_')) or key in {'DATABASE_URL','PYTEST_ADDOPTS'}:env.pop(key,None)
env.update(PYTHONPATH=str(ROOT/'apps/api'), PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
commands={
 'pytest':[sys.executable,'-B','-m','pytest','apps/api/tests','-q','-p','pytest_asyncio.plugin','-p','no:cacheprovider','--basetemp',str(OUT/'test-temp'),'--junitxml',str(OUT/'test-results.xml')],
 'ruff':[sys.executable,'-B','-m','ruff','check','apps/api/app','apps/api/tests','--no-cache'],
 'alembic-heads':[sys.executable,'-B','-m','alembic','-c','apps/api/alembic.ini','heads'],
}
for name,cmd in commands.items():
    print('START',name,flush=True)
    result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    (OUT/(name+'.log')).write_text(result.stdout,encoding='utf-8')
    print(name,'exit',result.returncode,result.stdout[-1800:],flush=True)
