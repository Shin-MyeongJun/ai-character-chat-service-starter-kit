"""Render editable Markdown + diagram JSON to searchable Korean PDF. No network."""
import html,json,math,re,time,io
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak,Table,TableStyle,KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing,Rect,Line,String,Polygon,Circle
from reportlab.graphics import renderPDF,renderSVG

OUT=Path(__file__).resolve().parent
FONT='Malgun Gothic';BOLD='Malgun Gothic Bold'
pdfmetrics.registerFont(TTFont(FONT,'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont(BOLD,'C:/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily(FONT,normal=FONT,bold=BOLD,italic=FONT,boldItalic=BOLD)
NAVY=colors.HexColor('#18354A');TEAL=colors.HexColor('#087F8C');LIGHT=colors.HexColor('#EDF5F7');GREY=colors.HexColor('#516473')
W=503

def write_retry(path,content):
    for attempt in range(5):
        try:
            path.write_bytes(content.encode('utf8') if isinstance(content,str) else content)
            return
        except OSError:
            if attempt==4:raise
            time.sleep(.3)
def wrap(s,width,size=9):
    lines=[];line=''
    for token in re.findall(r'[A-Za-z0-9_./+:-]+|\n|[^\S\n]+|.',str(s)):
        if token=='\n':lines.append(line.rstrip());line='';continue
        chunks=[token] if pdfmetrics.stringWidth(token,FONT,size)<=width else list(token)
        for c in chunks:
            if pdfmetrics.stringWidth(line+c,FONT,size)>width and line:
                lines.append(line.rstrip());line=c.lstrip()
            else:line+=c
    if line:lines.append(line)
    return lines or ['']
def label(d,s,x,y,width,size=9,color=NAVY,center=False,bold=False):
    for line in wrap(s,width,size):
        d.add(String(x+width/2 if center else x,y,line,fontName=BOLD if bold else FONT,fontSize=size,fillColor=color,textAnchor='middle' if center else 'start'));y-=size*1.35
    return y
def arrow(d,x1,y1,x2,y2,color=TEAL):
    d.add(Line(x1,y1,x2,y2,strokeColor=color,strokeWidth=1))
    a=math.atan2(y2-y1,x2-x1);r=4
    d.add(Polygon([x2,y2,x2-r*math.cos(a-.5),y2-r*math.sin(a-.5),x2-r*math.cos(a+.5),y2-r*math.sin(a+.5)],fillColor=color,strokeColor=color))
def draw(data):
    kind=data['kind']
    if kind=='module':
        nodes=data['nodes'];n=len(nodes);cell=min(25,(W-210)/max(n,1));left=210;h=max(130,70+n*26)
        d=Drawing(W,h)
        label(d,'정적 import: 행의 모듈/계층 → 열의 번호',0,h-12,W,8.5)
        if data.get('count_label')=='tables':
            d=Drawing(W,h);label(d,'물리 FK: 행의 자식 도메인 → 열의 참조 도메인',0,h-12,W,8.5)
        for j in range(n):label(d,f'{j+1:02}',left+j*cell,h-38,cell,8,center=True)
        edge={tuple(e) for e in data['edges']}
        for i,node in enumerate(nodes):
            y=h-66-i*26
            text=f'{i+1:02} {node} ({data["counts"].get(node,0)})'
            label(d,text,0,y+4,202,8.2)
            for j,target in enumerate(nodes):
                d.add(Rect(left+j*cell,y-9,cell,22,fillColor=LIGHT if i==j else colors.white,strokeColor=colors.HexColor('#D7E4E8'),strokeWidth=.4))
                if (node,target) in edge:d.add(Circle(left+(j+.5)*cell,y+2,3,fillColor=TEAL,strokeColor=TEAL))
        label(d,'● 관계 있음 · 대각 음영은 자기 자신 · 괄호는 파일 수'+(' 대신 테이블 수' if data.get('count_label')=='tables' else ''),0,13,W,7.7)
    elif kind=='relations':
        rows=data['rows'];h=30+len(rows)*66;d=Drawing(W,h)
        label(d,'자식 FK → 부모 참조 · 아래 수량/삭제 정책은 ORM 선언 기준',0,h-12,W,8)
        for i,r in enumerate(rows):
            top=h-30-i*66;y=top-43
            for x,name in [(0,r['child']),(W-128,r['parent'])]:
                d.add(Rect(x,y,128,43,rx=4,ry=4,fillColor=LIGHT,strokeColor=colors.HexColor('#B6CED5'),strokeWidth=.6));label(d,name,x+6,top-12,116,8.0,center=True,bold=True)
            arrow(d,131,y+18,W-131,y+18)
            label(d,r['columns']+' → '+r['target'],136,top-5,W-272,7.4,center=True)
            label(d,'자식당 부모 '+r['parent_per_child']+' / 부모당 자식 '+r['child_per_parent'],132,y+5,W-264,7.1,center=True)
            label(d,'DELETE '+r['delete']+' · UPDATE '+r['update'],130,y-11,W-260,7.1,center=True,color=GREY)
    elif kind=='sequence':
        actors=data['actors'];n=len(actors);steps=data['steps'];h=86+len(steps)*48;d=Drawing(W,h);xs=[56+i*(W-112)/(n-1) for i in range(n)]
        for x,name in zip(xs,actors):
            d.add(Rect(max(0,x-56),h-38,112,34,rx=4,ry=4,fillColor=LIGHT,strokeColor=TEAL,strokeWidth=.6));label(d,name,max(0,x-56)+4,h-16,104,8,center=True,bold=True)
            d.add(Line(x,h-40,x,20,strokeColor=colors.HexColor('#B4C8CF'),strokeWidth=.6,strokeDashArray=[3,3]))
        for i,(a,b,text) in enumerate(steps):
            y=h-77-i*48
            if a==b:
                arrow(d,xs[a],y,xs[a]+40,y);arrow(d,xs[a]+40,y,xs[a]+40,y-13);arrow(d,xs[a]+40,y-13,xs[a],y-13)
                width=240;left=max(0,min(W-width,xs[a]-20))
                label(d,str(i+1)+'. '+text,left,y+23,width,7.5)
            else:
                arrow(d,xs[a],y,xs[b],y)
                left=min(xs[a],xs[b]);span=abs(xs[b]-xs[a]);
                width=max(span,180);left=max(0,min(W-width,left+(span-width)/2))
                label(d,str(i+1)+'. '+text,left,y+24,width,7.4,center=True)
        label(d,'실선 → 호출·요청 또는 반환 · 세로 점선: 참여자 · 위에서 아래로 실행 순서',0,5,W,7.2,color=GREY)
    else:
        nodes=data['nodes'];maxcol=max(x[2] for x in nodes);maxrow=max(x[3] for x in nodes);bw=140;bh=48;extra=30 if data.get('id')=='layers' else 0;h=80+maxrow*92+extra;d=Drawing(W,h)
        pos={id:(8+col*(W-bw-16)/max(maxcol,1),h-60-extra-row*92) for id,_,col,row in nodes}
        for a,b,txt in data['edges']:
            x,y=pos[a];xx,yy=pos[b]
            if data.get('id')=='layers' and a=='http' and b=='wf':
                points=[(x+bw/2,y+bh),(x+bw/2,h-20),(xx+bw/2,h-20),(xx+bw/2,yy+bh)]
                for start,end in zip(points[:-2],points[1:-1]):
                    d.add(Line(*start,*end,strokeColor=TEAL,strokeWidth=1))
                arrow(d,*points[-2],*points[-1]);label(d,txt,W/2-48,h-12,96,7.3,center=True)
                continue
            if data.get('id')=='system' and a=='workers' and b=='providers':
                # Route external worker calls below the database, avoiding SQL label.
                points=[(x,y+24),(2,y+24),(2,3),(xx+bw/2,3),(xx+bw/2,yy)]
                for start,end in zip(points[:-2],points[1:-1]):
                    d.add(Line(*start,*end,strokeColor=TEAL,strokeWidth=1))
                arrow(d,*points[-2],*points[-1]);label(d,txt,330,9,72,7.3,center=True)
                continue
            if abs(y-yy)<1:
                x1=x+bw if xx>x else x;x2=xx if xx>x else xx+bw;y1=y2=y+bh/2
            else:x1=x+bw/2;x2=xx+bw/2;y1=y if yy<y else y+bh;y2=yy+bh if yy<y else yy
            arrow(d,x1,y1,x2,y2)
            if data.get('id')=='system' and abs(y-yy)<1:
                label(d,txt,(x1+x2)/2-48,y+bh+6,96,7.3,center=True)
            elif data.get('id')=='system':
                label(d,txt,x1+8,(y1+y2)/2,70,7.3)
            else:label(d,txt,(x1+x2)/2-48,(y1+y2)/2+8,96,7.3,center=True)
        for id,title,_,_ in nodes:
            x,y=pos[id];d.add(Rect(x,y,bw,bh,rx=5,ry=5,fillColor=LIGHT,strokeColor=TEAL,strokeWidth=.7));label(d,title,x+7,y+bh-15,bw-14,9,center=True,bold=True)
    return d

ST={
'body':ParagraphStyle('body',fontName=FONT,fontSize=9,leading=14.5,textColor=NAVY,spaceAfter=8,wordWrap='CJK'),
'small':ParagraphStyle('small',fontName=FONT,fontSize=7.5,leading=11,textColor=GREY,spaceAfter=8,wordWrap='CJK'),
'h1':ParagraphStyle('h1',fontName=BOLD,fontSize=20,leading=27,textColor=NAVY,spaceAfter=16,keepWithNext=True,wordWrap='CJK'),
'h2':ParagraphStyle('h2',fontName=BOLD,fontSize=13,leading=19,textColor=TEAL,spaceBefore=12,spaceAfter=9,keepWithNext=True,wordWrap='CJK'),
'h3':ParagraphStyle('h3',fontName=BOLD,fontSize=10.5,leading=16,textColor=NAVY,spaceBefore=10,spaceAfter=6,keepWithNext=True,wordWrap='CJK'),
'cell':ParagraphStyle('cell',fontName=FONT,fontSize=8,leading=11.4,textColor=NAVY,wordWrap='CJK'),
'th':ParagraphStyle('th',fontName=BOLD,fontSize=8,leading=11.4,textColor=colors.white,wordWrap='CJK'),
'caption':ParagraphStyle('caption',fontName=BOLD,fontSize=9,leading=14,textColor=TEAL,spaceBefore=8,spaceAfter=8,keepWithNext=True,wordWrap='CJK')}
def para(s,style='body'):
    s=html.escape(s).replace('\n','<br/>')
    s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
    return Paragraph(s,ST[style])
class ReportDoc(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path) if isinstance(path,Path) else path,pagesize=A4,leftMargin=46,rightMargin=46,topMargin=46,bottomMargin=44,title='백엔드 아키텍처 및 코드 검토 보고서',author='Backend review',allowSplitting=1)
        frame=Frame(46,44,W,A4[1]-90,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0,id='body')
        self.addPageTemplates(PageTemplate(id='normal',frames=[frame],onPage=self.page))
    def page(self,c,doc):
        c.saveState();c.setStrokeColor(TEAL);c.setLineWidth(.7);c.line(46,A4[1]-29,549,A4[1]-29)
        c.setFont(FONT,7);c.setFillColor(GREY);c.drawString(46,A4[1]-23,'CHAT KIT  /  BACKEND REVIEW  /  2026-10-21')
        c.drawString(46,23,'현재 작업 트리 · 정적 분석 + 로컬 검증 · 운영 DB 미조회');c.drawRightString(549,23,str(doc.page));c.restoreState()
    def afterFlowable(self,flow):
        if hasattr(flow,'toclevel'):
            key=flow.bookmark;self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flow.getPlainText(),key,flow.toclevel,False)
            self.notify('TOCEntry',(flow.toclevel,flow.getPlainText(),self.page,key))

