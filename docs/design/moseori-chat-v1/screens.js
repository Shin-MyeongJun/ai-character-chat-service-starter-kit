const createdNodeIds=[],mutatedNodeIds=[];
const page=await figma.getNodeByIdAsync(STATE.pages.review);await figma.setCurrentPageAsync(page);
await Promise.all(['Regular','Medium','Bold'].map(style=>figma.loadFontAsync({family:'Noto Sans KR',style})));
const variables={};for(const [theme,rs] of Object.entries(STATE.colors)){variables[theme]={};for(const [r,id]of Object.entries(rs))variables[theme][r]=await figma.variables.getVariableByIdAsync(id);}
const geometry={};for(const[n,id]of Object.entries(STATE.geometry))geometry[n]=await figma.variables.getVariableByIdAsync(id);
const comps={};for(const[name,map]of Object.entries(COMPONENTS)){comps[name]={};if(['icons','buttons'].includes(name))continue;for(const[k,id]of Object.entries(map))comps[name][k]=await figma.getNodeByIdAsync(id);}
function rec(n){createdNodeIds.push(n.id);return n;}
function paint(th,role){return figma.variables.setBoundVariableForPaint({type:'SOLID',color:{r:0,g:0,b:0}},'color',variables[th][role]);}
function fill(n,th,role){n.fills=role?[paint(th,role)]:[];}
function gap(n,v){n.setBoundVariable('itemSpacing',geometry['space/'+v]);}
function pad(n,v){for(const p of ['paddingLeft','paddingRight','paddingTop','paddingBottom'])n.setBoundVariable(p,geometry['space/'+v]);}
function auto(name,dir,w){const n=rec(figma.createAutoLayout(dir));n.name=name;n.resize(w,1);n.primaryAxisSizingMode=dir==='VERTICAL'?'AUTO':'FIXED';n.counterAxisSizingMode=dir==='VERTICAL'?'FIXED':'AUTO';n.fills=[];return n;}
async function text(p,name,value,style,th,role,w){const n=rec(figma.createText());n.name=name;await n.setTextStyleIdAsync(STATE.styles[style]);n.characters=value;fill(n,th,role);p.appendChild(n);if(w){n.textAutoResize='HEIGHT';n.resize(w,n.height);if(p.type==='FRAME'&&p.layoutMode!=='NONE')n.layoutSizingHorizontal='FILL';}return n;}
function inst(p,c,w){const i=rec(c.createInstance());p.appendChild(i);if(w)i.resize(w,i.height);return i;}
const section=rec(figma.createSection());section.name='01 · 대표 대화 | 모바일 먼저, 읽기에 집중';section.x=100;section.y=100;section.resizeWithoutConstraints(2070,2260);section.fills=[{type:'SOLID',color:{r:.92,g:.92,b:.93}}];
await text(section,'리뷰 제목','모서리 — 대화의 여백','Review/Title','Light','text',1500).then(n=>{n.x=56;n.y=36;});
await text(section,'리뷰 설명','캐릭터의 긴 이야기는 편하게 읽고, 나의 다음 대사는 자연스럽게.   ·   대표 화면 v1   /   2026.11.06','UI/Body','Light','secondary',1700).then(n=>{n.x=56;n.y=96;});
const screens={},scrollTargets={},diagnostics=[];
for(const th of ['Light','Dark'])for(const device of ['Mobile','Desktop']){
 const mobile=device==='Mobile',w=mobile?390:1440,h=mobile?844:960,bw=mobile?342:680,key=th+device;
 const root=auto('대화 / '+(mobile?'390':'1440')+' / '+th,'VERTICAL',w);root.resize(w,h);root.primaryAxisSizingMode='FIXED';root.clipsContent=true;fill(root,th,'canvas');section.appendChild(root);root.x=mobile?56:518;root.y=th==='Light'?204:1260;
 await text(section,'화면 라벨',`${mobile?'01 · Mobile / 390':'02 · Desktop / 1440'}  ·  ${th}`,'UI/Label','Light','text',mobile?390:1440).then(n=>{n.x=root.x;n.y=root.y-40;});
 if(mobile){const status=auto('기기 상단 안전 영역','HORIZONTAL',w);root.appendChild(status);status.resize(w,24);status.primaryAxisSizingMode='FIXED';status.paddingLeft=24;status.paddingRight=24;status.counterAxisAlignItems='CENTER';await text(status,'시각','9:41','UI/Caption',th,'text');const sp=auto('여백','HORIZONTAL',240);status.appendChild(sp);sp.layoutSizingHorizontal='FILL';await text(status,'연결 및 배터리','LTE  100%','UI/Caption',th,'text');}
 const header=inst(root,comps.headers[key]);header.layoutSizingHorizontal='FILL';
 const viewport=auto('대화 본문 · 세로 스크롤','VERTICAL',w);root.appendChild(viewport);viewport.resize(w,500);viewport.layoutSizingHorizontal='FILL';viewport.layoutSizingVertical='FILL';viewport.primaryAxisSizingMode='FIXED';viewport.clipsContent=true;viewport.overflowDirection='VERTICAL';viewport.counterAxisAlignItems='CENTER';pad(viewport,24);viewport.paddingBottom=80;
 const body=auto('읽기 열 · '+bw+'px','VERTICAL',bw);viewport.appendChild(body);gap(body,24);
 const opening=auto('첫 장면','VERTICAL',bw);body.appendChild(opening);opening.layoutSizingHorizontal='FILL';gap(opening,8);pad(opening,16);fill(opening,th,'subtle');opening.cornerRadius=8;
 await text(opening,'첫 장면 라벨','첫 장면 · 비 내리는 기록실','UI/Caption',th,'secondary',bw-32);
 await text(opening,'첫 장면 본문','낯선 골목 끝, 불이 켜진 기록실. 에린이 장부를 덮으며 고개를 들었다. “어떤 이야기를 찾고 계신가요?”','UI/Body',th,'text',bw-32);
 const userrow=auto('사용자 메시지 · 우측 정렬','HORIZONTAL',bw);body.appendChild(userrow);userrow.layoutSizingHorizontal='FILL';userrow.primaryAxisAlignItems='MAX';inst(userrow,comps.users[th]);
 const answer=inst(body,comps.characters[key]);answer.layoutSizingHorizontal='FILL';
 const end=auto('답변 끝 · 다음 대사로','VERTICAL',bw);body.appendChild(end);gap(end,8);await text(end,'답변 읽기 완료','이제, 당신의 이야기를 이어가세요.','UI/Caption',th,'secondary',bw);scrollTargets[key]=end.id;
 const footer=auto('작성 영역 · 고정','VERTICAL',w);root.appendChild(footer);footer.layoutSizingHorizontal='FILL';footer.counterAxisAlignItems='CENTER';footer.paddingTop=16;footer.paddingBottom=mobile?34:20;footer.paddingLeft=mobile?16:24;footer.paddingRight=mobile?16:24;gap(footer,8);fill(footer,th,'canvas');footer.strokes=[paint(th,'border')];footer.strokeTopWeight=1;footer.strokeLeftWeight=0;footer.strokeRightWeight=0;footer.strokeBottomWeight=0;
 inst(footer,comps.composers[key]);
 await text(footer,'입력 저장 안내','작성 중인 내용은 자동으로 저장돼요.','UI/Caption',th,'secondary');
 const jump=inst(root,comps.latest[th]);jump.layoutPositioning='ABSOLUTE';jump.x=(w-jump.width)/2;jump.y=h-footer.height-56;jump.name='최신 메시지로 · 이전 글을 읽는 동안 표시';
 await jump.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:end.id,navigation:'SCROLL_TO',transition:{type:'SCROLL_ANIMATE',easing:{type:'EASE_OUT'},duration:.24}}]}]);
 screens[key]=root.id;
 const ns=root.findAll(()=>true),types={};for(const n of ns)types[n.type]=(types[n.type]??0)+1;
 const images=ns.filter(n=>'fills'in n&&Array.isArray(n.fills)&&n.fills.some(p=>p.type==='IMAGE')).map(n=>({id:n.id,name:n.name,width:n.width,height:n.height}));
 diagnostics.push({key,id:root.id,width:root.width,height:root.height,readingWidth:body.width,viewportHeight:viewport.height,contentHeight:body.height,footerHeight:footer.height,types,images,fontFamilies:[...new Set(ns.filter(n=>n.type==='TEXT').map(n=>n.fontName.family))]});
}
page.flowStartingPoints=[{nodeId:screens.LightMobile,name:'모바일 · 긴 답변 읽기'},{nodeId:screens.DarkMobile,name:'모바일 · 다크'},{nodeId:screens.LightDesktop,name:'PC · 긴 답변 읽기'},{nodeId:screens.DarkDesktop,name:'PC · 다크'}];mutatedNodeIds.push(page.id);
figma.viewport.scrollAndZoomIntoView([await figma.getNodeByIdAsync(screens.LightMobile),await figma.getNodeByIdAsync(screens.LightDesktop)]);
return {createdNodeIds,mutatedNodeIds,section:section.id,screens,scrollTargets,diagnostics};
