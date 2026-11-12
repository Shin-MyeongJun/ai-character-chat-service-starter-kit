// Figma authoring source. Run only in the dedicated chat design file.
const createdNodeIds = [];
const page = figma.root.children[0];
page.name = '01 · 대표 대화 · Review';
const library = figma.createPage(); library.name = '02 · 구성 요소';
await figma.setCurrentPageAsync(library);
createdNodeIds.push(page.id, library.id);
await Promise.all(['Regular', 'Medium', 'Bold'].map(style => figma.loadFontAsync({family:'Noto Sans KR',style})));
const fontNames = (await figma.listAvailableFontsAsync()).filter(f => f.fontName.family === 'Noto Sans KR').map(f => f.fontName);
const primitive = await createVariableCollection('Chat · Primitive', ['Value']);
const hexes = ['FFFFFF','F7F7F8','F1F1F3','E5E5E8','202024','65656F','252529','EEEEF1','1C1C1E','222225','27272A','303034','3D3D42','F4F4F5','B2B2BB','F0F0F2','35353B'];
const primitiveTokens = await createSemanticTokens(primitive.collection, primitive.modeIds, hexes.map(h=>({name:'neutral/'+h,type:'COLOR',values:{Value:'#'+h},scopes:[],codeSyntax:{WEB:'var(--chat-neutral-'+h.toLowerCase()+')'}})));
const palettes = {Light:{canvas:'FFFFFF',subtle:'F7F7F8',surface:'FFFFFF',border:'E5E5E8',text:'202024',secondary:'65656F',action:'252529',onAction:'FFFFFF',selection:'EEEEF1',disabled:'E5E5E8'},Dark:{canvas:'1C1C1E',subtle:'222225',surface:'27272A',border:'3D3D42',text:'F4F4F5',secondary:'B2B2BB',action:'F0F0F2',onAction:'202024',selection:'35353B',disabled:'3D3D42'}};
const colors = {};
for (const [theme, roles] of Object.entries(palettes)) {
  const c = await createVariableCollection('Chat · '+theme, ['Value']);
  const t = await createSemanticTokens(c.collection,c.modeIds,Object.entries(roles).map(([name,h])=>({name:'color/'+name,type:'COLOR',values:{Value:{type:'VARIABLE_ALIAS',id:primitiveTokens.variables['neutral/'+h].id}},scopes:name==='border'?['STROKE_COLOR']:['FRAME_FILL','SHAPE_FILL','TEXT_FILL','STROKE_COLOR'],codeSyntax:{WEB:'var(--chat-'+name.replace(/[A-Z]/g,s=>'-'+s.toLowerCase())+')'}})));
  colors[theme]=Object.fromEntries(Object.entries(t.variables).map(([k,v])=>[k.split('/')[1],v.id]));
}
const dims = await createVariableCollection('Chat · Geometry',['Value']);
const dimensionTokens=await createSemanticTokens(dims.collection,dims.modeIds,[...[0,4,8,12,16,20,24,32,40,48].map(v=>({name:'space/'+v,type:'FLOAT',values:{Value:v},scopes:['GAP'],codeSyntax:{WEB:'var(--chat-space-'+v+')'}})),...[8,12].map(v=>({name:'radius/'+v,type:'FLOAT',values:{Value:v},scopes:['CORNER_RADIUS'],codeSyntax:{WEB:'var(--chat-radius-'+v+')'}}))]);
const styles={};
for (const [name,size,line,weight] of [['Reading/Narration',16,29,'Regular'],['Reading/Dialogue',16,28,'Medium'],['UI/Body',14,22,'Regular'],['UI/Label',14,22,'Medium'],['UI/Caption',12,20,'Regular'],['UI/Title',18,28,'Bold'],['Review/Title',32,44,'Bold']]) {
  const s=figma.createTextStyle();s.name='Chat/'+name;s.fontName={family:'Noto Sans KR',style:weight};s.fontSize=size;s.lineHeight={unit:'PIXELS',value:line};styles[name]=s.id;
}
return {createdNodeIds,pages:{review:page.id,library:library.id},colors,geometry:Object.fromEntries(Object.entries(dimensionTokens.variables).map(([k,v])=>[k,v.id])),styles,fontNames,collections:[primitive.collection.id,dims.collection.id],note:'Starter 1-mode limit: light and dark semantic collections are separate. Exact Studio neutral values retained.'};