def main():
    for path in (OUT/'diagrams').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf8'));d=draw(data)
        write_retry(path.with_suffix('.pdf'),renderPDF.drawToString(d))
        write_retry(path.with_suffix('.svg'),renderSVG.drawToString(d))
    lines=(OUT/'backend-review.md').read_text(encoding='utf8').splitlines();story=[];i=0;headno=0;section='';cover=True
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line:continue
        if line=='[TOC]':
            story.append(PageBreak());story.append(para('목차','h1'));toc=TableOfContents();toc.levelStyles=[ParagraphStyle('toc1',fontName=BOLD,fontSize=10,leading=17,textColor=NAVY,spaceBefore=5),ParagraphStyle('toc2',fontName=FONT,fontSize=8.4,leading=13,leftIndent=12,textColor=GREY)]
            story.append(toc);cover=False;continue
        match=re.match(r'^(#{1,3}) (.*)',line)
        if match:
            level=len(match[1]);text=match[2]
            if level==1:
                if story and not cover:story.append(PageBreak())
                section=text
            q=para(text,'h'+str(level));headno+=1
            if not cover and (level==1 or (level==2 and not section.startswith('부록'))):q.toclevel=level-1;q.bookmark='h'+str(headno)
            story.append(q);continue
        match=re.match(r'!\[(.*?)\]\((.*?)\.svg\)',line)
        if match:
            data=json.loads((OUT/(match[2]+'.json')).read_text(encoding='utf8'));drawing=draw(data)
            story.append(para(match[1],'caption'));story.append(drawing);story.append(Spacer(1,10));continue
        if line.startswith('|'):
            rows=[line]
            while i<len(lines) and lines[i].strip().startswith('|'):rows.append(lines[i].strip());i+=1
            cells=[[c.strip() for c in row.strip('|').split('|')] for row in rows if not re.match(r'^\|[\s|:-]+\|$',row)]
            n=len(cells[0]);widths={2:[W*.30,W*.70],3:[W*.48,W*.30,W*.22]}.get(n,[W/n]*n)
            if cells[0][0]=='메서드 / 경로':widths=[W*.53,W*.47]
            if cells[0][0]=='서비스 파일':widths=[W*.34,W*.66]
            if cells[0][0]=='패턴 / 실제 코드 발췌':widths=[W*.48,W*.52]
            data=[[para(c,'th' if ri==0 else 'cell') for c in row] for ri,row in enumerate(cells)]
            t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT',splitByRow=1)
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#DBE6EB'))]));story.append(t);story.append(Spacer(1,9));continue
        group=[line]
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','![')) and not lines[i].startswith('- '):group.append(lines[i]);i+=1
        text='\n'.join(group)
        if text.startswith('- '):text='• '+text[2:]
        style='small' if text.startswith(('근거:','코드 근거:','원본:','- INDEX','- CHECK','- UNIQUE')) else 'body'
        story.append(para(text,style))
    buffer=io.BytesIO();ReportDoc(buffer).multiBuild(story)
    write_retry(OUT/'backend-review.pdf',buffer.getvalue())
    print('PDF generated',OUT/'backend-review.pdf')
if __name__=='__main__':main()
