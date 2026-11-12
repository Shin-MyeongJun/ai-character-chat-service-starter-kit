const createdNodeIds=[],mutatedNodeIds=[],removedNodeIds=[];
const page=await figma.getNodeByIdAsync(BASE.foundations.pages.review);
await figma.setCurrentPageAsync(page);
await Promise.all(['Regular','Medium','Bold'].map(style=>figma.loadFontAsync({family:'Noto Sans KR',style})));
const S=BASE.foundations,B=BASE.components.components;
const vars={};
for(const [th,rs] of Object.entries(S.colors)){
 vars[th]=Object.fromEntries(await Promise.all(Object.entries(rs).map(async([role,id])=>[role,await figma.variables.getVariableByIdAsync(id)])));
}
const get=id=>figma.getNodeByIdAsync(id);
function rec(n){createdNodeIds.push(n.id);return n;}
function tree(n){rec(n);for(const d of n.findAll(()=>true))rec(d);return n;}
function del(n){removedNodeIds.push(n.id);n.remove();}
function paint(th,role){return figma.variables.setBoundVariableForPaint({type:'SOLID',color:{r:0,g:0,b:0}},'color',vars[th][role]);}
function frame(name,w,dir='VERTICAL',parent=null){
 const f=rec(figma.createAutoLayout(dir));f.name=name;f.resize(w,1);f.primaryAxisSizingMode=dir==='VERTICAL'?'AUTO':'FIXED';f.counterAxisSizingMode=dir==='VERTICAL'?'FIXED':'AUTO';f.fills=[];if(parent)parent.appendChild(f);return f;
}
function pad(f,x,y=x){f.paddingLeft=x;f.paddingRight=x;f.paddingTop=y;f.paddingBottom=y;}
function fill(f,th,role){f.fills=role?[paint(th,role)]:[];}
function rule(f,th,edge){f.strokes=[paint(th,'border')];f.strokeTopWeight=edge==='top'?1:0;f.strokeBottomWeight=edge==='bottom'?1:0;f.strokeLeftWeight=edge==='left'?1:0;f.strokeRightWeight=0;}
async function t(p,copy,style,th,role='text',wrap=false){
 const n=rec(figma.createText());n.name=copy.split('\n')[0].slice(0,65);await n.setTextStyleIdAsync(S.styles[style]);n.characters=copy;fill(n,th,role);p.appendChild(n);
 if(wrap){n.textAutoResize='HEIGHT';n.resize(Math.max(1,p.width-(p.paddingLeft||0)-(p.paddingRight||0)),n.height);if(p.type==='FRAME'&&p.layoutMode!=='NONE')n.layoutSizingHorizontal='FILL';}
 return n;
}
function spacer(p){const f=frame('여백',1,'HORIZONTAL',p);f.layoutSizingHorizontal='FILL';return f;}
async function button(p,copy,th,{w=96,primary=false,h=44,ghost=false}={}){
 const f=frame(copy,w,'HORIZONTAL',p);f.resize(w,h);f.primaryAxisSizingMode='FIXED';f.counterAxisSizingMode='FIXED';f.primaryAxisAlignItems='CENTER';f.counterAxisAlignItems='CENTER';f.cornerRadius=8;fill(f,th,primary?'action':ghost?null:'surface');if(!ghost&&!primary)f.strokes=[paint(th,'border')];await t(f,copy,'UI/Label',th,primary?'onAction':'text');return f;
}
function place(n,p,x,y){p.appendChild(n);if('layoutMode'in p&&p.layoutMode!=='NONE')n.layoutPositioning='ABSOLUTE';n.x=x;n.y=y;return n;}
async function instance(p,id,name=null){
 const c=await get(id);const n=rec(c.createInstance());p.appendChild(n);if(name)n.name=name;return n;
}
function select(n,name){return n.children.find(c=>c.name===name);}
function named(n,name){return n.findOne(c=>c.name===name);}
function footer(n){return select(n,'작성 영역 · 고정');}
function view(n){return select(n,'대화 본문 · 세로 스크롤');}
function body(n){return view(n).children[0];}
function clone(n,p,name,x,y){const c=tree(n.clone());c.name=name;place(c,p,x,y);return c;}
async function goto(n,to){await n.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:to.id,navigation:'NAVIGATE',transition:null,resetScrollPosition:false}]}]);mutatedNodeIds.push(n.id);}
function hotspot(root,child,name){
 const origin=root.absoluteBoundingBox,r=child.absoluteBoundingBox;
 if(!origin||!r)throw new Error('No bounds for '+name);
 const f=rec(figma.createFrame());f.name=name;f.fills=[];f.resize(r.width,r.height);place(f,root,r.x-origin.x,r.y-origin.y);return f;
}
function dim(root,opacity){
 const f=rec(figma.createRectangle());f.name='배경 어둡게';f.resize(root.width,root.height);f.fills=[{type:'SOLID',color:{r:0,g:0,b:0},opacity}];place(f,root,0,0);return f;
}
function section(name,x,y,w,h){
 const s=rec(figma.createSection());s.name=name;s.x=x;s.y=y;s.resizeWithoutConstraints(w,h);s.fills=[{type:'SOLID',color:{r:.92,g:.92,b:.93}}];return s;
}
async function heading(section,title,sub){
 const f=frame('검토 보드 안내',section.width-96,'VERTICAL');place(f,section,48,32);f.itemSpacing=8;
 await t(f,title,'Review/Title','Light');await t(f,sub,'UI/Body','Light','secondary',true);
}
async function label(section,x,y,copy){const f=frame('시안 이름',1440,'VERTICAL');place(f,section,x,y);await t(f,copy,'UI/Label','Light');}
function panel(name,root,w,th,x,y){
 const p=frame(name,w);fill(p,th,'surface');pad(p,20);p.itemSpacing=12;p.cornerRadius=12;p.strokes=[paint(th,'border')];place(p,root,x,y);return p;
}
function removeRootHotspots(root){
 for(const n of [...root.children])if(n.name.startsWith('프로토타입 ·'))del(n);
}
