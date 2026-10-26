"""Rasterize the report and each vector diagram with local Poppler. No network."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil, subprocess, tempfile, time

OUT = Path(__file__).resolve().parent
POPPLER = shutil.which('pdftoppm')
if not POPPLER:
    raise SystemExit('pdftoppm (Poppler) must be available on PATH.')
(OUT / 'qa/final').mkdir(parents=True, exist_ok=True)
def copy_retry(source, target):
    for attempt in range(8):
        try:
            shutil.copyfile(source,target)
            return
        except OSError:
            if attempt==7:raise
            time.sleep(.3)

with tempfile.TemporaryDirectory(prefix='raster-',dir=OUT/'qa') as temporary:
    staging=Path(temporary)
    subprocess.run([POPPLER, '-png', '-r', '85', str(OUT / 'backend-review.pdf'), str(staging/'page')], check=True)
    for source in staging.glob('page-*.png'):
        copy_retry(source,OUT/'qa/final'/source.name)
    def render_one(path):
        prefix=staging/path.stem
        subprocess.run([POPPLER, '-png', '-singlefile', '-scale-to', '1800', str(path), str(prefix)], check=True)
        copy_retry(prefix.with_suffix('.png'),path.with_suffix('.png'))
    paths = sorted((OUT / 'diagrams').glob('*.pdf'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(render_one, paths))
print(f'Rasterized report and {len(paths)} diagrams.')
