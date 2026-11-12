const createdNodeIds=[];
const page=await figma.getNodeByIdAsync(STATE.pages.library);await figma.setCurrentPageAsync(page);
await Promise.all(['Regular','Medium','Bold'].map(style=>figma.loadFontAsync({family:'Noto Sans KR',style})));
const variables={};
for(const [theme,roles] of Object.entries(STATE.colors)){variables[theme]={};for(const [role,id] of Object.entries(roles))variables[theme][role]=await figma.variables.getVariableByIdAsync(id);}
const geometry={};for(const [name,id] of Object.entries(STATE.geometry))geometry[name]=await figma.variables.getVariableByIdAsync(id);
function record(n){createdNodeIds.push(n.id);return n;}
function paint(theme,role){return figma.variables.setBoundVariableForPaint({type:'SOLID',color:{r:0,g:0,b:0}},'color',variables[theme][role]);}
function fill(n,theme,role){n.fills=role?[paint(theme,role)]:[];}
function gap(n,v){n.setBoundVariable('itemSpacing',geometry['space/'+v]);}
function pad(n,v){for(const k of ['paddingTop','paddingBottom','paddingLeft','paddingRight'])n.setBoundVariable(k,geometry['space/'+v]);}
function radius(n,v){for(const k of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])n.setBoundVariable(k,geometry['radius/'+v]);}
function auto(name,dir='VERTICAL',width=342){const n=record(figma.createAutoLayout(dir));n.name=name;n.resize(width,1);n.primaryAxisSizingMode=dir==='VERTICAL'?'AUTO':'FIXED';n.counterAxisSizingMode=dir==='VERTICAL'?'FIXED':'AUTO';n.fills=[];return n;}
function component(name,dir,width){const n=record(figma.createComponent());n.name=name;n.layoutMode=dir;n.resize(width,1);n.primaryAxisSizingMode='AUTO';n.counterAxisSizingMode='FIXED';n.fills=[];return n;}
async function text(parent,name,value,style,theme,role,width){const n=record(figma.createText());n.name=name;await n.setTextStyleIdAsync(STATE.styles[style]);n.characters=value;fill(n,theme,role);parent.appendChild(n);if(width){n.textAutoResize='HEIGHT';n.resize(width,n.height);n.layoutSizingHorizontal='FILL';}else n.textAutoResize='WIDTH_AND_HEIGHT';return n;}
function inst(parent,c,w){const n=record(c.createInstance());parent.appendChild(n);if(w)n.resize(w,n.height);return n;}
const paths={back:'<path d="m14 6-6 6 6 6"/>',settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2" fill="white"/><circle cx="15" cy="17" r="2" fill="white"/>',tools:'<path d="M12 5v14M5 12h14"/>',send:'<path d="M12 19V5m-6 6 6-6 6 6"/>',down:'<path d="M12 5v14m-6-6 6 6 6-6"/>'};
const icons={},buttons={},headers={},composers={},characters={},users={},latest={};
let y=160;
for(const theme of ['Light','Dark']){
 icons[theme]={};
 for(const [name,path] of Object.entries(paths)){
  const c=component('Icon/'+name+'/'+theme,'HORIZONTAL',24);c.resize(24,24);c.primaryAxisSizingMode='FIXED';c.counterAxisAlignItems='CENTER';c.primaryAxisAlignItems='CENTER';
  const v=record(figma.createNodeFromSvg('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#202024" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">'+path+'</svg>'));c.appendChild(v);for(const d of [v,...v.findAll(()=>true)]){createdNodeIds.push(d.id);if('strokes' in d&&Array.isArray(d.strokes)&&d.strokes.length)d.strokes=[paint(theme,'text')];if('fills' in d&&Array.isArray(d.fills)&&d.fills.length)d.fills=[paint(theme,'surface')];}c.x=100+Object.keys(icons[theme]).length*68;c.y=y;icons[theme][name]=c;
 }
 buttons[theme]={};
 for(const role of ['neutral','disabled','primary']){
  const c=component('Theme='+theme+', Style='+role,'HORIZONTAL',44);c.resize(44,44);c.primaryAxisSizingMode='FIXED';c.counterAxisAlignItems='CENTER';c.primaryAxisAlignItems='CENTER';radius(c,8);fill(c,theme,role==='primary'?'action':role==='disabled'?'disabled':null);
  const i=inst(c,icons[theme][role==='neutral'?'back':'send']);const key=c.addComponentProperty('Icon','INSTANCE_SWAP',i.mainComponent.id);i.componentPropertyReferences={mainComponent:key};
  if(role!=='neutral')for(const d of i.findAll(()=>true))if('strokes' in d&&Array.isArray(d.strokes)&&d.strokes.length)d.strokes=[paint(theme,role==='primary'?'onAction':'secondary')];
  buttons[theme][role]=c;
 }
 const bset=record(figma.combineAsVariants(Object.values(buttons[theme]),page));bset.name='Control / '+theme;bset.x=100;bset.y=y+72;bset.resize(260,116);bset.children.forEach((c,i)=>{c.x=16+i*76;c.y=40;});
 const u=component('Message / User / '+theme,'VERTICAL',270);pad(u,12);radius(u,12);fill(u,theme,'selection');gap(u,4);
 const ut=await text(u,'사용자 대사','잊어버린 이야기를 찾으러 왔어요.\n어디서부터 시작하면 될까요?','UI/Body',theme,'text',246);const ukey=u.addComponentProperty('Message','TEXT',ut.characters);ut.componentPropertyReferences={characters:ukey};u.x=420;u.y=y;users[theme]=u;
 const l=component('Navigation / Latest / '+theme,'HORIZONTAL',172);pad(l,8);gap(l,4);radius(l,8);l.counterAxisAlignItems='CENTER';l.primaryAxisAlignItems='CENTER';fill(l,theme,'surface');l.strokes=[paint(theme,'border')];await text(l,'최신 메시지로','최신 메시지로','UI/Caption',theme,'text');inst(l,icons[theme].down);l.x=420;l.y=y+120;latest[theme]=l;
 for(const device of ['Mobile','Desktop']){
  const mobile=device==='Mobile',w=mobile?390:1440,bw=mobile?342:680;
  const h=component('Theme='+theme+', Device='+device,'HORIZONTAL',w);h.resize(w,mobile?56:72);h.primaryAxisSizingMode='FIXED';pad(h,mobile?8:16);gap(h,8);h.counterAxisAlignItems='CENTER';fill(h,theme,'canvas');h.strokes=[paint(theme,'border')];h.strokeTopWeight=0;h.strokeLeftWeight=0;h.strokeRightWeight=0;h.strokeBottomWeight=1;
  h.paddingTop=mobile?4:12;h.paddingBottom=mobile?4:12;
  inst(h,buttons[theme].neutral);
  if(!mobile)await text(h,'모서리','모서리','UI/Title',theme,'text');
  const title=auto('작품과 캐릭터','VERTICAL',mobile?270:1100);h.appendChild(title);title.layoutSizingHorizontal='FILL';gap(title,0);
  await text(title,'작품명 · 긴 이름 말줄임','비가 그치면, 기록실에서','UI/Label',theme,'text',mobile?262:1000);
  await text(title,'캐릭터명','에린 · 기록실 안내인','UI/Caption',theme,'secondary',mobile?262:1000);
  const setting=inst(h,buttons[theme].neutral);const si=setting.findAllWithCriteria({types:['INSTANCE']})[0];si.swapComponent(icons[theme].settings);setting.name='대화 설정';headers[theme+device]=h;
  const c=component('Theme='+theme+', Device='+device,'VERTICAL',mobile?358:680);pad(c,12);gap(c,8);radius(c,12);fill(c,theme,'surface');c.strokes=[paint(theme,'border')];
  const line=auto('작성란','HORIZONTAL',(mobile?358:680)-24);c.appendChild(line);line.layoutSizingHorizontal='FILL';gap(line,8);line.counterAxisAlignItems='CENTER';
  const prompt=await text(line,'입력 · 빈 상태','에린에게 이야기를 이어가세요…','UI/Body',theme,'secondary',mobile?270:590);prompt.layoutSizingHorizontal='FILL';
  const actions=auto('작성 도구와 전송','HORIZONTAL',(mobile?358:680)-24);c.appendChild(actions);actions.layoutSizingHorizontal='FILL';gap(actions,8);actions.counterAxisAlignItems='CENTER';
  const tool=inst(actions,buttons[theme].neutral);tool.findAllWithCriteria({types:['INSTANCE']})[0].swapComponent(icons[theme].tools);tool.name='입력 보조 · 로어 선택';
  const help=await text(actions,'자동 저장 안내',mobile?'나의 다음 장면을 천천히':'Enter 전송 · Shift + Enter 줄바꿈','UI/Caption',theme,'secondary',mobile?206:500);help.layoutSizingHorizontal='FILL';
  const send=inst(actions,buttons[theme].disabled);send.name='전송 · 입력하면 활성화';composers[theme+device]=c;
  const a=component('Theme='+theme+', Device='+device,'VERTICAL',bw);gap(a,16);
  const byline=auto('캐릭터 정보','HORIZONTAL',bw);a.appendChild(byline);byline.layoutSizingHorizontal='FILL';gap(byline,8);byline.counterAxisAlignItems='CENTER';await text(byline,'캐릭터 이름','에린','UI/Label',theme,'text');await text(byline,'응답 시간','방금','UI/Caption',theme,'secondary');
  for(let i=0;i<CONTENT.length;i++){const p=CONTENT[i];await text(a,(p.type==='dialogue'?'대사':'서술')+' '+(i+1),p.text,p.type==='dialogue'?'Reading/Dialogue':'Reading/Narration',theme,p.type==='dialogue'?'text':'secondary',bw);}
  characters[theme+device]=a;
 }
 y+=340;
}
const families={};
for(const [name,map] of Object.entries({Header:headers,Composer:composers,Character:characters})){
 const set=record(figma.combineAsVariants(Object.values(map),page));set.name='Chat / '+name;set.x=name==='Header'?100:name==='Composer'?1700:2600;set.y=1000;
 let yy=40;for(const c of set.children){c.x=24;c.y=yy;yy+=c.height+40;}set.resize(Math.max(...set.children.map(c=>c.width))+48,yy);families[name]=set.id;
}
const components={icons:Object.fromEntries(Object.entries(icons).map(([th,cs])=>[th,Object.fromEntries(Object.entries(cs).map(([k,v])=>[k,v.id]))])),buttons:Object.fromEntries(Object.entries(buttons).map(([th,cs])=>[th,Object.fromEntries(Object.entries(cs).map(([k,v])=>[k,v.id]))])),headers:Object.fromEntries(Object.entries(headers).map(([k,v])=>[k,v.id])),composers:Object.fromEntries(Object.entries(composers).map(([k,v])=>[k,v.id])),characters:Object.fromEntries(Object.entries(characters).map(([k,v])=>[k,v.id])),users:Object.fromEntries(Object.entries(users).map(([k,v])=>[k,v.id])),latest:Object.fromEntries(Object.entries(latest).map(([k,v])=>[k,v.id]))};
return {createdNodeIds:[...new Set(createdNodeIds)],components,families,answerCharacters:CONTENT.map(p=>p.text).join('\n\n').length,characterBounds:Object.fromEntries(Object.entries(characters).map(([k,v])=>[k,{width:v.width,height:v.height}])),font:'Noto Sans KR'};
