await Promise.all(["Regular","Medium","Bold"].map(style=>figma.loadFontAsync({family:"Noto Sans KR",style})));
const allV=await figma.variables.getLocalVariablesAsync();
const allC=await figma.variables.getLocalVariableCollectionsAsync();
const collections=Object.fromEntries(allC.map(c=>[c.name,c.id]));
const styles=Object.fromEntries((await figma.getLocalTextStylesAsync()).map(s=>[s.name.replace("Studio/",""),s.id]));
const V={};for(const theme of ["Light","Dark"]){V[theme]=Object.fromEntries(allV.filter(v=>v.variableCollectionId===collections["Studio · "+theme]).map(v=>[v.name.replace("color/",""),v]));}
const S=Object.fromEntries(allV.filter(v=>v.variableCollectionId===collections["Studio · Layout"]).map(v=>[v.name,v]));
const created=[],changed=[];
function track(n){created.push(n.id);return n;}
function paint(theme,key){return figma.variables.setBoundVariableForPaint({type:"SOLID",color:{r:0,g:0,b:0}},"color",V[theme][key]);}
function fill(n,theme,key){n.fills=key?[paint(theme,key)]:[];}
function border(n,theme,key="border"){n.strokes=[paint(theme,key)];n.strokeWeight=1;}
function radius(n,r=8){for(const p of ["topLeftRadius","topRightRadius","bottomLeftRadius","bottomRightRadius"])n.setBoundVariable(p,S["radius/"+r]);}
function spacing(n,gap=0,pad=0){n.setBoundVariable("itemSpacing",S["space/"+gap]);for(const p of ["paddingTop","paddingRight","paddingBottom","paddingLeft"])n.setBoundVariable(p,S["space/"+pad]);}
function F(name,parent,dir="VERTICAL",w=null,h=null,theme="Light",bg=null,gap=0,pad=0){const n=track(figma.createAutoLayout(dir));n.name=name;fill(n,theme,bg);if(w!==null||h!==null)n.resize(w??100,h??100);spacing(n,gap,pad);if(parent)parent.appendChild(n);n.layoutSizingHorizontal=w!==null?"FIXED":parent&&parent.type!=="PAGE"?"FILL":"HUG";n.layoutSizingVertical=h!==null?"FIXED":"HUG";return n;}
async function T(value,parent,theme="Light",style="Body",key="text",width=null){const n=track(figma.createText());n.name=value.split("\n")[0].slice(0,50);await n.setTextStyleIdAsync(styles[style]);n.characters=value;fill(n,theme,key);parent.appendChild(n);if(width!==null){n.textAutoResize="HEIGHT";n.resize(width,22);n.layoutSizingHorizontal="FIXED";}else{n.textAutoResize="WIDTH_AND_HEIGHT";n.layoutSizingHorizontal="HUG";}return n;}
function componentNodes(n){return [n,...n.findAll(()=>true)].map(v=>v.id);}
