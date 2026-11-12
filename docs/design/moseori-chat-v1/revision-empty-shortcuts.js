// Append after revision-shared.js, with WRITING injected.
const ids=WRITING.screens;
const [latest,slash,diary,detail,description,original]=await Promise.all([ids.latest,ids.slash,ids.applied,ids.appliedAlt,ids.described,BASE.screens.screens.LightMobile].map(get));
const sec=section('02b · 빈 작성란에서 단축어 선택',5260,100,1390,1048);
await heading(sec,'단축어만 골라도 초안은 그대로','02b  /  입력란을 비운 상태에서 단축어를 여는 경우. 선택한 이름만 추가됩니다.');
const x=i=>48+i*452;
const menu=clone(slash,sec,'390 · 단축어 목록 / 빈 작성란',x(0),164);removeRootHotspots(menu);
const menuFooter=footer(menu);del(menuFooter.children[0]);
menuFooter.appendChild(tree(footer(latest).children[0].clone()));
const list=select(menu,'단축어 목록');list.y=menuFooter.y-list.height-8;mutatedNodeIds.push(menuFooter.id,list.id);
const close=named(list,'×');
const rows=list.children.filter(n=>n.type==='FRAME'&&n.name.startsWith('/'));
const states=[];
for(const [i,source]of [diary,detail].entries()){
 const root=clone(source,sec,'390 · '+(i===0?'/일기':'/묘사 강화')+' / 빈 작성란',x(i+1),164);removeRootHotspots(root);
 const draft=named(footer(root),'묘사와 대사 입력 예시');draft.characters='에린에게 이야기를 이어가세요…';fill(draft,'Light','secondary');draft.name='입력 · 빈 상태';mutatedNodeIds.push(draft.id);
 if(i===1){const send=named(footer(root),'전송');send.swapComponent(await get(B.buttons.Light.disabled));send.name='전송 · 대사를 입력하면 활성화';mutatedNodeIds.push(send.id);}
 const chip=select(named(footer(root),'선택한 단축어'),i===0?'/일기  ×':'/묘사 강화  ×');
 await goto(chip,latest);
 await goto(rows[i],root);states.push(root);
 for(const n of [...source.children])if(['프로토타입 · 묘사 넣기','프로토타입 · 단축어'].includes(n.name))del(n);
}
await goto(close,latest);
for(const root of [latest,original])await goto(select(root,'프로토타입 · 단축어'),menu);
await label(sec,x(0),131,'빈 입력 · 단축어 열기');
await label(sec,x(1),131,'단독 사용 예시 · /일기');
await label(sec,x(2),131,'작성 보조 예시 · /묘사 강화');
return {createdNodeIds:[...new Set(createdNodeIds)],mutatedNodeIds:[...new Set(mutatedNodeIds)],removedNodeIds:[...new Set(removedNodeIds)],section:sec.id,screens:{menu:menu.id,diary:states[0].id,detail:states[1].id},drafts:states.map(n=>({id:n.id,footer:footer(n).height,placeholder:named(n,'입력 · 빈 상태')?.characters}))};
