from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont
import shutil

root = Path(__file__).parent
src = root / 'exports-final'
out = Path('docs/assets/admin-web-design')
out.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 20)
files = sorted(p for p in src.rglob('*.png') if '디자인 인계' not in p.name)
sheet = Image.new('RGB', (1800, ((len(files)+3)//4)*410), '#e9e9ed')
draw = ImageDraw.Draw(sheet)
for i, path in enumerate(files):
    im = Image.open(path).convert('RGB')
    im.thumbnail((426, 352))
    x, y = (i%4)*450+12, (i//4)*410+12
    sheet.paste(im, (x+(426-im.width)//2, y))
    label = path.parent.name + ' / ' + path.stem if path.parent != src else path.stem
    draw.text((x, y+360), label[:28], fill='#202024', font=font)
sheet.save(out/'all-screens.png')
main = [('01 · 관리자 로그인.png','login.png'), ('02 · 생성 프롬프트 · data/1440.png','list.png'), ('03 · 생성 프롬프트 상세 · roles/1440.png','detail.png'), ('03 · 생성 프롬프트 상세 · missing/1440.png','missing.png')]
preview = Image.new('RGB',(1800,670),'#eeeeF1')
pd = ImageDraw.Draw(preview)
for i, (a,b) in enumerate(main[:3]):
    path = src/a
    shutil.copy2(path,out/b)
    im = Image.open(path).convert('RGB')
    im.thumbnail((576,590))
    preview.paste(im,(i*600+12,48))
    pd.text((i*600+14,10), ['관리자 로그인','생성 프롬프트 목록','생성 프롬프트 상세'][i],font=font,fill='#202024')
shutil.copy2(src/main[3][0],out/main[3][1])
preview.save(out/'overview.png')
print(f'{len(files)} screens; previews: {out.resolve()}')
