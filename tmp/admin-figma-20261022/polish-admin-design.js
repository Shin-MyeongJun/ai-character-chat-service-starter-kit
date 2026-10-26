// Applies targeted visual fixes to the existing administrator design.
// No network, credentials or application code. Existing screen IDs are preserved.
// Run once in the SAME administrator file, after build-admin-design.js completed.
const page=figma.root.children.find(p=>p.name==='01 · 관리자 화면 및 상태');
if(!page)throw new Error('Administrator page not found.');
await figma.setCurrentPageAsync(page);
const roots=/** @type {AdminFrame[]} */(page.children.filter(n=>n.type==='FRAME'&&/^0[1-4]/.test(n.name)));
if(roots.length!==15)throw new Error('Expected 15 existing screens, found '+roots.length+'. Inspect before applying again.');
const created=[],mutated=[];
const removed=[];
const tree=n=>[n,...('findAll' in n?n.findAll(()=>true):[])];
const texts=roots.flatMap(n=>n.findAllWithCriteria({types:['TEXT']}));
const fonts=new Map();for(const n of texts)for(const s of n.getStyledTextSegments(['fontName']))fonts.set(JSON.stringify(s.fontName),s.fontName);
await Promise.all([...fonts.values()].map(f=>figma.loadFontAsync(f)));
function changed(n){mutated.push(n.id);return n;}
function nav(n,dest){return n.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:dest.id,navigation:'NAVIGATE',transition:{type:'DISSOLVE',easing:{type:'EASE_OUT'},duration:.15},resetScrollPosition:true}]}]);}
const rowNames=new Set(['필터 입력','식별 정보','모델 및 생성 결과']);
for(const r of roots){
  for(const n of r.findAllWithCriteria({types:['FRAME']}).filter(n=>rowNames.has(n.name))){
    n.primaryAxisSizingMode='FIXED';n.counterAxisSizingMode='AUTO';changed(n);
  }
  for(const t of r.findAllWithCriteria({types:['TEXT']})){
    if(t.textAutoResize==='HEIGHT'){
      const value=t.characters;t.textAutoResize='NONE';t.textAutoResize='HEIGHT';t.characters=value;changed(t);
    }
  }
}
// Explicitly reserve two 34px headline lines and keep subsequent copy separated.
for(const r of roots.filter(n=>n.name.startsWith('01'))){
  const title=r.findAllWithCriteria({types:['TEXT']}).find(n=>n.characters.startsWith('운영에 필요한 기록을,'));
  if(title){title.textAutoResize='NONE';title.resize(480,68);title.textAutoResize='HEIGHT';title.characters='운영에 필요한 기록을,\n명확하게.';changed(title);}
}
// Make the 50-row page represented in the pagination scroll inside the table.
for(const r of roots.filter(n=>n.name.startsWith('02 · 생성 프롬프트 · data'))){
  const table=r.findAllWithCriteria({types:['FRAME']}).find(n=>n.name==='생성 프롬프트 표');
  const rows=table.children.filter(n=>n.type==='INSTANCE');
  if(rows.length!==6)throw new Error('Expected six mock rows before expansion: '+r.name);
  const base=rows[0];
  for(let i=6;i<50;i++){
    const row=rows[i%rows.length].clone();table.appendChild(row);row.name='가상 생성 '+(i+1);
    const key=Object.keys(row.componentProperties).find(k=>k.startsWith('열0#'));
    if(key)row.setProperties({[key]:(0x12000000+i).toString(16)+'\n…'+(0x1000+i).toString(16)});
    created.push(...tree(row).map(n=>n.id));
  }
  table.resize(table.width,428);table.primaryAxisSizingMode='FIXED';table.clipsContent=true;table.overflowDirection='VERTICAL';changed(table);
}
// Create a native prototype for line wrapping without altering the source string.
const raw=roots.find(n=>n.name==='03 · 생성 프롬프트 상세 · raw / 1440');
const nowrap=raw.clone();page.appendChild(nowrap);nowrap.name='03 · 생성 프롬프트 상세 · raw nowrap / 1440';nowrap.x=4920;nowrap.y=120;
created.push(...tree(nowrap).map(n=>n.id));
const rawSource=nowrap.findAllWithCriteria({types:['FRAME']}).find(n=>n.name==='원문 읽기 영역 · 세로 스크롤');
rawSource.name='원문 읽기 영역 · 가로 및 세로 스크롤';rawSource.overflowDirection='BOTH';changed(rawSource);
const sourceText=nowrap.findAllWithCriteria({types:['TEXT']}).find(n=>n.characters.startsWith('{"chat_message_format"'));
sourceText.textAutoResize='WIDTH_AND_HEIGHT';sourceText.layoutSizingHorizontal='HUG';sourceText.characters=sourceText.characters;changed(sourceText);
const on=raw.findAllWithCriteria({types:['TEXT']}).find(n=>n.characters==='줄바꿈 켜짐');
const off=nowrap.findAllWithCriteria({types:['TEXT']}).find(n=>n.characters==='줄바꿈 켜짐');
on.characters='줄바꿈 켜짐 ▾';off.characters='줄바꿈 꺼짐 ▾';changed(on);changed(off);
await nav(on,nowrap);await nav(off,raw);
// Keep content panels recognizably scrollable without obscuring the text.
for(const r of [...roots,nowrap].filter(n=>n.name.startsWith('03 · 생성 프롬프트 상세 · roles')||n.name.startsWith('03 · 생성 프롬프트 상세 · copied'))){
  const viewport=r.findAllWithCriteria({types:['FRAME']}).find(n=>n.name==='원문 읽기 영역 · 세로 스크롤');
  if(viewport){viewport.name='원문 읽기 영역 · 스크롤하여 전체 내용 보기';changed(viewport);}
}
const library=figma.root.children.find(p=>p.name==='02 · 공통 요소 및 인계');
// Componentize repeated role cards; preserve each message's exact visible text.
const roleRoot=roots.find(n=>n.name==='03 · 생성 프롬프트 상세 · roles / 1440');
const roleVariants=[];
for(const role of ['system','user','assistant']){
  const source=roleRoot.findAllWithCriteria({types:['FRAME']}).find(n=>n.name==='메시지 · '+role);
  const copy=source.clone();library.appendChild(copy);const c=figma.createComponentFromNode(copy);c.name='Role='+role;c.primaryAxisSizingMode='AUTO';
  const body=c.findAllWithCriteria({types:['TEXT']})[1];body.textAutoResize='HEIGHT';body.layoutSizingHorizontal='FILL';
  roleVariants.push(c);created.push(...tree(c).map(n=>n.id));
}
const messages=figma.combineAsVariants(roleVariants,library);messages.name='Prompt message';messages.description='원문의 role과 순서를 보존하는 카드. 본문은 저장된 문자열이며 HTML로 실행하지 않습니다.';messages.x=120;messages.y=2100;messages.fills=[];
const messageProperty=messages.addComponentProperty('본문','TEXT','메시지 내용');
for(let i=0;i<roleVariants.length;i++){const c=roleVariants[i];c.x=24;c.y=24+i*160;c.findAllWithCriteria({types:['TEXT']})[1].componentPropertyReferences={characters:messageProperty};}
messages.resize(1168,504);created.push(messages.id);
for(const r of [...roots,nowrap]){
  const cards=r.findAllWithCriteria({types:['FRAME']}).filter(n=>n.name.startsWith('메시지 · '));
  for(const old of cards){
    const role=old.name.slice('메시지 · '.length);const value=old.findAllWithCriteria({types:['TEXT']})[1].characters;
    const c=roleVariants.find(c=>c.name==='Role='+role);const i=c.createInstance();const parent=old.parent;const index=parent.children.indexOf(old);parent.insertChild(index,i);i.resize(old.width,old.height);i.primaryAxisSizingMode='AUTO';i.setProperties({[messageProperty]:value});
    created.push(...tree(i).map(n=>n.id));removed.push(...tree(old).map(n=>n.id));old.remove();
  }
}
// Library gallery: show every state as an instance, with masters kept separately.
const sets=library.children.filter(n=>n.type==='COMPONENT_SET');
const overview=figma.createFrame();library.appendChild(overview);overview.name='공통 요소 · 상태 미리보기';overview.x=1500;overview.y=160;overview.resize(1280,1200);overview.layoutMode='VERTICAL';overview.primaryAxisSizingMode='AUTO';overview.counterAxisSizingMode='FIXED';overview.paddingTop=32;overview.paddingBottom=32;overview.paddingLeft=32;overview.paddingRight=32;overview.itemSpacing=24;overview.fills=[{type:/** @type {'SOLID'} */('SOLID'),color:{r:1,g:1,b:1}}];created.push(overview.id);
function text(value,parent,size=14){const t=figma.createText();t.fontName={family:'Noto Sans KR',style:'Regular'};t.fontSize=size;t.lineHeight={unit:'PIXELS',value:size===24?34:22};t.characters=value;t.fills=[{type:/** @type {'SOLID'} */('SOLID'),color:{r:32/255,g:32/255,b:36/255}}];parent.appendChild(t);created.push(t.id);return t;}
text('공통 컴포넌트 · 상태 미리보기',overview,24);
for(const set of sets){
  text(set.name+' · '+set.children.length+'개 상태',overview);
  if(set.name==='Table row'||set.name==='Prompt message'){
    for(const c of set.children){if(c.type!=='COMPONENT')continue;const i=c.createInstance();overview.appendChild(i);i.resize(1216,set.name==='Table row'?64:c.height);if(set.name==='Prompt message')i.primaryAxisSizingMode='AUTO';created.push(...tree(i).map(n=>n.id));}
  }else{
    const row=figma.createFrame();overview.appendChild(row);row.name=set.name+' 상태';row.resize(1216,100);row.layoutMode='HORIZONTAL';row.primaryAxisSizingMode='FIXED';row.counterAxisSizingMode='AUTO';row.layoutWrap='WRAP';row.itemSpacing=12;row.counterAxisSpacing=12;row.fills=[];created.push(row.id);
    for(const c of set.children){if(c.type!=='COMPONENT')continue;const i=c.createInstance();row.appendChild(i);created.push(...tree(i).map(n=>n.id));}
  }
}
const allRoots=[...roots,nowrap];
const report={createdNodeIds:created,mutatedNodeIds:mutated,replacedMessageNodeIds:removed,screenCount:allRoots.length,components:sets.map(s=>({id:s.id,name:s.name,variants:s.children.length})),imageFilledNodes:[],fontFamilies:[],overflow:[],screens:allRoots.map(r=>({id:r.id,name:r.name,width:r.width,height:r.height,descendants:r.findAll(()=>true).length,text:r.findAllWithCriteria({types:['TEXT']}).length,instances:r.findAllWithCriteria({types:['INSTANCE']}).length}))};
const families=new Set();
for(const r of allRoots){
  const box=r.absoluteBoundingBox;
  for(const n of r.findAll(()=>true)){
    if(n.type==='TEXT')for(const seg of n.getStyledTextSegments(['fontName']))families.add(seg.fontName.family);
    if('fills' in n&&Array.isArray(n.fills)&&n.fills.some(f=>f.type==='IMAGE'))report.imageFilledNodes.push({id:n.id,name:n.name});
    const b=n.absoluteBoundingBox;if(!b||!box||!n.visible)continue;
    let intentional=false,p=n.parent;while(p&&p!==r){if(p.type==='FRAME'&&p.clipsContent&&p.overflowDirection!=='NONE'){intentional=true;break;}p=p.parent;}
    if(!intentional&&(b.x<box.x-1||b.y<box.y-1||b.x+b.width>box.x+box.width+1||b.y+b.height>box.y+box.height+1))report.overflow.push({screen:r.name,id:n.id,name:n.name,bounds:b});
  }
}
report.fontFamilies=[...families];
const qa=figma.createFrame();library.appendChild(qa);qa.name='QA · 검수 결과';qa.x=1500;qa.y=1800;qa.resize(1280,400);qa.layoutMode='VERTICAL';qa.primaryAxisSizingMode='AUTO';qa.counterAxisSizingMode='FIXED';qa.paddingTop=32;qa.paddingBottom=32;qa.paddingLeft=32;qa.paddingRight=32;qa.itemSpacing=16;qa.fills=[{type:/** @type {'SOLID'} */('SOLID'),color:{r:1,g:1,b:1}}];created.push(qa.id);
text('QA · 구조 확인',qa,24);text('화면 '+report.screenCount+'개 · 이미지 채움 '+report.imageFilledNodes.length+'개 · 폰트 '+report.fontFamilies.join(', ')+' · 루트 경계 초과 '+report.overflow.length+'개',qa);
const detail=text(JSON.stringify(report),qa,12);detail.name='QA_JSON';detail.resize(1216,300);detail.textAutoResize='HEIGHT';detail.characters=JSON.stringify(report);created.push(detail.id);
page.selection=[raw];figma.viewport.scrollAndZoomIntoView([raw]);
console.log(JSON.stringify(report));

