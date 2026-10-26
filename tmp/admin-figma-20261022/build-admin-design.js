// Figma-only design authoring. Run in Scripter in the new administrator file.
// No network, credentials, storage reads, application changes, or deletions.
// Reuses the inspected initial partial build: Studio variables/styles and 10 buttons.
// Refuses unrelated content or already-created screens; never deletes nodes.
// Adapted variant-grid construction from figma-generate-library helper scripts.
const created = [];
const changed = [];
const track = n => { created.push(n.id); return n; };
const page = figma.root.children.find(p=>p.name==='01 · 관리자 화면 및 상태') || figma.currentPage;
const initialButtonNames = ['Primary','Secondary'].flatMap(Style=>['Default','Hover','Focus','Disabled','Loading'].map(State=>'Style='+Style+', State='+State));
const unexpected = page.children.filter(n=>n.type!=='COMPONENT'||!initialButtonNames.includes(n.name));
if(unexpected.length)throw new Error('Unreviewed existing nodes: '+unexpected.map(n=>n.name+' ['+n.id+']').join(', '));
const localCollections=await figma.variables.getLocalVariableCollectionsAsync();
const localVariables=await figma.variables.getLocalVariablesAsync();
const localStyles=await figma.getLocalTextStylesAsync();
const fonts = await figma.listAvailableFontsAsync();
for (const style of ['Regular', 'Medium', 'Bold']) {
  if (!fonts.some(f => f.fontName.family === 'Noto Sans KR' && f.fontName.style === style)) {
    throw new Error('Required product font unavailable: Noto Sans KR ' + style);
  }
}
await Promise.all(['Regular', 'Medium', 'Bold'].map(style => figma.loadFontAsync({family:'Noto Sans KR', style})));
page.name = '01 · 관리자 화면 및 상태'; changed.push(page.id);
const hex = s => ({r:parseInt(s.slice(0,2),16)/255,g:parseInt(s.slice(2,4),16)/255,b:parseInt(s.slice(4,6),16)/255});
const palette = {canvas:'FFFFFF',sidebar:'F7F7F8',hover:'F1F1F3',border:'E5E5E8',text:'202024',secondary:'65656F',action:'252529',onAction:'FFFFFF',selection:'EEEEF1',positive:'3B6550',danger:'9D493E'};
function createVariableCollection(name, modes) {
  const existing=localCollections.filter(c=>c.name===name);
  if(existing.length>1)throw new Error('Duplicate variable collections: '+name);
  if(existing.length)return existing[0];
  const collection = figma.variables.createVariableCollection(name);
  collection.renameMode(collection.modes[0].modeId,modes[0]);
  return collection;
}
const prim = createVariableCollection('Admin · Primitives',['Value']);
const tokens = createVariableCollection('Admin · Studio Light',['Light']);
const V = {}, P = {};
function variable(name,type,value,scopes,css) {
  const p = localVariables.find(v=>v.variableCollectionId===prim.id&&v.name===name)||figma.variables.createVariable(name,prim,type); p.scopes=[];
  p.setValueForMode(prim.defaultModeId,value); P[name]=p;
  const v = localVariables.find(v=>v.variableCollectionId===tokens.id&&v.name===name)||figma.variables.createVariable(name,tokens,type); v.scopes=scopes;
  v.setValueForMode(tokens.defaultModeId,{type:'VARIABLE_ALIAS',id:p.id});
  v.setVariableCodeSyntax('WEB','var(--'+css+')'); V[name]=v;
}
for (const [key,value] of Object.entries(palette)) variable('color/'+key,'COLOR',hex(value),['FRAME_FILL','SHAPE_FILL','TEXT_FILL','STROKE_COLOR'],key==='onAction'?'on-action':key);
for (const n of [0,4,8,12,16,20,24,32,40,48]) variable('space/'+n,'FLOAT',n,['GAP'],'admin-space-'+n);
for (const n of [8,12,999]) variable('radius/'+n,'FLOAT',n,['CORNER_RADIUS'],'admin-radius-'+n);
function paint(key) { return figma.variables.setBoundVariableForPaint({type:'SOLID',color:hex(palette[key])},'color',V['color/'+key]); }
function fill(n,key) { n.fills=key?[paint(key)]:[]; }
function border(n,key='border',weight=1) { n.strokes=[paint(key)]; n.strokeWeight=weight; }
function round(n,r=8) { for(const p of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius']) n.setBoundVariable(p,V['radius/'+r]); }
function spacing(n,gap=0,pad=0) { n.setBoundVariable('itemSpacing',V['space/'+gap]); for(const p of ['paddingLeft','paddingRight','paddingTop','paddingBottom']) n.setBoundVariable(p,V['space/'+pad]); }
const styles = {};
for (const [name,size,line,weight] of /** @type {[string,number,number,string][]} */ ([['Title',24,34,'Bold'],['Section',18,28,'Bold'],['Body',14,22,'Regular'],['Label',14,22,'Medium'],['Meta',12,20,'Regular'],['MetaStrong',12,20,'Medium']])) {
  const s=localStyles.find(s=>s.name==='Admin/'+name)||figma.createTextStyle(); s.name='Admin/'+name; s.fontName={family:'Noto Sans KR',style:weight}; s.fontSize=size; s.lineHeight={unit:'PIXELS',value:line}; styles[name]=s;
}
function F(name,parent,dir='VERTICAL',w=100,h=null,bg=null,gap=0,pad=0) {
  const n=track(figma.createFrame()); n.name=name; n.layoutMode=dir; n.primaryAxisSizingMode=h===null?'AUTO':'FIXED'; n.counterAxisSizingMode='FIXED';
  n.resize(w,h===null?100:h); fill(n,bg); spacing(n,gap,pad); n.clipsContent=false; if(parent)parent.appendChild(n); return n;
}
function T(value,parent,style='Body',color='text',width=null) {
  const n=track(figma.createText()); n.fontName=styles[style].fontName; n.fontSize=styles[style].fontSize; n.lineHeight=styles[style].lineHeight; n.textStyleId=styles[style].id;
  n.characters=value; n.name=value.split('\n')[0].slice(0,60); fill(n,color); parent.appendChild(n);
  if(width!==null){ n.textAutoResize='HEIGHT'; n.resize(width,22); n.layoutSizingHorizontal='FIXED'; } else n.textAutoResize='WIDTH_AND_HEIGHT'; return n;
}
function expand(n,vertical=false){ n[vertical?'layoutSizingVertical':'layoutSizingHorizontal']='FILL'; return n; }
function spacer(parent,vertical=false) { const s=F('여백',parent,vertical?'VERTICAL':'HORIZONTAL',1,1); expand(s,vertical); return s; }
function divider(parent,w){ const n=F('구분선',parent,'HORIZONTAL',w,1,'border'); return n; }
function component(name,w,h,bg='canvas',dir='HORIZONTAL',pad=12,gap=8){
  const n=track(figma.createComponent()); n.name=name;n.resize(w,h);n.layoutMode=dir;n.primaryAxisSizingMode='FIXED';n.counterAxisSizingMode='FIXED';n.counterAxisAlignItems='CENTER';fill(n,bg);spacing(n,gap,pad);round(n);return n;
}
const library=figma.root.children.find(p=>p.name==='02 · 공통 요소 및 인계')||track(figma.createPage());library.name='02 · 공통 요소 및 인계';
if(library.children.length)throw new Error('The library is no longer empty; inspect it before resuming.');
await figma.setCurrentPageAsync(library);
const sets={};
// Variant grid follows the bundled createComponentWithVariants helper pattern.
function combine(name,variants,x,y,columns=4){
  for(const n of variants)library.appendChild(n);
  const set=track(figma.combineAsVariants(variants,library));set.name=name;set.description='Studio Light를 계승한 관리자 공통 요소. 실제 앱 구현 전의 디자인 명세.';
  set.x=x;set.y=y;set.fills=[];
  let maxX=0,maxY=0; variants.forEach((n,i)=>{n.x=24+(i%columns)*(n.width+24);n.y=24+Math.floor(i/columns)*(n.height+24);maxX=Math.max(maxX,n.x+n.width);maxY=Math.max(maxY,n.y+n.height);});
  set.resize(maxX+24,maxY+24);sets[name]=set;return set;
}
const buttons=[];
for(const Style of ['Primary','Secondary'])for(const State of ['Default','Hover','Focus','Disabled','Loading']){
  const old=page.children.find(n=>n.type==='COMPONENT'&&n.name==='Style='+Style+', State='+State);
  if(old){buttons.push(old);changed.push(old.id);continue;}
  const n=component('Style='+Style+', State='+State,120,40,Style==='Primary'?'action':State==='Hover'?'hover':'canvas');
  n.primaryAxisAlignItems='CENTER'; border(n,State==='Focus'?'secondary':Style==='Primary'?'action':'border',State==='Focus'?2:1);
  if(State==='Disabled')n.opacity=.5;
  const label=T(State==='Loading'?'처리 중…':'버튼',n,'Label',Style==='Primary'?'onAction':'text');
  buttons.push(n);
}
const buttonSet=combine('Button',buttons,120,160,5);
const buttonLabel=buttonSet.addComponentProperty('문구','TEXT','버튼');
for(const c of buttons)c.findOne(n=>n.type==='TEXT').componentPropertyReferences={characters:buttonLabel};
const inputs=[];
for(const State of ['Default','Focus','Error','Disabled']){
  const n=component('State='+State,280,40,State==='Disabled'?'sidebar':'canvas');
  border(n,State==='Error'?'danger':State==='Focus'?'secondary':'border',State==='Focus'?2:1);
  const label=T(State==='Error'?'UUID 형식을 확인해 주세요':'입력 내용',n,'Body',State==='Disabled'?'secondary':'text'); expand(label);
  inputs.push(n);
}
const inputSet=combine('Input',inputs,120,420,2);
const inputValue=inputSet.addComponentProperty('값','TEXT','입력 내용');
for(const c of inputs)c.findOne(n=>n.type==='TEXT').componentPropertyReferences={characters:inputValue};
const statusNames={pending:'대기',succeeded:'성공',failed:'실패',cancelled:'취소',stale:'만료',recorded:'저장됨',missing:'미기록'};
const badges=[];
for(const [Status,label] of Object.entries(statusNames)){
  const n=component('Status='+Status,68,28,'sidebar','HORIZONTAL',4,4);n.primaryAxisAlignItems='CENTER';round(n,999);
  T(label,n,'MetaStrong',Status==='failed'?'danger':Status==='succeeded'?'positive':'secondary');badges.push(n);
}
combine('Badge',badges,120,660,7);
const navs=[];for(const State of ['Default','Selected']){
  const n=component('State='+State,192,44,State==='Selected'?'selection':'sidebar');
  T('생성 프롬프트',n,'Label',State==='Selected'?'text':'secondary');navs.push(n);
}combine('Navigation',navs,120,810,2);
function I(name,parent,label,props={}){
  const set=sets[name]; const c=set.children.find(c=>Object.entries(props).every(([k,v])=>c.variantProperties[k]===v))||set.defaultVariant;
  const n=track(c.createInstance());parent.appendChild(n);
  if(label!==null){const key=Object.keys(set.componentPropertyDefinitions).find(k=>set.componentPropertyDefinitions[k].type==='TEXT');if(key)n.setProperties({[key]:label});}
  return n;
}
function B(label,parent,primary=false,w=null,state='Default'){
  const n=I('Button',parent,label,{Style:primary?'Primary':'Secondary',State:state});n.name=label;if(w)n.resize(w,40);return n;
}
function input(value,parent,w,state='Default'){const n=I('Input',parent,value,{State:state});n.resize(w,40);return n;}
function badge(status,parent){return I('Badge',parent,null,{Status:status});}
const colW=[132,132,160,68,68,128,76,76];
const rowVariants=[];
for(const State of ['Default','Hover','Focus']){
  const n=component('State='+State,1120,64,State==='Hover'?'sidebar':'canvas','HORIZONTAL',12,8);round(n,8);border(n,State==='Focus'?'secondary':'border',State==='Focus'?2:1);
  const samples=['d274c6a0\n…a901','80d4cbe2\n…f723','GPT-4.1','medium','成功','10-22\n14:32:08','저장됨','상세 보기'];
  for(let i=0;i<samples.length;i++){
    const cell=F('열 '+i,n,'VERTICAL',colW[i],40,null,0);cell.primaryAxisAlignItems='CENTER';
    if(i===2)expand(cell);
    if(i===4)badge('succeeded',cell);else if(i===6)badge('recorded',cell);else{
      const t=T(i===4?'성공':samples[i],cell,i===7?'MetaStrong':'Meta','text',colW[i]);
    }
  }rowVariants.push(n);
}const rowSet=combine('Table row',rowVariants,120,980,1);
for(const i of [0,1,2,3,5]){
  const defaultText=rowVariants[0].children[i].findOne(n=>n.type==='TEXT').characters;
  const key=rowSet.addComponentProperty('열'+i,'TEXT',defaultText);
  for(const c of rowVariants)c.children[i].findOne(n=>n.type==='TEXT').componentPropertyReferences={characters:key};
}
const note=F('공통 요소 · 사용 가이드',library,'VERTICAL',1120,null,'canvas',24,32);note.x=120;note.y=1320;
T('Studio Admin · 디자인 기준',note,'Title');
T('Noto Sans KR · 흰 본문 · 옅은 회색 탐색기 · 짙은 중성색 행동 버튼 · 8px 모서리',note,'Body');
T('간격 4 / 8 / 12 / 16 / 24 / 32 · 제목 24/34 · 본문 14/22 · 보조 12/20',note,'Body');
T('Button: 기본·호버·포커스·비활성·로딩 / Input: 기본·포커스·오류·비활성 / Table row: 기본·호버·키보드 포커스',note,'Body','secondary',1056);
T('원문 저장 여부는 생성 성공 및 공급자 전송 성공과 별개입니다. 원문은 공급자 어댑터 변환 전 JSON입니다.',note,'Body','secondary',1056);
T('근거: apps/web/components/studio/studio.module.css · studio-controls.tsx · creator-studio.tsx · docs/figma-creator-studio-brief.md · Studio Figma 4:193',note,'Meta','secondary',1056);
const screens={}, links=[];
function root(key,name,w=1440,h=1000){
  const n=F(name,page,'HORIZONTAL',w,h,'canvas'); n.x=120+(Object.keys(screens).length%3)*1600;n.y=120+Math.floor(Object.keys(screens).length/3)*1260;n.clipsContent=true;screens[key]=n;return n;
}
function brand(parent){const r=F('Studio 브랜드',parent,'HORIZONTAL',192,40,null,12);r.counterAxisAlignItems='CENTER';const mark=F('S 마크',r,'HORIZONTAL',36,36,'action');round(mark);mark.primaryAxisAlignItems='CENTER';mark.counterAxisAlignItems='CENTER';T('S',mark,'Section','onAction');T('STUDIO ADMIN',r,'MetaStrong');}
function shell(key,title,w=1440,h=1120){
  const r=root(key,title+' / '+w,w,h);
  const side=F('관리자 사이드바',r,'VERTICAL',224,h,'sidebar',24,16);brand(side);divider(side,192);T('관리자 도구',side,'Meta','secondary');I('Navigation',side,null,{State:'Selected'});
  spacer(side,true);T('운영 관리자',side,'Label');T('admin@example.test',side,'Meta','secondary');const logout=B('로그아웃',side,false,192);links.push([logout,'login']);
  const main=F('작업 영역',r,'VERTICAL',w-224,h,'canvas');expand(main);
  const top=F('현재 위치',main,'HORIZONTAL',w-224,72,'canvas',12,24);top.counterAxisAlignItems='CENTER';T('관리자',top,'Meta','secondary');T('/',top,'Meta','secondary');T('생성 프롬프트',top,'MetaStrong');spacer(top);T('모든 시각은 서울 기준 (UTC+9)',top,'Meta','secondary');
  const body=F('페이지 본문',main,'VERTICAL',w-224,null,'canvas',16,32);expand(body);return {r,body,cw:w-288};
}
function heading(parent,title,desc,w){const box=F('페이지 제목',parent,'VERTICAL',w,null,null,4);T(title,box,'Title');T(desc,box,'Body','secondary',w);}
function field(parent,label,value,w,state='Default'){const f=F(label,parent,'VERTICAL',w,null,null,8);T(label,f,'MetaStrong');input(value,f,w,state);return f;}
function filters(parent,w){
  const box=F('검색 및 필터',parent,'VERTICAL',w,null,'sidebar',12,16);round(box,12);
  const row=F('필터 입력',box,'HORIZONTAL',w-32,null,null,12);row.counterAxisAlignItems='MAX';
  field(row,'시작일 · 서울','2026-10-16',136);field(row,'종료일 · 서울','2026-10-22',136);
  const conv=field(row,'대화 ID','UUID 전체 입력',Math.max(200,w-656));expand(conv);
  field(row,'생성 상태','전체 ▾',140);const search=B('검색',row,true,72);const reset=B('초기화',row,false,80);
  T('서울 날짜 기준 · 시작일과 종료일 포함 · 최대 731일',box,'Meta','secondary');return {search,reset,box};
}
function tableHeader(parent,w){
  const n=F('표 머리글',parent,'HORIZONTAL',w,44,'sidebar',8,12);n.counterAxisAlignItems='CENTER';
  ['생성 ID','대화 ID','당시 모델','Effort','상태','생성 시각 · 서울','원문 기록',''].forEach((s,i)=>{const cell=F('열 '+i,n,'VERTICAL',colW[i],20);if(i===2)expand(cell);T(s,cell,'MetaStrong','secondary',colW[i]);});return n;
}
function overrideRow(row,index){
  const props={};for(const key of Object.keys(sets['Table row'].componentPropertyDefinitions)){
    if(key.startsWith('열0#'))props[key]=['d274c6a0\n…a901','6d580c1e\n…b824','42e867a9\n…c502','e189a6f4\n…a337','a82f670b\n…d103','70ef8301\n…e269','ca8d229e\n…a602','54f0973b\n…f137'][index];
    if(key.startsWith('열1#'))props[key]=['80d4cbe2\n…f723','29a4b3d8\n…e102','80d4cbe2\n…f723','f27a3e9c\n…c318'][index%4];
    if(key.startsWith('열2#'))props[key]=['GPT-4.1','Claude Sonnet 4.5\n20250929','Gemini 2.5 Pro','GPT-4.1'][index%4];
    if(key.startsWith('열3#'))props[key]=['medium','none','high','low'][index%4];
    if(key.startsWith('열5#'))props[key]='2026-10-22\n14:'+String(32-index).padStart(2,'0')+':08';
  }row.setProperties(props);
  const statuses=['succeeded','failed','pending','cancelled','stale','succeeded','failed','succeeded'];
  const badgeInstances=row.findAllWithCriteria({types:['INSTANCE']}).filter(n=>n.name.startsWith('Badge')||('variantProperties' in n&&n.variantProperties&&n.variantProperties.Status));
  for(const n of badgeInstances){const old=n.variantProperties.Status;const wanted=old==='succeeded'?statuses[index]:index===6?'missing':'recorded';const base=sets.Badge.children.find(c=>c.variantProperties.Status===wanted);n.swapComponent(base);}
  row.name='생성 '+(index+1)+' · '+statuses[index];
}
function message(parent,w,role,content){const box=F('메시지 · '+role,parent,'VERTICAL',w,null,role==='user'?'sidebar':'canvas',8,16);round(box);border(box);T(role+' · '+({system:'시스템',user:'사용자',assistant:'어시스턴트'}[role]),box,'MetaStrong');T(content,box,'Body','text',w-32);return box;}
const sample={chat_message_format:1,messages:[{role:'system',content:'당신은 가상의 별빛 기록실 안내자입니다. 주어진 설정과 대화의 맥락을 따르고 한국어로 답변합니다.'},{role:'user',content:'{"reference_data":{"setting":"별빛 기록실","characters":[{"name":"에린","role":"기록실 안내자"}],"active_lore":[],"memories":[]}}'},{role:'assistant',content:'에린이 오래된 장부를 덮으며 고개를 들었다. “기록실에 오신 것을 환영해요. 어떤 이야기를 찾고 계신가요?”'},{role:'user',content:'시계탑에 관한 기록을 찾고 있어요. 마지막으로 종이 울렸던 날의 이야기를 알려주세요.'}]};
const raw=JSON.stringify(sample); // Synthetic source string only; never use this to reserialize real request_json.
// Login / login failure / permission screen.
for(const [key,error] of [['login',false],['loginError',true]]){
  const r=root(key,error?'01b · 로그인 오류':'01 · 관리자 로그인');
  const left=F('브랜드 영역',r,'VERTICAL',600,1000,'sidebar',32,48);brand(left);spacer(left,true);T('운영에 필요한 기록을,\n명확하게.',left,'Title','text',480);T('Studio 관리자 웹',left,'Body','secondary');T('생성 프롬프트를 검색하고\n기록된 원문을 확인합니다.',left,'Body','secondary',440);spacer(left,true);T('STUDIO · ADMIN',left,'Meta','secondary');
  const right=F('로그인 영역',r,'VERTICAL',840,1000,'canvas');right.primaryAxisAlignItems='CENTER';right.counterAxisAlignItems='CENTER';
  const card=F('관리자 로그인 폼',right,'VERTICAL',400,null,null,24);T('관리자 로그인',card,'Title');T('관리자 계정으로 로그인해 주세요.',card,'Body','secondary',400);
  field(card,'이메일','admin@example.test',400,error?'Error':'Default');field(card,'비밀번호','••••••••••••',400,error?'Error':'Default');
  if(error)T('이메일 또는 비밀번호를 확인해 주세요.',card,'Meta','danger',400);
  const button=B('로그인',card,true,400);links.push([button,'list']);T('관리자 권한이 있는 계정만 이용할 수 있습니다.',card,'Meta','secondary',400);
}
// List: data, loading, empty, error and 1280 layout.
for(const [key,state,w] of /** @type {[string,string,number][]} */ ([['list','data',1440],['list1280','data',1280],['listLoading','loading',1440],['listEmpty','empty',1440],['listError','error',1440]])){
  const {r,body,cw}=shell(key,'02 · 생성 프롬프트 · '+state,w);heading(body,'생성 프롬프트','생성 당시의 모델 정보와 기록된 프롬프트를 확인합니다.',cw);
  const f=filters(body,cw);links.push([f.search,'listLoading'],[f.reset,'list']);
  const toolbar=F('결과 요약',body,'HORIZONTAL',cw,40,null,12);toolbar.counterAxisAlignItems='CENTER';
  T(state==='loading'?'결과를 불러오는 중…':state==='error'?'결과를 확인할 수 없습니다':state==='empty'?'검색 결과 0건':'검색 결과 128건',toolbar,'Label');spacer(toolbar);T('페이지당',toolbar,'Meta','secondary');B('50개 ▾',toolbar,false,92);
  const table=F('생성 프롬프트 표',body,'VERTICAL',cw,null,'canvas');border(table);round(table);tableHeader(table,cw);
  if(state==='data')for(const i of [0,1,2,3,4,6]){
    const row=I('Table row',table,null,{State:i===0?'Hover':'Default'});row.resize(cw,64);overrideRow(row,i);
    const detail=row.findAllWithCriteria({types:['TEXT']}).find(t=>t.characters==='상세 보기');links.push([detail,i===6?'detailMissing':'detail']);
  }
  if(state==='loading')for(let j=0;j<6;j++){
    const row=F('로딩 행 '+j,table,'HORIZONTAL',cw,64,null,16,16);row.counterAxisAlignItems='CENTER';for(const width of [112,112,cw-672,52,60,96,64]){const bar=F('스켈레톤',row,'HORIZONTAL',Math.max(24,width),12,'selection');round(bar);} }
  if(state==='empty'||state==='error'){
    const empty=F(state==='empty'?'빈 결과':'조회 실패',table,'VERTICAL',cw,376,null,16,32);empty.primaryAxisAlignItems='CENTER';empty.counterAxisAlignItems='CENTER';
    T(state==='empty'?'검색 결과가 없습니다':'목록을 불러오지 못했습니다',empty,'Section');
    T(state==='empty'?'날짜 범위와 대화 ID, 생성 상태를 확인해 주세요.':'잠시 후 다시 시도해 주세요. 검색 조건은 유지됩니다.',empty,'Body','secondary');
    const retry=B(state==='empty'?'필터 초기화':'다시 시도',empty,false,144);links.push([retry,'list']);
  }
  if(state==='data'){
    const foot=F('페이지 이동',body,'HORIZONTAL',cw,40,null,8);foot.counterAxisAlignItems='CENTER';T('1–50 / 128건',foot,'Meta','secondary');spacer(foot);B('이전',foot,false,64,'Disabled');B('1',foot,true,40);B('2',foot,false,40);B('3',foot,false,40);B('다음',foot,false,64);
    T('원문 기록 여부는 저장 사실만 표시하며 생성 성공과 별개입니다.',body,'Meta','secondary',cw);
  }
}
// Detail metadata and source view.
for(const [key,state,w] of /** @type {[string,string,number][]} */ ([['detail','roles',1440],['detailRaw','raw',1440],['detailCopied','copied',1440],['detailMissing','missing',1440],['detail1280','roles',1280],['detailError','error',1440],['detailNotFound','notfound',1440]])){
  const {r,body,cw}=shell(key,'03 · 생성 프롬프트 상세 · '+state,w,1120);
  const back=B('‹ 목록으로',body,false,120);links.push([back,'list']);
  heading(body,'생성 프롬프트 상세','생성 당시의 메타데이터와 저장된 원문을 조회합니다.',cw);
  if(state==='error'||state==='notfound'){
    const box=F('상세 '+state,body,'VERTICAL',cw,460,'sidebar',16,32);round(box,12);box.primaryAxisAlignItems='CENTER';box.counterAxisAlignItems='CENTER';T(state==='notfound'?'생성 기록을 찾을 수 없습니다':'상세 정보를 불러오지 못했습니다',box,'Section');T(state==='notfound'?'생성 ID를 확인하거나 목록으로 돌아가 주세요.':'잠시 후 다시 시도해 주세요.',box,'Body','secondary');const retry=B(state==='notfound'?'목록으로':'다시 시도',box,false,144);links.push([retry,state==='notfound'?'list':'detail']);continue;
  }
  const meta=F('생성 메타데이터',body,'VERTICAL',cw,null,'sidebar',16,20);round(meta,12);
  const ids=F('식별 정보',meta,'HORIZONTAL',cw-40,null,null,24);
  for(const [label,value] of [['생성 ID',state==='missing'?'ca8d229e-721b-44c6-9511-aed069c0a602':'d274c6a0-a613-4d20-972f-56183ef4a901'],['대화 ID','80d4cbe2-6338-40f8-a734-6a29b685f723']]){
    const cell=F(label,ids,'VERTICAL',(cw-64)/2,null,null,4);T(label,cell,'Meta','secondary');T(value,cell,'MetaStrong','text',(cw-64)/2);
  }
  const details=F('모델 및 생성 결과',meta,'HORIZONTAL',cw-40,null,null,24);
  for(const [label,value] of [['당시 모델','GPT-4.1'],['Reasoning effort','medium'],['생성 시각 · 서울','2026-10-22 14:32:08'],['완료 시각 · 서울','2026-10-22 14:32:12']]){
    const cell=F(label,details,'VERTICAL',(cw-112)/4,null,null,4);T(label,cell,'Meta','secondary');T(value,cell,'MetaStrong','text',(cw-112)/4);
  }
  const statusRow=F('생성과 저장 상태',meta,'HORIZONTAL',cw-40,28,null,12);statusRow.counterAxisAlignItems='CENTER';T('생성 상태',statusRow,'Meta','secondary');badge(state==='missing'?'failed':'succeeded',statusRow);T('원문 기록',statusRow,'Meta','secondary');badge(state==='missing'?'missing':'recorded',statusRow);spacer(statusRow);T('이력 무효화 시각  —',statusRow,'Meta','secondary');
  const sourceHead=F('원문 도구',body,'HORIZONTAL',cw,40,null,8);sourceHead.counterAxisAlignItems='CENTER';T('프롬프트 원문',sourceHead,'Section');spacer(sourceHead);
  const roles=B('역할별 보기',sourceHead,state!=='raw',128);const rawBtn=B('원본 JSON 문자열',sourceHead,state==='raw',160);const copy=B(state==='copied'?'✓ 복사 완료':'원문 복사',sourceHead,false,120,state==='missing'?'Disabled':'Default');
  links.push([roles,'detail'],[rawBtn,'detailRaw']);if(state!=='missing')links.push([copy,'detailCopied']);
  if(state==='missing'){
    const box=F('원문 미기록 안내',body,'VERTICAL',cw,360,'sidebar',16,32);round(box,12);box.primaryAxisAlignItems='CENTER';box.counterAxisAlignItems='CENTER';T('기록된 프롬프트 원문이 없습니다',box,'Section');T('생성 기록은 존재하지만 저장된 원문이 없습니다.\n미기록 이유나 실제 공급자 전송 여부는 확인할 수 없습니다.',box,'Body','secondary',520);continue;
  }
  T('저장된 원문은 공급자 어댑터 변환 전 JSON입니다. 저장 사실은 공급자 전송 또는 생성 성공을 뜻하지 않습니다.',body,'Meta','secondary',cw);
  const source=F('원문 읽기 영역 · 세로 스크롤',body,'VERTICAL',cw,344,'canvas',12,16);round(source);border(source);source.clipsContent=true;source.overflowDirection='VERTICAL';
  const content=F('원문 내용',source,'VERTICAL',cw-32,null,null,12);
  if(state==='raw'){
    const bar=F('원본 표시 설정',content,'HORIZONTAL',cw-32,32,null,12);T('request_json · 원본 문자열',bar,'MetaStrong');spacer(bar);T('줄바꿈 켜짐',bar,'Meta','secondary');
    T(raw,content,'Body','text',cw-32);T('이 보기는 저장된 문자열을 재직렬화하지 않습니다.',content,'Meta','secondary',cw-32);
  }else for(const m of sample.messages)message(content,cw-32,m.role,m.content);
  const record=F('원문 기록 메타데이터',body,'VERTICAL',cw,null,'sidebar',8,16);round(record);
  T('원문 기록 시각 · 서울  2026-10-22 14:32:08    /    공급자  openai    /    형식 버전  1    /    최대 출력 토큰  2048',record,'Meta','secondary',cw-32);
  T('모델 ID  27ac43e0-f72c-4ad5-bb32-f6238c287102',record,'Meta','secondary',cw-32);
  T('SHA-256  6f82c9b2c41e6e40f3931a91d7b049f83dc13921d407147171e741b6b59ac235',record,'Meta','secondary',cw-32);
}
{
  const r=root('forbidden','04 · 접근 권한 없음');const area=F('접근 차단',r,'VERTICAL',1440,1000,'sidebar',24,48);brand(area);spacer(area,true);
  const c=F('권한 안내',area,'VERTICAL',640,null,'canvas',24,40);round(c,12);area.counterAxisAlignItems='CENTER';T('접근 권한이 없습니다',c,'Title');T('관리자 권한이 있는 계정만 이용할 수 있습니다.\n다른 계정으로 로그인하거나 운영 담당자에게 문의해 주세요.',c,'Body','secondary',560);const b=B('로그아웃 후 로그인',c,true,200);links.push([b,'login']);spacer(area,true);
}
// Developer notes are outside product frames and never exposed as menus.
const handoff=F('디자인 인계 · 상태 및 계약',page,'VERTICAL',1440,null,'sidebar',24,32);handoff.x=120;handoff.y=6500;
T('개발 인계 · 생성 프롬프트 조회 v1',handoff,'Title');
for(const s of [
  '01 로그인 → 02 목록 → 03 상세 → 목록 복귀. 모든 데이터는 현실적인 가상 예시입니다.',
  '목록 필터: date_from/date_to (서울 날짜 양 끝 포함, 최대 731일), conversation_id UUID, status. page ≥1, page_size 1–100 / 기본 50.',
  '상태: pending=대기, succeeded=성공, failed=실패, cancelled=취소, stale=만료(한국어 명칭 검토). 모델/사용자/원문 검색 및 정렬 변경은 현재 계약에 없습니다.',
  '목록 로딩=스켈레톤 / 빈 결과=200+items[] / 오류=네트워크·5xx / 422=입력 필드 오류 / 401=로그인 / 403=접근 권한 없음.',
  '상세 미기록=200+prompt:null. 미존재=404. 둘을 혼동하지 않습니다. JSON 파싱 실패/알 수 없는 형식에서는 원본 문자열로 전환하고 손실 없이 표시합니다.',
  '원문 복사: request_json 전체 문자열. 원본 UTF-8 문자열을 파싱 후 재직렬화하지 않습니다. 실제 복사 성공 후 피드백 / 실패 시 재시도 안내.',
  '원문은 no-store. localStorage·분석 이벤트·오류 로그에 남기지 않습니다. 새로고침 및 상세 복귀 시 필터·페이지 URL 유지.',
  'UUID는 표에서 축약, 상세에서 전체 표시. 긴 모델명은 2줄. 1280/1440 화면에서 열·진입점 유지. 원문 영역 세로 스크롤 / wrap off 시 가로 스크롤.',
  '생성 성공 ≠ 원문 저장 ≠ 공급자 전송 성공. 실패 생성에도 원문이 있을 수 있습니다. 공급자 SDK HTTP 요청 전체를 기록한 것으로 표현하지 않습니다.',
  '후속 결정: 제안된 /admin/session 계약·최소 관리자 정보·Light/시스템 테마·원문 조회 감사 정책·대용량 뷰어·날짜 및 페이지 크기 기본값.',
  '후속 기능 제안: 작품/콘텐츠 → 사용자 → 결제/환불 내역 → 크레딧 원장 → 신고/검토 → 감사/권한 → 운영 통계·모델/가격 → 고객지원. 이번 내비게이션에 미노출.'
])T(s,handoff,'Body','text',1376);
// Connect meaningful controls with native prototype navigation.
for(const [from,to] of links)if(from&&screens[to])await from.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:screens[to].id,navigation:'NAVIGATE',transition:{type:'DISSOLVE',easing:{type:'EASE_OUT'},duration:.15},resetScrollPosition:true}]}]);
await screens.listLoading.setReactionsAsync([{trigger:{type:'AFTER_TIMEOUT',timeout:.8},actions:[{type:'NODE',destinationId:screens.list.id,navigation:'NAVIGATE',transition:null}]}]);
page.flowStartingPoints=[{nodeId:screens.login.id,name:'관리자 로그인 → 생성 프롬프트 조회'}];
await figma.setCurrentPageAsync(page);page.selection=[screens.list];figma.viewport.scrollAndZoomIntoView([screens.list]);
const countTypes=n=>{const out={};for(const c of n.findAll(()=>true))out[c.type]=(out[c.type]||0)+1;return out;};
const report={createdNodeIds:created,mutatedNodeIds:changed,pages:{screens:page.id,components:library.id},screens:Object.fromEntries(Object.entries(screens).map(([k,n])=>[k,{id:n.id,name:n.name,width:n.width,height:n.height,types:countTypes(n)}])),components:Object.fromEntries(Object.entries(sets).map(([k,n])=>[k,{id:n.id,variants:n.children.length}])),variables:Object.fromEntries(Object.entries(V).map(([k,v])=>[k,v.id])),textStyles:Object.fromEntries(Object.entries(styles).map(([k,v])=>[k,v.id])),prototypeLinks:links.length+1,fontFamilies:[...new Set(page.findAllWithCriteria({types:['TEXT']}).map(n=>n.fontName===figma.mixed?'MIXED':n.fontName.family))],imageFilledNodes:page.findAll(n=>'fills' in n&&Array.isArray(n.fills)&&n.fills.some(f=>f.type==='IMAGE')).map(n=>({id:n.id,name:n.name}))};
console.log(JSON.stringify(report));
