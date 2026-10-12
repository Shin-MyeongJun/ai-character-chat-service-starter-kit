/* Native Figma Plugin API. No API key, external network, or application-code changes. */
figma.showUI(__html__,{width:420,height:320});
figma.ui.onmessage=async msg=>{
 if(msg.type==='review'){
  try{
   const page=figma.root.children.find(p=>p.name==='모서리 · 발견 v1 · 2026-10-12');if(!page)throw Error('완성된 시안 페이지가 없습니다.');await figma.setCurrentPageAsync(page);
   const names=['Desktop Light','Desktop Dark','Mobile Light','Mobile Dark'];const files=[];const screens={};const overflow=[];const polishIds=[];const removedIds=[];
   const unfinished=await figma.getNodeByIdAsync('5:633');if(unfinished&&unfinished.parent?.id===page.id&&unfinished.name==='이전 생성 기록/Desktop Light'&&!unfinished.visible){removedIds.push(unfinished.id);unfinished.remove();}
   const palette=(await figma.variables.getLocalVariablesAsync()).filter(v=>v.name==='Light/accent'||v.name==='Dark/accent');
   function nodeTheme(node){let current=node;while(current&&current.type!=='PAGE'){if(/\bDark\b/.test(current.name))return 'Dark';current=current.parent;}return 'Light';}
   for(const svg of page.findAll(n=>n.type==='FRAME'&&n.name==='Brand mark / vector')){const token=palette.find(v=>v.name===nodeTheme(svg)+'/accent');if(token)for(const shape of svg.findAll(n=>'strokes'in n)){shape.strokes=shape.strokes.map(p=>p.type==='SOLID'?figma.variables.setBoundVariableForPaint(p,'color',token):p);}polishIds.push(svg.id);}
   for(const text of page.findAllWithCriteria({types:['TEXT']}).filter(n=>n.visible&&(n.name==='Mark'||n.name==='Footer label'&&n.characters.startsWith('✳')))){
    await Promise.all(text.getStyledTextSegments(['fontName']).map(s=>figma.loadFontAsync(s.fontName)));
    if(text.name==='Footer label'){text.characters=text.characters.replace(/^✳\s*/, '');polishIds.push(text.id);continue;}
    const theme=nodeTheme(text);
    const color=MOSEORI.colors[theme].accent;const svg=figma.createNodeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="'+color+'" stroke-width="1.8" stroke-linecap="round">'+MOSEORI.icons.brand+'</svg>');svg.name='Brand mark / vector';const parent=text.parent,index=parent.children.indexOf(text);parent.insertChild(index,svg);text.visible=false;const token=palette.find(v=>v.name===theme+'/accent');if(token)for(const shape of svg.findAll(n=>'strokes'in n)){shape.strokes=shape.strokes.map(p=>p.type==='SOLID'?figma.variables.setBoundVariableForPaint(p,'color',token):p);}polishIds.push(text.id,svg.id);
   }
   for(const name of ['Desktop Light','Desktop Dark']){const root=page.children.find(n=>n.name===name);const art=root?.findOne(n=>n.type==='RECTANGLE'&&n.name==='Featured art'&&n.parent.name==='Featured story');if(art){const parent=art.parent,index=parent.children.indexOf(art),w=art.width,h=art.height;const crop=figma.createFrame();crop.name='Featured art crop';crop.resize(w,h);crop.fills=[];crop.clipsContent=true;crop.cornerRadius=12;parent.insertChild(index,crop);crop.appendChild(art);art.resize(w,w*4/3);art.x=0;art.y=0;polishIds.push(crop.id,art.id);}}
   for(const instance of page.findAllWithCriteria({types:['INSTANCE']}).filter(n=>n.name==='Search/Filled')){const text=instance.findOne(n=>n.type==='TEXT'&&n.name==='Value');if(text&&text.characters!=='도서관'){await Promise.all(text.getStyledTextSegments(['fontName']).map(s=>figma.loadFontAsync(s.fontName)));text.characters='도서관';polishIds.push(text.id);}}
   for(const name of names){const frame=page.children.find(n=>n.name===name);if(!frame)throw Error('화면 누락: '+name);screens[name]={id:frame.id,width:frame.width,height:frame.height,instances:frame.findAllWithCriteria({types:['INSTANCE']}).length};
    for(const node of frame.findAll(n=>n.visible)){if(!node.parent||node.parent.type==='PAGE'||!('width'in node.parent))continue;const parent=node.parent;if(parent.clipsContent||node.layoutPositioning==='ABSOLUTE')continue;if(node.x<-.5||node.y<-.5||node.x+node.width>parent.width+.5||node.y+node.height>parent.height+.5)overflow.push({screen:name,id:node.id,name:node.name,parent:parent.name,x:node.x,y:node.y,width:node.width,height:node.height,parentWidth:parent.width,parentHeight:parent.height});}
    figma.ui.postMessage({type:'progress',message:name+' 검토 이미지 저장 중…'});files.push({name:name.toLowerCase().replace(/ /g,'-')+'.png',bytes:Array.from(await frame.exportAsync({format:'PNG',constraint:{type:'SCALE',value:1}}))});
   }
   for(const name of ['States Light','Components Light']){const board=page.children.find(n=>n.name===name);if(board)files.push({name:name.toLowerCase().replace(/ /g,'-')+'.png',bytes:Array.from(await board.exportAsync({format:'PNG',constraint:{type:'SCALE',value:.75}}))});}
   const texts=page.findAllWithCriteria({types:['TEXT']}).filter(n=>n.visible);const collections=await figma.variables.getLocalVariableCollectionsAsync();const variables=(await figma.variables.getLocalVariablesAsync()).filter(v=>collections.some(c=>c.id===v.variableCollectionId&&c.name.startsWith('모서리 v1/'))||collections.some(c=>c.id===v.variableCollectionId&&c.name.startsWith('모서리 v1 /')));
   const report={date:'2026-10-13',pageId:page.id,screens,textCount:texts.length,zeroSizeText:texts.filter(t=>t.width<=0||t.height<=0).map(n=>n.id),fontFamilies:[...new Set(texts.flatMap(t=>t.getStyledTextSegments(['fontName']).map(s=>s.fontName.family)))],overflow,polishMutatedNodeIds:polishIds,removedIncompleteNodeIds:removedIds,variables:variables.map(v=>({id:v.id,name:v.name,scopes:v.scopes,codeSyntax:v.codeSyntax})),componentSets:page.findAllWithCriteria({types:['COMPONENT_SET']}).map(n=>({id:n.id,name:n.name,variants:n.children.length}))};
   files.push({name:'native-qa.json',text:JSON.stringify(report,null,2)});figma.ui.postMessage({type:'review',message:'Figma 원본 화면 4개와 검증 기록을 준비했습니다.',files});
  }catch(error){figma.ui.postMessage({type:'error',message:String(error&&error.message||error)});}return;
 }
 if(msg.type!=='build')return;
 try{
  const M=MOSEORI,runName='모서리 · 발견 v1 · 2026-10-12';
  const prior=figma.root.children.find(p=>p.name===runName);
  if(prior){await figma.setCurrentPageAsync(prior);figma.viewport.scrollAndZoomIntoView(prior.children);figma.ui.postMessage({type:'done',message:'이미 생성된 페이지를 열었습니다. 중복 생성하지 않았습니다.'});return;}
  const available=await figma.listAvailableFontsAsync();
  for(const style of ['Regular','Medium','Bold']){if(!available.some(f=>f.fontName.family==='Noto Sans KR'&&f.fontName.style===style))throw Error('Noto Sans KR '+style+' 글꼴이 필요합니다.');await figma.loadFontAsync({family:'Noto Sans KR',style});}
  const page=figma.root.children.find(p=>p.name===runName+' · 생성 중')||figma.createPage();page.name=runName+' · 생성 중';await figma.setCurrentPageAsync(page);
  const created=[],styles={},vars={},components={},sets={},artHashes={},iconComponents={};
  const status=s=>figma.ui.postMessage({type:'progress',message:s});status('이미지와 테마 토큰 준비 중…');
  for(const [key,data] of Object.entries(msg.assets))artHashes[key]=figma.createImage(new Uint8Array(data)).hash;
  const existingCollections=await figma.variables.getLocalVariableCollectionsAsync();
  const primitives=existingCollections.find(c=>c.name==='모서리 v1 / Primitives')||figma.variables.createVariableCollection('모서리 v1 / Primitives');primitives.renameMode(primitives.defaultModeId,'Base');
  const themeCollection=existingCollections.find(c=>c.name==='모서리 v1 / Theme')||figma.variables.createVariableCollection('모서리 v1 / Theme');themeCollection.renameMode(themeCollection.defaultModeId,'Light');
  let darkMode=themeCollection.modes.find(m=>m.name==='Dark')?.modeId||null;if(!darkMode)try{darkMode=themeCollection.addMode('Dark');}catch(_){themeCollection.renameMode(themeCollection.defaultModeId,'Theme tokens');}
  const layout=existingCollections.find(c=>c.name==='모서리 v1 / Layout')||figma.variables.createVariableCollection('모서리 v1 / Layout');layout.renameMode(layout.defaultModeId,'Base');
  const existingVariables=await figma.variables.getLocalVariablesAsync();
  const rgb=h=>({r:parseInt(h.slice(1,3),16)/255,g:parseInt(h.slice(3,5),16)/255,b:parseInt(h.slice(5,7),16)/255});
  // Adapted from figma-generate-library/scripts/createSemanticTokens.js.
  function variable(name,coll,type,values,scopes,css){const v=existingVariables.find(v=>v.name===name&&v.variableCollectionId===coll.id)||figma.variables.createVariable(name,coll,type);for(const [mode,val]of Object.entries(values))v.setValueForMode(mode,val);v.scopes=scopes;v.setVariableCodeSyntax('WEB','var(--'+css+')');return v;}
  const primitiveVars={};for(const theme of ['Light','Dark'])for(const [key,hex]of Object.entries(M.colors[theme])){primitiveVars[theme+'/'+key]=variable(theme+'/'+key,primitives,'COLOR',{[primitives.defaultModeId]:{...rgb(hex),a:1}},[],'primitive-'+theme.toLowerCase()+'-'+key);}
  for(const key of Object.keys(M.colors.Light)){
   const scopes=key==='line'?['STROKE_COLOR']:['FRAME_FILL','SHAPE_FILL','TEXT_FILL','STROKE_COLOR'];
   if(darkMode){const v=variable(key,themeCollection,'COLOR',{[themeCollection.defaultModeId]:{type:'VARIABLE_ALIAS',id:primitiveVars['Light/'+key].id},[darkMode]:{type:'VARIABLE_ALIAS',id:primitiveVars['Dark/'+key].id}},scopes,key);vars['Light/'+key]=v;vars['Dark/'+key]=v;}
   else for(const theme of ['Light','Dark'])vars[theme+'/'+key]=variable(theme+'/'+key,themeCollection,'COLOR',{[themeCollection.defaultModeId]:{type:'VARIABLE_ALIAS',id:primitiveVars[theme+'/'+key].id}},scopes,key);
  }
  for(const value of [0,2,3,4,6,8,10,12,14,16,20,24,28,32,40,44,48,64])vars['space/'+value]=variable('space/'+value,layout,'FLOAT',{[layout.defaultModeId]:value},['GAP'],'space-'+value);
  for(const value of [8,12,16,20,24,999])vars['radius/'+value]=variable('radius/'+value,layout,'FLOAT',{[layout.defaultModeId]:value},['CORNER_RADIUS'],'radius-'+value);
  const existingStyles=await figma.getLocalTextStylesAsync();
  for(const [name,[size,line,weight]]of Object.entries(M.typography)){const s=existingStyles.find(s=>s.name==='모서리 v1/'+name)||figma.createTextStyle();s.name='모서리 v1/'+name;s.fontName={family:'Noto Sans KR',style:weight};s.fontSize=size;s.lineHeight={unit:'PIXELS',value:line};styles[name]=s;}
  function track(node){created.push(node.id);return node;}
  function paint(key,theme){return figma.variables.setBoundVariableForPaint({type:'SOLID',color:rgb(M.colors[theme][key])},'color',vars[theme+'/'+key]);}
  function color(node,key,theme,field='fills'){node[field]=[paint(key,theme)];}
  function numeric(node,field,val,prefix){node[field]=val;const v=vars[prefix+'/'+val];if(v)node.setBoundVariable(field,v);}
  function radius(node,r){if(!r)return;node.cornerRadius=r;for(const prop of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])if(vars['radius/'+r])node.setBoundVariable(prop,vars['radius/'+r]);}
  function paddings(p){if(!Array.isArray(p))return[p||0,p||0,p||0,p||0];return p.length===2?[p[0],p[1],p[0],p[1]]:p;}
  function key(f,t,v){return f+'|'+t+'|'+v;}
  function iconSvg(o,theme){return '<svg xmlns="http://www.w3.org/2000/svg" width="'+o.w+'" height="'+o.h+'" viewBox="0 0 24 24" fill="none" stroke="'+M.colors[theme][o.color]+'" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+M.icons[o.icon]+'</svg>';}
  function overrideNode(node,patch,theme){if(patch.text!==undefined&&node.type==='TEXT')node.characters=patch.text;if(patch.asset&&'fills'in node&&Array.isArray(node.fills)&&node.fills.some(p=>p.type==='IMAGE'))node.fills=[{type:'IMAGE',imageHash:artHashes[patch.asset],scaleMode:'FILL'}];if(patch.icon&&node.type==='INSTANCE'){const w=node.width,h=node.height;node.swapComponent(iconComponents[theme+'/'+patch.icon]);node.resize(w,h);}}
  for(const theme of ['Light','Dark'])for(const [index,icon]of Object.keys(M.icons).entries()){const existing=page.findOne(n=>n.type==='COMPONENT'&&n.name==='Icon/'+theme+'/'+icon);if(existing){iconComponents[theme+'/'+icon]=existing;continue;}const c=track(figma.createComponent());c.name='Icon/'+theme+'/'+icon;c.resize(24,24);c.fills=[];const svg=figma.createNodeFromSvg(iconSvg({icon,w:24,h:24,color:'muted'},theme));for(const child of [...svg.children])c.appendChild(child);svg.remove();c.x=5000+index*48;c.y=theme==='Light'?-200:-120;iconComponents[theme+'/'+icon]=c;}
  async function build(o,parent,theme,isComponent=false){
   let node;
   if(o.type==='instance'){
    const master=components[key(o.family,o.theme,o.variant)];if(!master)throw Error('컴포넌트 누락: '+key(o.family,o.theme,o.variant));node=track(master.createInstance());parent.appendChild(node);node.name=o.family+'/'+o.variant;
    const defaults=MOSEORI.defs.find(d=>d.family===o.family&&d.theme===o.theme&&d.variant===o.variant);const defaultsQueue=[defaults.tree];while(defaultsQueue.length){const item=defaultsQueue.shift();if(item.type==='text'){const target=node.findOne(n=>n.type==='TEXT'&&n.name===item.name);if(target)target.characters=item.text;}defaultsQueue.push(...item.children||[]);}
    for(const [name,patch]of Object.entries(o.overrides)){const target=node.findOne(n=>n.name===name);if(target)overrideNode(target,patch,theme);}
    if(o.w!=null)node.resize(o.w,node.height);if(o.h!=null)node.resize(node.width,o.h);if(o.pad!=null){const p=paddings(o.pad);['paddingTop','paddingRight','paddingBottom','paddingLeft'].forEach((field,i)=>numeric(node,field,p[i],'space'));}
    return node;
   }
   if(o.type==='text'){
    node=track(figma.createText());parent.appendChild(node);node.name=o.name;await node.setTextStyleIdAsync(styles[o.style].id);node.characters=o.text;color(node,o.color,theme);
    if(o.w!=null){node.textAutoResize='HEIGHT';node.resize(o.w,Math.max(1,node.height));}else node.textAutoResize='WIDTH_AND_HEIGHT';return node;
   }
   if(o.type==='icon'){node=track(iconComponents[theme+'/'+o.icon].createInstance());parent.appendChild(node);node.name=o.name;node.resize(o.w,o.h);for(const child of node.findAll(n=>'strokes'in n))if(child.strokes.length)color(child,o.color,theme,'strokes');return node;}
   if(o.type==='image'||o.type==='shape'){node=track(figma.createRectangle());parent.appendChild(node);node.name=o.name;node.resize(o.w,o.h);radius(node,o.r);if(o.type==='image')node.fills=[{type:'IMAGE',imageHash:artHashes[o.asset],scaleMode:'FILL'}];else if(o.bg)color(node,o.bg,theme);return node;}
   node=track(isComponent?figma.createComponent():figma.createFrame());parent.appendChild(node);node.name=o.name;node.layoutMode=o.dir==='row'?'HORIZONTAL':'VERTICAL';node.fills=o.bg?[paint(o.bg,theme)]:[];node.resize(o.w||100,o.h||100);node.primaryAxisSizingMode=(o.dir==='row'?o.w:o.h)==null?'AUTO':'FIXED';node.counterAxisSizingMode=(o.dir==='row'?o.h:o.w)==null?'AUTO':'FIXED';node.primaryAxisAlignItems=o.justify==='center'?'CENTER':o.justify==='end'?'MAX':'MIN';node.counterAxisAlignItems=o.align==='center'?'CENTER':o.align==='end'?'MAX':'MIN';numeric(node,'itemSpacing',o.gap||0,'space');const pad=paddings(o.pad);['paddingTop','paddingRight','paddingBottom','paddingLeft'].forEach((field,i)=>numeric(node,field,pad[i],'space'));radius(node,o.r);node.clipsContent=!!o.clip;if(o.opacity)node.opacity=o.opacity;if(o.stroke){node.strokes=[paint(o.stroke,theme)];node.strokeWeight=o.strokeWidth||1;}if(darkMode)node.setExplicitVariableModeForCollection(themeCollection,theme==='Dark'?darkMode:themeCollection.defaultModeId);
   for(const child of o.children||[])await build(child,node,theme);return node;
  }
  status('버튼·검색·필터·카드 컴포넌트를 만드는 중…');
  // Adapted from createComponentWithVariants: create native components, combine, then grid.
  const families=[...new Set(M.defs.map(d=>d.family))];let libraryY=240;
  for(const family of families){const existingSet=page.findOne(n=>n.type==='COMPONENT_SET'&&n.name==='모서리/'+family);if(existingSet){for(const d of M.defs.filter(d=>d.family===family)){const comp=existingSet.children.find(c=>c.name==='Theme='+d.theme+', Variant='+d.variant);if(!comp)throw Error('기존 컴포넌트 변형 누락: '+family+' '+d.variant);components[key(family,d.theme,d.variant)]=comp;}sets[family]=existingSet.id;libraryY=Math.max(libraryY,existingSet.y+existingSet.height+120);continue;}const variants=[];for(const d of M.defs.filter(d=>d.family===family)){const comp=await build(d.tree,page,d.theme,true);comp.name='Theme='+d.theme+', Variant='+d.variant;comp.description='모서리 '+family+' · '+d.variant;for(const text of comp.findAllWithCriteria({types:['TEXT']})){if(['Label','Value','Title','Description','Genre','Author'].includes(text.name)){const property=comp.addComponentProperty(text.name,'TEXT',text.characters);text.componentPropertyReferences={characters:property};}}
   components[key(family,d.theme,d.variant)]=comp;variants.push(comp);}
   const set=track(figma.combineAsVariants(variants,page));set.name='모서리/'+family;set.description='Light/Dark 테마와 상태 변형. 모든 화면은 이 컴포넌트의 인스턴스를 사용합니다.';const maxW=Math.max(...variants.map(n=>n.width)),maxH=Math.max(...variants.map(n=>n.height));variants.forEach((c,i)=>{c.x=32+(i%5)*(maxW+32);c.y=32+Math.floor(i/5)*(maxH+32);});set.resize(64+5*(maxW+32),64+Math.ceil(variants.length/5)*(maxH+32));set.x=5000;set.y=libraryY;libraryY+=set.height+120;sets[family]=set.id;}
  status('PC·모바일 메인과 상태 보드 생성 중…');const screens={};
  for(const [theme,mobile,x,y]of [['Light',false,200,200],['Dark',false,1800,200],['Light',true,3400,200],['Dark',true,3900,200]]){const name=(mobile?'Mobile':'Desktop')+' '+theme;const partial=page.children.find(n=>n.name===name);if(partial){partial.name='이전 생성 기록/'+name;partial.visible=false;partial.x=-1800;}const f=await build(M.screen(theme,mobile,true),page,theme);f.x=x;f.y=y;screens[name]=f;}
  for(const [theme,x]of [['Light',200],['Dark',1800]]){const state=await build(M.stateBoard(theme),page,theme);state.x=x;state.y=2000;const board=await build(M.componentBoard(theme),page,theme);board.x=x;board.y=3800;}
  const notes=await build(M.notesBoard(),page,'Light');notes.x=3400;notes.y=2200;
  for(const [name,f]of Object.entries(screens)){const target=screens[name.replace(/Light|Dark/,name.includes('Light')?'Dark':'Light')];for(const toggle of f.findAll(n=>n.type==='INSTANCE'&&n.name.startsWith('ThemeToggle/')))await toggle.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:target.id,navigation:'NAVIGATE',transition:null,preserveScrollPosition:true}]}]);}
  const all=[...created,...page.findAll(()=>true).map(n=>n.id)];const texts=page.findAllWithCriteria({types:['TEXT']});const zero=texts.filter(t=>t.width<=0||t.height<=0).map(n=>n.id);
  page.name=runName;figma.currentPage.selection=[screens['Desktop Light']];figma.viewport.scrollAndZoomIntoView([screens['Desktop Light'],screens['Mobile Light']]);
  const report={pageId:page.id,screens:Object.fromEntries(Object.entries(screens).map(([k,n])=>[k,{id:n.id,width:n.width,height:n.height}])),sets,variantCount:M.defs.length,textCount:texts.length,zeroSizeText:zero,themeMode:darkMode?'Native Light/Dark modes':'Single-mode plan: separate Light/Dark tokens and component variants',createdNodeIds:[...new Set(all)]};figma.ui.postMessage({type:'done',message:'메인 4개, 상태 2개, 컴포넌트 보드 2개와 구현 메모를 생성했습니다.',report});
 }catch(error){figma.ui.postMessage({type:'error',message:String(error&&error.message||error)});}
};
