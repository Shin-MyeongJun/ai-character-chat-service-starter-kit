// Append after revision-shared.js, with BASE and WRITING injected.
const sec=section('03 · 대화 설정 | 모바일 시트와 PC 패널',2320,2310,3080,3230);
await heading(sec,'이야기를 이어가는 데 필요한 설정','03  /  유저 노트 · 답변 길이와 생각 깊이 · 요약 메모리. 대화 문맥은 패널 뒤 또는 옆에 남습니다.');
const kinds={menu:'대화 설정',note:'유저 노트',output:'답변 길이',memory:'요약 메모리'};
const options=[
 ['note','유저 노트','에린이 기억할 내용을 정해요.'],
 ['output','답변 길이','한 번의 답변 길이와 생각 깊이를 정해요.'],
 ['memory','요약 메모리','지금까지 쌓인 이야기를 확인해요.']
];
const mBase=await get(BASE.screens.screens.LightMobile);
const dBase=await get(BASE.screens.screens.DarkDesktop);
const latest=await get(WRITING.screens.latest);
const screens={}, connections=[];
function stretch(n,w,vertical){
 const h=n.height;n.resize(w,h);n.layoutSizingHorizontal='FIXED';n.layoutSizingVertical=vertical;
}
async function row(p,th,copy,detail,value='›'){
 const width=p.width-p.paddingLeft-p.paddingRight;
 const r=frame(copy,width,'HORIZONTAL',p);r.itemSpacing=8;r.counterAxisAlignItems='CENTER';pad(r,0,9);rule(r,th,'bottom');
 const l=frame('설정 항목',width-36,'VERTICAL',r);l.layoutSizingHorizontal='FILL';l.itemSpacing=2;
 await t(l,copy,'UI/Label',th);
 if(detail)await t(l,detail,'UI/Caption',th,'secondary',true);
 await t(r,value,'UI/Caption',th,'secondary');return r;
}
async function title(p,th,key){
 const w=p.width-p.paddingLeft-p.paddingRight;
 const r=frame('설정 화면 제목',w,'HORIZONTAL',p);r.counterAxisAlignItems='CENTER';r.itemSpacing=4;
 let back=null;if(key!=='menu')back=await button(r,'‹',th,{w:44,ghost:true});
 await t(r,kinds[key],'UI/Title',th);spacer(r);
 const close=await button(r,'×',th,{w:44,ghost:true});
 return {back,close};
}
async function segment(p,th,name,values,selected){
 const w=p.width-p.paddingLeft-p.paddingRight;
 const s=frame(name,w,'VERTICAL',p);s.itemSpacing=8;await t(s,name,'UI/Label',th);
 const r=frame('선택지',w,'HORIZONTAL',s);r.itemSpacing=8;
 for(const value of values)await button(r,value,th,{w:Math.floor((w-8*(values.length-1))/values.length),primary:value===selected});
 return s;
}
async function memoryCard(p,th,title,copy){
 const width=p.width-p.paddingLeft-p.paddingRight;
 const c=frame(title,width,'VERTICAL',p);pad(c,12);c.itemSpacing=8;c.cornerRadius=8;fill(c,th,'subtle');c.strokes=[paint(th,'border')];
 await t(c,title,'UI/Label',th);await t(c,copy,'UI/Body',th,'secondary',true);return c;
}
async function make(base,mobile,th,key,x,y){
 const root=clone(base,sec,(mobile?'390':'1440')+' · '+kinds[key]+' / '+th,x,y);
 removeRootHotspots(root);
 let veil=null;
 if(mobile)veil=dim(root,.32);
 else{
  stretch(view(root),1120,'FILL');
  stretch(footer(root),1120,'HUG');
  const jump=root.children.find(n=>n.name.startsWith('최신 메시지로'));jump.x=(1120-jump.width)/2;jump.y=root.height-footer(root).height-56;
 }
 const width=mobile?390:320;
 const p=panel(mobile?'대화 설정 · 하단 시트':'대화 설정 · 우측 패널',root,width,th,mobile?0:1120,mobile?0:72);
 if(mobile){p.paddingTop=10;p.paddingBottom=34;p.bottomLeftRadius=0;p.bottomRightRadius=0;}
 else{p.cornerRadius=0;rule(p,th,'left');p.paddingTop=16;}
 p.itemSpacing=12;
 if(mobile){
  const h=frame('시트 손잡이 영역',width-40,'HORIZONTAL',p);h.primaryAxisAlignItems='CENTER';
  const b=rec(figma.createRectangle());h.appendChild(b);b.resize(32,4);b.cornerRadius=2;b.fills=[paint(th,'border')];
 }
 const {back,close}=await title(p,th,key);const widthInner=width-40;
 const rows={},labels=[];
 if(key==='menu'){
  const about=frame('현재 대화 정보',widthInner,'VERTICAL',p);pad(about,12);about.itemSpacing=3;about.cornerRadius=8;fill(about,th,'subtle');
  await t(about,'비가 그치면, 기록실에서','UI/Label',th,'text',true);
  await t(about,'에린 · 기록실 안내인','UI/Caption',th,'secondary');
  const group=frame('대화 설정 항목',widthInner,'VERTICAL',p);
  for(const [k,name,copy] of options)rows[k]=await row(group,th,name,copy);
  const reading=frame('읽기 설정',widthInner,'VERTICAL',p);reading.itemSpacing=4;
  await t(reading,'읽기','UI/Caption',th,'secondary');
  await row(reading,th,'글자 크기 · 행간',null,'16px · 보통');
  await row(reading,th,'테마',null,th==='Light'?'라이트':'다크');
 }else if(key==='note'){
  await t(p,'에린이 이 대화에서 기억했으면 하는 내용을 적어보세요.','UI/Body',th,'secondary',true);
  const f=frame('유저 노트 작성란',widthInner,'VERTICAL',p);pad(f,12);f.paddingBottom=36;f.cornerRadius=8;f.strokes=[paint(th,'border')];fill(f,th,'canvas');
  await t(f,'에린은 손님에게 존댓말을 쓴다.\n기록실 문은 비가 내릴 때만 열린다.','UI/Body',th,'text',true);
 }else if(key==='output'){
  await t(p,'이 대화에서 한 번에 받을 답변의 최대 길이를 정해요.','UI/Body',th,'secondary',true);
  await segment(p,th,'최대 답변 길이',['짧게','기본','길게'],'기본');
  await segment(p,th,'생각 깊이',['기본','깊게'],'기본');
  await t(p,'모델과 선택한 길이에 따라 사용 크레딧이 달라질 수 있어요.','UI/Caption',th,'secondary',true);
 }else{
  await t(p,'대화에서 이어갈 내용과 기억할 사실을 살펴보세요.','UI/Body',th,'secondary',true);
  await memoryCard(p,th,'최근 요약','에린이 은색 열쇠를 건넸다. 맞은편 문을 열기 전에 편지를 읽을지 정하려 한다.');
  await memoryCard(p,th,'장기 기억','에린은 기록실의 안내인이다. 손님은 잊어버린 이야기를 찾으러 왔다.');
 }
 if(key==='note'||key==='output'){
  const r=frame('설정 적용',widthInner,'HORIZONTAL',p);spacer(r);
  rows.apply=await button(r,'적용',th,{w:88,primary:true});
 }
 if(mobile){p.y=root.height-p.height;}
 else{p.resize(width,root.height-72);p.primaryAxisSizingMode='FIXED';p.clipsContent=true;}
 return {root,p,back,close,veil,rows,labels};
}
for(const [device,mobile,th,base] of [['Mobile',true,'Light',mBase],['Desktop',false,'Dark',dBase]]){
 const variants={};
 for(const [i,key] of Object.keys(kinds).entries()){
  const x=mobile?48+452*i:48+1492*(i%2);
  const y=mobile?164:1110+1030*Math.floor(i/2);
  variants[key]=await make(base,mobile,th,key,x,y);
  await label(sec,x,y-33,(mobile?'모바일 / 라이트':'PC / 다크')+'   ·   '+kinds[key]);
  screens[device+key]=variants[key].root.id;
 }
 for(const [k,v]of Object.entries(variants)){
  await goto(v.close,base);
  if(v.veil)await goto(v.veil,base);
  if(v.back)await goto(v.back,variants.menu.root);
  if(v.rows.apply)await goto(v.rows.apply,variants.menu.root);
  if(k==='menu')for(const [key]of options)await goto(v.rows[key],variants[key].root);
  connections.push({id:v.root.id,width:v.root.width,height:v.root.height,panel:{id:v.p.id,x:v.p.x,y:v.p.y,width:v.p.width,height:v.p.height}});
 }
 for(const root of mobile?[base,latest]:[base]){
  const target=named(root,'대화 설정');await goto(hotspot(root,target,'프로토타입 · 대화 설정'),variants.menu.root);
 }
}
const flows=new Map(page.flowStartingPoints.map(f=>[f.nodeId,f.name]));
for(const [id,name]of [[screens.Mobilemenu,'모바일 v2 · 대화 설정'],[screens.Desktopmenu,'PC v2 · 대화 설정']])flows.set(id,name);
page.flowStartingPoints=[...flows].filter(([id])=>[...Object.values(BASE.screens.screens),WRITING.screens.latest,screens.Mobilemenu,screens.Desktopmenu].includes(id)).map(([nodeId,name])=>({nodeId,name}));
mutatedNodeIds.push(page.id);
figma.viewport.scrollAndZoomIntoView([await get(screens.Mobilemenu),await get(screens.Desktopmenu)]);
return {createdNodeIds:[...new Set(createdNodeIds)],mutatedNodeIds:[...new Set(mutatedNodeIds)],removedNodeIds:[...new Set(removedNodeIds)],section:sec.id,screens,connections};
