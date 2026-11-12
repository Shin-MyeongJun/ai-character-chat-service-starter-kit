// Inject BASE from the existing Figma state ledger before running.
const page=await figma.getNodeByIdAsync(BASE.foundations.pages.library);
await figma.setCurrentPageAsync(page);
const font={family:'Noto Sans KR',style:'Medium'};
await Promise.all(['Regular','Medium','Bold'].map(style=>figma.loadFontAsync({family:font.family,style})));
const createdNodeIds=[],mutatedNodeIds=[],removedNodeIds=[];
const B=BASE.components.components, S=BASE.foundations;
const roles={};
for(const [theme,values] of Object.entries(S.colors)){
 roles[theme]=Object.fromEntries(await Promise.all(Object.entries(values).map(async ([k,id])=>[k,await figma.variables.getVariableByIdAsync(id)])));
}
const paint=(th,k)=>figma.variables.setBoundVariableForPaint({type:'SOLID',color:{r:0,g:0,b:0}},'color',roles[th][k]);
const defs={description:{label:'**',name:'묘사 넣기'},slash:{label:'/',name:'단축어'},lore:{label:'＋',name:'로어 선택'},reroll:{label:'리롤',name:'리롤',path:'<path d="M20 7v5h-5M4 17v-5h5M6 8a7 7 0 0 1 12-1l2 3M4 14l2 3a7 7 0 0 0 12-1"/>'},branch:{label:'분기',name:'분기',path:'<path d="M6 6v11a3 3 0 0 0 3 3h4M6 12h7a4 4 0 0 0 4-4V5m-3 3 3-3 3 3m-10 9 3 3-3 3"/>'}};
const controls={};
for(const [i,theme] of ['Light','Dark'].entries()){
 controls[theme]={};
 for(const [j,[k,o]] of Object.entries(defs).entries()){
  const c=figma.createComponent();createdNodeIds.push(c.id);
  c.name='Chat / '+o.name+' / '+theme;
  c.description=k==='description'?'선택한 글을 **묘사**로 감싸거나 빈 묘사 구간을 삽입합니다.':k==='slash'?'프롬프트 단축어 목록을 엽니다.':k==='lore'?'이번 답변에 적용할 로어를 선택합니다.':'캐릭터 답변 아래에 배치하는 메시지 액션.';
  c.layoutMode='HORIZONTAL';c.resize(o.path?88:44,44);c.primaryAxisSizingMode='FIXED';c.counterAxisSizingMode='FIXED';c.primaryAxisAlignItems='CENTER';c.counterAxisAlignItems='CENTER';c.itemSpacing=6;c.cornerRadius=8;
  c.fills=[paint(theme,o.path?'canvas':'surface')];c.strokes=[paint(theme,'border')];
  c.x=100+j*112;c.y=800+i*68;
  if(o.path){
   const v=figma.createNodeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#202024" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+o.path+'</svg>');
   v.fills=[];c.appendChild(v);createdNodeIds.push(v.id);
   for(const n of v.findAll(()=>true)){createdNodeIds.push(n.id);if('strokes'in n&&n.strokes.length)n.strokes=[paint(theme,'secondary')];}
  }
  const t=figma.createText();createdNodeIds.push(t.id);await t.setTextStyleIdAsync(S.styles['UI/Label']);t.characters=o.label;t.name=o.name;t.fills=[paint(theme,'text')];c.appendChild(t);
  controls[theme][k]=c;
 }
}
const composerInfo={};
for(const [key,id] of Object.entries(B.composers)){
 const theme=key.startsWith('Light')?'Light':'Dark';
 const comp=await figma.getNodeByIdAsync(id);
 const row=comp.children.find(n=>n.name==='작성 도구와 전송');
 const old=row.children.find(n=>n.name.startsWith('입력 보조'));
 if(old){removedNodeIds.push(old.id);old.remove();}
 for(const [i,k]of ['description','slash','lore'].entries()){
  const b=controls[theme][k].createInstance();row.insertChild(i,b);b.name=defs[k].name;createdNodeIds.push(b.id);
 }
 const hint=row.children.find(n=>n.type==='TEXT');
 hint.name=key.endsWith('Mobile')?'작성 도구 여백':'전송 키 안내';
 hint.characters=key.endsWith('Mobile')?'':'Enter로 전송';
 hint.layoutSizingHorizontal='FILL';
 mutatedNodeIds.push(comp.id,row.id,hint.id);
 composerInfo[key]={id:comp.id,height:comp.height,controls:row.children.map(n=>({id:n.id,name:n.name,width:n.width,height:n.height}))};
}
return {createdNodeIds,mutatedNodeIds,removedNodeIds,composerInfo,controls:Object.fromEntries(Object.entries(controls).map(([th,c])=>[th,Object.fromEntries(Object.entries(c).map(([k,n])=>[k,n.id]))]))};
