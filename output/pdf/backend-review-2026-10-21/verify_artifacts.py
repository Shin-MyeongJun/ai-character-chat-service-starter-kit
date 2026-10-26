"""PDF text/geometry, contact sheets, input hash verification. Read-only backend."""
import hashlib,json,math,re,subprocess
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
import pdfplumber
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
d=json.loads((OUT/'inventory.json').read_text(encoding='utf8'))
changes=[]
for f in d['files']:
    p=ROOT/f['path']
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:changes.append(f['path'])
(OUT/'source-integrity.json').write_text(json.dumps({'changed_since_inventory':changes,'scope':'inventoried app/tests/alembic/init files','note':'No application code was edited by this review.'},ensure_ascii=False,indent=2),encoding='utf8')
qa=OUT/'qa';qa.mkdir(exist_ok=True)
pages=sorted((qa/'final').glob('page-*.png'))
for offset in range(0,len(pages),12):
    chunk=pages[offset:offset+12];sheet=Image.new('RGB',(1008,1500),'#DDE5E9');draw=ImageDraw.Draw(sheet)
    for n,path in enumerate(chunk):
        im=Image.open(path).convert('RGB');im.thumbnail((246,350));x=(n%4)*252+(252-im.width)//2;y=(n//4)*500
        sheet.paste(im,(x,y+22));draw.text(((n%4)*252+8,y+4),path.stem,fill='black')
    sheet.save(qa/f'contact-{offset//12+1:02}.jpg',quality=88)
violations=[];counts=[];selected={};alltext=[]
with pdfplumber.open(OUT/'backend-review.pdf') as pdf:
    for n,page in enumerate(pdf.pages,1):
        text=page.extract_text() or '';alltext.append(text);counts.append(len(text))
        bad=[c for c in page.chars if c['x0']<40 or c['x1']>555 or c['top']<10 or c['bottom']>829]
        if bad:violations.append({'page':n,'chars':''.join(c['text'] for c in bad)[:200]})
        for needle in ['시스템 구성과 실행 호출','답변 생성: 예약','전체 ERD:','content/product 상세 FK','F01 ·','부록 B. 전체 테이블 사전']:
            if n>3 and needle in text and needle not in selected:selected[needle]=n
result={'pages':len(counts),'characters':sum(counts),'page_character_counts':counts,'geometry_violations':violations,'selected_pages':selected,'korean_searchable':all(x in '\n'.join(alltext) for x in ['백엔드','아키텍처','크레딧','트랜잭션']), 'source_changes':changes}
(qa/'qa-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
(qa/'extracted.txt').write_text('\n\n'.join(alltext),encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='page_character_counts'},ensure_ascii=False))
