// Append after revision-shared.js, with BASE, CONTROLS and CONTENT injected.
const originals={};
async function actions(end,th){
 end.name='답변 끝 · 메시지 액션';end.itemSpacing=8;end.paddingTop=8;rule(end,th,'top');
 const row=frame('답변 아래 액션',end.width,'HORIZONTAL',end);row.itemSpacing=8;
 const reroll=await instance(row,CONTROLS[th].reroll,'리롤');
 const branch=await instance(row,CONTROLS[th].branch,'분기');
 return {reroll,branch};
}
for(const [key,id]of Object.entries(BASE.screens.screens)){
 const root=await get(id);originals[key]=root;const f=footer(root),th=key.startsWith('Light')?'Light':'Dark';
 const notice=select(f,'입력 저장 안내');if(notice)del(notice);
 const end=body(root).children.at(-1);
 if(end.name!=='답변 끝 · 메시지 액션'){
  for(const n of [...end.children])del(n);
  await actions(end,th);
 }
 const jump=root.children.find(n=>n.name.startsWith('최신 메시지로'));
 jump.y=root.height-f.height-56;mutatedNodeIds.push(root.id,f.id,end.id,jump.id);
}
const board=await get(BASE.screens.section);
const reviewCopy=select(board,'리뷰 설명');reviewCopy.characters='캐릭터의 긴 이야기는 편하게 읽고, 나의 다음 대사는 자연스럽게.   ·   대표 화면 v2   /   2026.11.09';mutatedNodeIds.push(reviewCopy.id);
const oldNote=await get('8:244');if(oldNote){oldNote.name='기록 · v1 검토 메모';mutatedNodeIds.push(oldNote.id);}
const sec=section('02 · 작성 도구와 답변 아래 액션',2320,100,2810,2110);
await heading(sec,'다음 대사를 쓰고, 이 장면에서 이어가기','02  /  ** 묘사 · / 단축어 · 답변 아래 리롤과 분기. 확인 화면은 디자인 시뮬레이션입니다.');
const screens={};
async function tail(source,th,p,x,y,name){
 const root=clone(source,p,name,x,y);
 const v=view(root);v.paddingBottom=24;
 const b=body(root);b.itemSpacing=16;
 const end=b.children.at(-1);
 for(const n of [...b.children])if(n!==end)del(n);
 const narrative=frame('에린 · 답변 마지막 문단',b.width,'VERTICAL');b.insertChild(0,narrative);narrative.itemSpacing=16;
 await t(narrative,'에린','UI/Label',th);
 for(const c of CONTENT.slice(source.width===390?-3:-6)){
  const dlg=c.type==='dialogue';await t(narrative,c.text,dlg?'Reading/Dialogue':'Reading/Narration',th,dlg?'text':'secondary',true);
 }
 const jump=root.children.find(n=>n.name.startsWith('최신 메시지로'));if(jump)del(jump);
 return root;
}
const x=i=>48+i*452,y=164;
const lm=await tail(originals.LightMobile,'Light',sec,x(0),y,'390 · 답변 끝 / 작성 도구');
screens.latest=lm.id;
await label(sec,x(0),y-33,'01   답변 끝 · 리롤 / 분기');
const draftText='**열쇠를 들어 빛에 비춰 본다.**\n편지부터 읽어 볼까요?';
async function filled(root,cmd){
 const f=footer(root);del(f.children[0]);
 const c=frame('작성란 · 입력된 예시',358,'VERTICAL',f);pad(c,12);c.itemSpacing=8;c.cornerRadius=12;fill(c,'Light','surface');c.strokes=[paint('Light','border')];
 let remove=null;
 if(cmd){
  const r=frame('선택한 단축어',334,'HORIZONTAL',c);r.itemSpacing=8;r.counterAxisAlignItems='CENTER';
  remove=await button(r,cmd+'  ×','Light',{w:cmd==='/일기'?88:120,h:36});
 }
 const txt=await t(c,draftText,'UI/Body','Light','text',true);txt.name='묘사와 대사 입력 예시';
 const bar=frame('작성 도구와 전송',332,'HORIZONTAL',c);bar.itemSpacing=8;bar.counterAxisAlignItems='CENTER';
 for(const [k,n] of [['description','묘사 넣기'],['slash','단축어'],['lore','로어 선택']])await instance(bar,CONTROLS.Light[k],n);
 spacer(bar);await instance(bar,B.buttons.Light.primary,'전송');
 return {remove};
}
const described=clone(lm,sec,'390 · 별표로 묘사 입력',x(1),y);screens.described=described.id;
await filled(described,null);await label(sec,x(1),y-33,'02   **  묘사 입력');
const slash=clone(described,sec,'390 · 단축어 목록',x(2),y);screens.slash=slash.id;
await label(sec,x(2),y-33,'03   /  단축어 목록');
const sp=panel('단축어 목록',slash,358,'Light',16,0);sp.itemSpacing=0;pad(sp,16,8);
const st=frame('단축어 제목',324,'HORIZONTAL',sp);st.counterAxisAlignItems='CENTER';await t(st,'단축어','UI/Title','Light');spacer(st);
const sClose=await button(st,'×','Light',{w:44,ghost:true});
await t(sp,'선택한 단축어를 다음 답변에 추가해요.','UI/Caption','Light','secondary',true);
async function command(name,description){
 const r=frame(name,324,'HORIZONTAL',sp);r.itemSpacing=8;r.counterAxisAlignItems='CENTER';pad(r,0,12);rule(r,'Light','top');
 const l=frame('단축어 이름과 용도',252,'VERTICAL',r);l.itemSpacing=4;
 await t(l,name,'UI/Label','Light');await t(l,description,'UI/Caption','Light','secondary',true);
 await t(r,'추가  ＋','UI/Caption','Light');return r;
}
const diary=await command('/일기','지금까지의 이야기를 일기로 정리');
const detail=await command('/묘사 강화','다음 장면을 더 자세하게 묘사');
sp.y=footer(slash).y-sp.height-8;
const applied=clone(lm,sec,'390 · 단축어가 추가된 작성란',x(3),y);screens.applied=applied.id;
const a=await filled(applied,'/일기');await label(sec,x(3),y-33,'04   선택한 이름만 표시');
const appliedAlt=clone(lm,sec,'390 · 묘사 강화 단축어 적용',1540,1100);screens.appliedAlt=appliedAlt.id;
const a2=await filled(appliedAlt,'/묘사 강화');await label(sec,1540,1067,'07   두 번째 단축어 예시');
const desktop=await tail(originals.LightDesktop,'Light',sec,48,1100,'1440 · 답변 끝 / 작성 도구');screens.desktop=desktop.id;
await label(sec,48,1067,'06   PC · 답변 끝과 입력 도구');
async function actionDialog(index,kind,title,copy,primary){
 const f=clone(lm,sec,'390 · '+title,x(index),y);screens[kind]=f.id;
 dim(f,.36);
 const d=panel(title,f,350,'Light',20,0);d.itemSpacing=16;
 await t(d,title,'UI/Title','Light','text',true);await t(d,copy,'UI/Body','Light','secondary',true);
 if(kind==='reroll'){
  const field=frame('리롤 추가 요청 입력',310,'VERTICAL',d);pad(field,12);field.cornerRadius=8;field.strokes=[paint('Light','border')];await t(field,'다음 답변에 반영할 내용 (선택)','UI/Caption','Light','secondary',true);
 }
 const r=frame('확인과 취소',310,'HORIZONTAL',d);r.itemSpacing=8;spacer(r);
 const close=await button(r,'취소','Light',{w:72});
 await button(r,primary,'Light',{w:112,primary:true});
 d.y=Math.round((f.height-d.height)/2);await goto(close,lm);
 return f;
}
const reroll=await actionDialog(4,'reroll','답변을 다시 만들까요?','에린이 같은 대사에 새로 답해요.','리롤');
await label(sec,x(4),y-33,'05a   리롤 확인');
const branch=await actionDialog(5,'branch','이 장면에서 분기할까요?','이 답변까지의 대화를 새 방에서 이어가요. 지금 대화는 그대로 남아요.','새 대화 시작');
await label(sec,x(5),y-33,'05b   분기 확인');
for(const root of [lm,originals.LightMobile,described,applied,appliedAlt]){
 const f=footer(root);
 if(root!==described)await goto(hotspot(root,named(f,'묘사 넣기'),'프로토타입 · 묘사 넣기'),described);
 await goto(hotspot(root,named(f,'단축어'),'프로토타입 · 단축어'),slash);
}
await goto(sClose,described);await goto(diary,applied);await goto(detail,appliedAlt);await goto(a.remove,described);await goto(a2.remove,described);
for(const [label,target]of [['리롤',reroll],['분기',branch]])await goto(named(body(lm),label),target);
page.flowStartingPoints=[...Object.entries(originals).map(([key,n])=>({nodeId:n.id,name:key+' · 긴 답변 읽기'})),{nodeId:lm.id,name:'모바일 v2 · 묘사·단축어·답변 액션'}];mutatedNodeIds.push(page.id);
const checks=Object.entries(screens).map(([k,id])=>({k,id}));
return {createdNodeIds:[...new Set(createdNodeIds)],mutatedNodeIds:[...new Set(mutatedNodeIds)],removedNodeIds:[...new Set(removedNodeIds)],section:sec.id,screens,checks,originals:Object.fromEntries(Object.entries(originals).map(([k,r])=>[k,{id:r.id,footer:footer(r).height,actions:body(r).children.at(-1).height,notices:r.findAllWithCriteria({types:['TEXT']}).filter(n=>n.characters.includes('자동으로 저장')).length}]))};
