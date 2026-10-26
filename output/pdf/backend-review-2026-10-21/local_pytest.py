import os,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
for k in list(os.environ):
    if k.startswith(('TEST_', 'RUN_', 'VOYAGE_', 'OPENAI_', 'ANTHROPIC_', 'AWS_', 'AUTH_', 'ASSET_', 'BILLING_')) or k in {'DATABASE_URL','PYTEST_ADDOPTS','PYTEST_DISABLE_PLUGIN_AUTOLOAD'}:os.environ.pop(k,None)
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'apps/api'))
sys.path.insert(0,str(ROOT/'apps/api/tests'))
os.chdir(ROOT/'apps/api')
(OUT/'local-pytest.pid').write_text(str(os.getpid()))
import pytest
class Progress:
    def pytest_runtest_logreport(self,report):
        with (OUT/'test-progress.log').open('a',encoding='utf-8') as f:
            f.write(f'{report.nodeid} {report.when} {report.outcome}\n')
    def pytest_sessionfinish(self,session,exitstatus):
        (OUT/'test-exit.txt').write_text(str(exitstatus))
raise SystemExit(pytest.main(['tests','-q','-p','no:cacheprovider','--basetemp',str(OUT/'pytest-temp'),'--junitxml',str(OUT/'tests.xml')],plugins=[Progress()]))
