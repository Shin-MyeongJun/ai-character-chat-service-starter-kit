/* Shared design description for the review preview and native Figma importer. */
(function(root){
const colors={
 Light:{paper:'#FCFBF9',surface:'#FFFFFF',subtle:'#F3F1EE',hover:'#ECE7E2',ink:'#28262B',muted:'#6E6872',line:'#E5DFD9',accent:'#B74B40',accentBg:'#B74B40',onAccent:'#FFFFFF',warm:'#FAE9E3',focus:'#5562C9',hero:'#1A252D',onHero:'#FFF9EF',heroMuted:'#C9D1D5',error:'#B23535',errorBg:'#FFF0EE',success:'#2D6A51'},
 Dark:{paper:'#151517',surface:'#1F1F22',subtle:'#29282D',hover:'#333139',ink:'#F5F3F0',muted:'#B7AFBD',line:'#3C3841',accent:'#FFA18F',accentBg:'#F49382',onAccent:'#291A18',warm:'#3C2827',focus:'#ABB5FF',hero:'#1A252D',onHero:'#FFF9EF',heroMuted:'#C9D1D5',error:'#FFAAA5',errorBg:'#3A2326',success:'#A3DFBD'}
};
const typography={Hero:[32,44,'Bold'],H1:[28,40,'Bold'],H2:[22,32,'Bold'],Title:[18,28,'Bold'],Body:[14,22,'Regular'],Label:[14,22,'Medium'],Small:[12,20,'Regular'],SmallStrong:[12,20,'Bold'],Micro:[11,18,'Medium']};
colors.Light.accentHover='#A43F35';colors.Dark.accentHover='#FFAA97';
const works=[
 {id:'archive',title:'밤의 기록 보관소',desc:'사라진 기억을 보관하는 도서관. 당신 앞으로 도착한 편지 한 통.',genre:'미스터리',author:'별의서재',tags:'#도서관  #비밀',badge:'추천'},
 {id:'bluehour',title:'푸른 시간의 역',desc:'막차가 떠난 플랫폼에서 다시 만난 오래된 친구.',genre:'로맨스',author:'유월',tags:'#재회  #현대',badge:''},
 {id:'garden',title:'유리 온실의 계약',desc:'꽃이 사람의 비밀을 기억한다는 도시의 작은 온실.',genre:'판타지',author:'온실지기',tags:'#마법  #힐링',badge:'NEW'},
 {id:'radio',title:'새벽 2시 라디오',desc:'전파가 닿지 않는 곳에서 들려온 당신만의 방송.',genre:'일상',author:'모노',tags:'#새벽  #대화',badge:''}
];
const icons={
 search:'<circle cx="10.8" cy="10.8" r="7.2"/><path d="m16 16 4.6 4.6"/>',
 home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
 compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5Z"/>',
 chat:'<path d="M21 11.5a8.6 8.6 0 0 1-9 8.5 10 10 0 0 1-4-.8L3 21l1.6-5A8.2 8.2 0 0 1 3 11.5a9 9 0 0 1 18 0Z"/>',
 pen:'<path d="m14 4 6 6M4 20l5-1 12-12a2.1 2.1 0 0 0-6-3L4 15Z"/>',
 moon:'<path d="M20.6 14A9 9 0 0 1 10 3.4 9 9 0 1 0 20.6 14Z"/>',
 sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
 user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
 arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
 chevron:'<path d="m9 5 7 7-7 7"/>',
 collapse:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m7-12-3 4 3 4"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 filter:'<path d="M3 7h18M3 17h18"/><circle cx="8" cy="7" r="2.5" fill="currentColor"/><circle cx="16" cy="17" r="2.5" fill="currentColor"/>',
 retry:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7"/>',
 alert:'<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3v.1"/>',
 menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
 sparkle:'<path d="m12 2 2.7 7.3L22 12l-7.3 2.7L12 22l-2.7-7.3L2 12l7.3-2.7Z"/>'
};
function n(type,name,p,children=[]){return {type,name,...p,children};}
function row(name,w,h,gap=0,pad=0,bg=null,children=[]){return n('frame',name,{dir:'row',w,h,gap,pad,bg,align:h==null?'start':'center'},children);}
function col(name,w,h,gap=0,pad=0,bg=null,children=[]){return n('frame',name,{dir:'column',w,h,gap,pad,bg},children);}
function txt(name,text,style='Body',color='ink',w){return n('text',name,{text,style,color,w});}
function ic(name,color='muted',size=20){return n('icon','Icon/'+name,{icon:name,color,w:size,h:size});}
function art(name,id,w,h,r=12){return n('image',name,{asset:id,w,h,r});}
function ref(family,theme,variant,overrides={},p={}){return n('instance',family,{family,theme,variant,overrides,...p});}
const defs=[];
function def(family,theme,variant,tree){defs.push({family,theme,variant,tree});return tree;}
for(const theme of ['Light','Dark']){
 for(const kind of ['Primary','Secondary']) for(const state of ['Default','Hover','Focus','Disabled']){
  const isP=kind==='Primary',disabled=state==='Disabled';
  const f=row('Button',null,44,8,[0,16],disabled?'subtle':isP?(state==='Hover'?'accentHover':'accentBg'):state==='Hover'?'hover':'surface',[txt('Label','작품 둘러보기','Label',disabled?'muted':isP?'onAccent':'ink'),ic('arrow',disabled?'muted':isP?'onAccent':'ink',16)]);
  f.r=12;f.stroke=state==='Focus'?'focus':isP?null:'line';f.strokeWidth=state==='Focus'?2:1;f.disabled=disabled;
  def('Button',theme,kind+'/'+state,f);
 }
 for(const family of ['Chip','Tab','MenuItem']) for(const state of ['Default','Selected','Hover','Focus','Disabled']){
  const active=state==='Selected';const menu=family==='MenuItem';
  const f=row(family,menu?184:null,44,8,[0,menu?12:16],active?(menu?'warm':'ink'):state==='Hover'?'hover':family==='Chip'?'surface':null,
   [...(menu?[ic('compass',active?'accent':'muted')]:[]),txt('Label',menu?'발견':'전체','Label',active?(menu?'accent':'paper'):'muted')]);
  f.r=menu?12:999;f.stroke=state==='Focus'?'focus':family==='Chip'&&!active?'line':null;f.strokeWidth=state==='Focus'?2:1;f.disabled=state==='Disabled';if(f.disabled)f.opacity=.5;
  def(family,theme,state,f);
 }
 for(const state of ['Default','Focus','Filled','Disabled']){
  const f=row('Search',360,44,10,[0,14],state==='Disabled'?'subtle':'surface',[ic('search'),txt('Value',state==='Filled'?'도서관':'제목, 분위기, 키워드 검색','Body',state==='Filled'?'ink':'muted',288)]);
  f.r=12;f.stroke=state==='Focus'?'focus':'line';f.strokeWidth=state==='Focus'?2:1;f.disabled=state==='Disabled';def('Search',theme,state,f);
 }
 for(const state of ['Off','On','Pending']){
  const f=row('AdultFilter',182,44,8,[0,10],state==='On'?'warm':null,[txt('Age','19','SmallStrong',state==='On'?'accent':'muted'),txt('Label','성인 콘텐츠 포함','SmallStrong',state==='On'?'accent':'muted')]);
  const toggle=row('Switch',32,20,0,3,state==='On'?'accentBg':'line',[]);toggle.r=999;toggle.justify=state==='On'?'end':'start';toggle.children.push(n('shape','Thumb',{w:14,h:14,r:999,bg:state==='On'?'onAccent':'surface'}));f.children.push(toggle);f.disabled=state==='Pending';if(f.disabled)f.opacity=.45;def('AdultFilter',theme,state,f);
 }
 const toggle=row('ThemeToggle',44,44,0,0,'surface',[ic(theme==='Light'?'moon':'sun')]);toggle.r=12;toggle.justify='center';toggle.stroke='line';toggle.action='theme';def('ThemeToggle',theme,'Default',toggle);
 for(const size of ['Desktop','Mobile']) for(const state of ['Default','Hover','Focus','Loading','ImageMissing']){
  const w=size==='Desktop'?276:173,coverH=w*4/3;
  const image=state==='Loading'?n('shape','Cover',{w,h:coverH,r:12,bg:'subtle'}):state==='ImageMissing'?col('Cover',w,coverH,12,16,'subtle',[ic('sparkle','muted',32),txt('Fallback','새로운 이야기','Small','muted')]):art('Cover','archive',w,coverH);
  if(state==='ImageMissing'){image.justify='center';image.align='center';image.r=12;}
  let children=[image];
  if(state==='Loading') children.push(n('shape','Skeleton/Title',{w:w*.7,h:20,r:8,bg:'subtle'}),n('shape','Skeleton/Body',{w,h:16,r:8,bg:'subtle'}));
  else children.push(row('Metadata',w,20,8,0,null,[txt('Genre','미스터리','SmallStrong','accent'),txt('Author','별의서재','Small','muted')]),txt('Title','밤의 기록 보관소',size==='Mobile'?'Label':'Title','ink',w),txt('Description','사라진 기억을 보관하는 도서관. 당신 앞으로 도착한 편지 한 통.','Small','muted',w));
  const f=col('StoryCard',w,null,8,0,state==='Hover'?'subtle':null,children);f.r=12;f.stroke=state==='Focus'?'focus':null;f.strokeWidth=2;def('StoryCard',theme,size+'/'+state,f);
 }
 for(const state of ['Default','Active']){
  const f=col('BottomItem',89.5,60,4,8,null,[ic('compass',state==='Active'?'accent':'muted'),txt('Label','발견','Micro',state==='Active'?'accent':'muted')]);f.align='center';f.justify='center';def('BottomItem',theme,state,f);
 }
}
function button(theme,label,primary=true,p={}){return ref('Button',theme,(primary?'Primary':'Secondary')+'/Default',{Label:{text:label}},p);}
function card(theme,work,mobile=false,state='Default'){return ref('StoryCard',theme,(mobile?'Mobile':'Desktop')+'/'+state,{Cover:{asset:work.id},Title:{text:work.title},Description:{text:work.desc},Genre:{text:work.genre},Author:{text:work.author}});}
function heading(title,subtitle,w,theme){return row('Section heading',w,null,16,0,null,[col('Section copy',w-112,null,2,0,null,[txt('Section title',title,'H2'),...(subtitle?[txt('Section description',subtitle,'Small','muted')]:[])]),row('View all',96,44,4,0,null,[txt('View all label','전체 보기','Small','muted'),ic('chevron','muted',14)])]);}
function logo(w=140){return row('Brand',w,44,8,0,null,[txt('Mark','✳','H1','accent'),txt('Wordmark','모서리','H2')]);}
function sidebar(theme){
 return col('Sidebar',224,null,24,[24,20],'surface',[
  row('Brand row',184,44,4,0,null,[logo(148),ic('collapse')]),
  col('Primary navigation',184,null,8,0,null,[ref('MenuItem',theme,'Selected'),ref('MenuItem',theme,'Default',{Label:{text:'둘러보기'},'Icon/compass':{icon:'search'}}),ref('MenuItem',theme,'Default',{Label:{text:'내 대화'},'Icon/compass':{icon:'chat'}})]),
  col('Recent conversations',184,null,16,[16,0],null,[txt('Caption','이어갈 이야기','SmallStrong','muted'),...works.slice(0,2).map(w=>row('Recent/'+w.id,184,56,10,0,null,[art('Avatar',w.id,40,48,8),col('Copy',134,null,3,0,null,[txt('Title',w.title,'SmallStrong','ink',134),txt('Preview','다음 장면이 기다려요','Micro','muted',134)])]))]),
  col('Sidebar spacer',184,440,0,0,null,[]),
  col('Studio entry',184,null,12,16,'subtle',[ic('pen','accent'),txt('Studio title','내 이야기를 만들어요','SmallStrong'),txt('Studio description','캐릭터와 세계를 담는 공간','Small','muted',152),button(theme,'제작 스튜디오',false,{w:152})]),
  txt('Sidebar note','이야기가 시작되는 곳','Micro','muted')
 ]);
}
function header(theme,mobile,adult){
 if(mobile)return col('Header',390,null,12,[12,16],'paper',[
  row('Top bar',358,44,8,0,null,[logo(254),ref('ThemeToggle',theme,'Default'),row('Account',44,44,0,0,null,[ic('user')])]),
  ref('Search',theme,'Default',{}, {w:358}),
  row('Navigation and content policy',358,44,4,0,null,[ref('Tab',theme,'Selected',{Label:{text:'발견'}}),ref('Tab',theme,'Default',{Label:{text:'둘러보기'}}),...(adult?[ref('AdultFilter',theme,'Off',{}, {w:178})]:[])])
 ]);
 return row('Header',1216,80,12,[16,32],'paper',[txt('Page label','발견','Title','ink',150),ref('Search',theme,'Default',{}, {w:448}),...(adult?[ref('AdultFilter',theme,'Off')]:[]),ref('ThemeToggle',theme,'Default'),button(theme,adult?'로그아웃':'로그인',false,{w:116})]);
}
function filters(theme,mobile){return row('Genre filters',mobile?358:1152,44,8,0,null,(mobile?['전체','로맨스','판타지','미스터리']:['전체','로맨스','판타지','미스터리','SF','일상','힐링']).map((g,i)=>ref('Chip',theme,i===0?'Selected':'Default',{Label:{text:g}},mobile?{pad:[0,14]}:{})));}
function hero(theme,mobile){
 const copy=col('Feature story copy',mobile?172:720,null,mobile?10:16,0,null,[txt('Eyebrow','이번 주의 이야기','SmallStrong','heroMuted'),txt('Feature title','밤의 기록\n보관소',mobile?'H2':'Hero','onHero',mobile?172:650),...(!mobile?[txt('Feature description','당신이 잊은 기억을, 누군가는 기다리고 있다.','Body','heroMuted',650)]:[]),button(theme,'이야기 살펴보기',false,{w:mobile?172:190})]);
 const f=row('Featured story',mobile?358:1152,mobile?256:264,16,mobile?20:28,'hero',[copy,art('Featured art','archive',mobile?126:348,mobile?256:310,12)]);f.r=20;f.clip=true;return f;
}
function continueSection(theme,mobile){
 if(mobile)return col('Continue reading',358,null,12,16,'surface',[txt('Heading','지난 이야기를 이어볼까요?','Label'),row('Last conversation',326,56,12,0,null,[art('Avatar','bluehour',40,52,8),col('Copy',208,null,2,0,null,[txt('Title','푸른 시간의 역','Label'),txt('Preview','“정말 올 줄은 몰랐어.”','Small','muted')]),ic('arrow','accent')])]);
 const f=row('Continue reading',1152,112,20,24,'surface',[art('Avatar','bluehour',48,64,8),col('Copy',770,null,6,0,null,[txt('Heading','지난 이야기를 이어볼까요?','Title'),txt('Preview','푸른 시간의 역  ·  “정말 올 줄은 몰랐어.”','Body','muted')]),button(theme,'내 대화 열기',false)]);f.r=16;f.stroke='line';return f;
}
function bottom(theme){return row('Mobile bottom navigation',390,76,0,[0,16,16,16],'surface',[
 ref('BottomItem',theme,'Active'),ref('BottomItem',theme,'Default',{Label:{text:'둘러보기'},'Icon/compass':{icon:'search'}}),ref('BottomItem',theme,'Default',{Label:{text:'내 대화'},'Icon/compass':{icon:'chat'}}),ref('BottomItem',theme,'Default',{Label:{text:'스튜디오'},'Icon/compass':{icon:'pen'}})
]);}
function screen(theme,mobile=false,adult=true){
 const width=mobile?390:1440;
 const main=col('Main content',mobile?390:1216,null,mobile?24:28,mobile?[12,16,24,16]:[16,32,32,32],'paper',[
  filters(theme,mobile),hero(theme,mobile),
  col('Today discovery',mobile?358:1152,null,16,0,null,[heading('오늘의 발견',mobile?'어떤 이야기 속으로 들어가 볼까요?':'마음이 가는 캐릭터, 빠져들고 싶은 세계',mobile?358:1152,theme),
   ...(mobile?[row('Card row 1',358,null,12,0,null,works.slice(0,2).map(w=>card(theme,w,true))),row('Card row 2',358,null,12,0,null,works.slice(2,4).map(w=>card(theme,w,true)))]:[row('Story grid',1152,null,16,0,null,works.map(w=>card(theme,w)))])]),
  continueSection(theme,mobile),
  row('Footer',mobile?358:1152,40,12,0,null,[txt('Footer label',mobile?'모서리  ·  이야기가 시작되는 곳':'✳ 모서리     이야기가 시작되는 곳','Small','muted')])
 ]);
 const f=mobile?col('Mobile '+theme,390,null,0,0,'paper',[header(theme,true,adult),main,bottom(theme)]):row('Desktop '+theme,1440,null,0,0,'paper',[sidebar(theme),col('Page',1216,null,0,0,'paper',[header(theme,false,adult),main])]);
 f.align='start';f.theme=theme;f.mobile=mobile;f.adult=adult;return f;
}
function stateBoard(theme){return col('States '+theme,1152,null,24,32,'paper',[
 txt('Title','상태와 접근 조건','H1'),txt('Intro','기본 콘텐츠 탐색을 유지하면서, 상황에 맞는 피드백을 제공합니다.','Body','muted'),
 row('Loading cards',1088,null,16,0,null,[card(theme,works[0],false,'Loading'),card(theme,works[1],false,'Loading'),card(theme,works[2],false,'ImageMissing')]),
 row('Feedback',1088,null,24,0,null,[
 col('Empty',532,212,12,24,'surface',[ic('search','muted',28),txt('Title','아직 찾는 이야기가 없어요','Title'),txt('Message','다른 키워드나 장르로 다시 찾아보세요.','Body','muted'),button(theme,'필터 초기화',false)]),
 col('Error',532,212,12,24,'errorBg',[ic('alert','error',28),txt('Title','작품을 불러오지 못했어요','Title'),txt('Message','잠시 후 다시 시도해 주세요.','Body','muted'),button(theme,'다시 시도',false)])
 ]),
 txt('Adult states','성인 콘텐츠 포함 · 검증된 성인에게만 표시','Title'),
 row('Adult filters',1088,60,24,0,null,[ref('AdultFilter',theme,'Off'),ref('AdultFilter',theme,'On'),ref('AdultFilter',theme,'Pending')]),
 txt('Policy','OFF: 일반 콘텐츠만 / ON: 성인 콘텐츠 포함 / 갱신 중: 조작 비활성\n미성년·로그아웃·연령 미확인: 필터 자체와 여백을 제거. 권한 확인 전에도 노출하지 않음.\n서버가 허용한 목록만 표시. 필터 전환 실패 시 마지막 확인 상태로 복귀.','Body','muted',1088),
 txt('Minor title','미성년 사용자 · 상단 필터 없음','Title'),header(theme,true,false),
 txt('No account','로그아웃 / 대화 없음','Title'),col('No conversations',1088,160,12,24,'surface',[txt('Title','아직 시작한 이야기가 없어요','Title'),txt('Message','마음에 드는 작품에서 첫 장면을 열어보세요.','Body','muted'),button(theme,'작품 둘러보기')])
]);}
function componentBoard(theme){const families=['Button','Chip','Tab','MenuItem','Search','AdultFilter','ThemeToggle','StoryCard','BottomItem'];return col('Components '+theme,1456,null,28,32,'paper',[
 txt('Title','모서리 · 공통 컴포넌트','H1'),txt('Subtitle','Noto Sans KR · 4px 기반 간격 · 키보드 포커스 · Light / Dark','Body','muted'),
 ...families.map(f=>col(f,1392,null,12,0,null,[txt('Label',f,'Title'),...chunk(defs.filter(d=>d.family===f&&d.theme===theme),f==='StoryCard'?4:f==='Search'?3:5).map(ds=>row('Variants',1392,null,16,0,null,ds.map(d=>col(d.variant,null,null,8,0,null,[txt('State',d.variant,'Micro','muted'),ref(d.family,theme,d.variant)]))))]))
]);}
function chunk(a,k){const o=[];for(let i=0;i<a.length;i+=k)o.push(a.slice(i,i+k));return o;}
const notes=[
 ['01 · 범위와 화면 흐름','이번 시안: 발견 메인 PC 1440px / 모바일 390px × Light·Dark. 공통 메뉴·검색·필터·카드·버튼과 주요 상태.\n후속 확장: /explore 검색·장르, /works/[id] 작품 상세·시작 장면, /chats 내 대화, /chats/[id] 대화, 로그인·가입·이메일 인증·비밀번호 재설정.\n스튜디오는 이동 진입점만 유지. 기존 흐름: 발견 → 둘러보기 → 작품 상세 → 시작 장면 선택 → 대화.'],
 ['02 · 참고와 개성','2026-10-12 crack.wrtn.ai 실제 브라우저 화면을 확인. 좌측 탐색, 상단 검색, 가로 장르 칩, 추천 배너, 이미지 카드의 정보 위계를 참고.\n모서리의 코랄 색과 따뜻한 중성 배경, 기존 샘플 이야기 제목을 유지. 큰 소개 문구를 줄여 작품을 빨리 찾게 함. 표지 4장은 이번 시안용 생성 이미지.'],
 ['03 · 반응형 규칙','≥1280: 좌측 224px, 본문 좌우 32px, 4열 카드, gap 16px. 본문 최대 1280px로 확장.\n768–1279: 사이드바 64px로 축소, 카드 3열(1024 이상) 또는 2열, 검색과 필터는 별도 행.\n<768: 좌우 16px, 카드 2열, gap 12px, 검색 별도 행, 하단 탐색 4항목. 최소 360px 지원.\n모바일 장르 칩은 가로 스크롤. 하단 탐색은 viewport에 고정하고 safe-area와 가림 방지 여백 확보.\n표지 비율 3:4, object-fit cover. 제목 2줄, 소개 2줄 말줄임. 카드 전체가 상세 링크이며 상세에서 전문 제공.'],
 ['04 · 테마와 상호작용','시스템 설정을 초기값으로 사용하고 사용자의 Light/Dark 선택을 저장. 본문·배경·경계·포커스에 의미 토큰 사용.\n버튼 기본/hover/focus/disabled, 칩·메뉴 선택 상태, 검색 focus/filled/disabled, 카드 hover/focus/loading/image-missing을 제공.\n선택은 색과 배경으로, 포커스는 2px 외곽선으로 구분. 주요 조작 영역 최소 44px.'],
 ['05 · 성인 필터 계약 제안','상단 라벨: 성인 콘텐츠 포함. OFF=일반 콘텐츠만, ON=성인 콘텐츠도 포함. 성인 확인 사용자에게만 표시하며 초기 OFF.\n미성년·로그아웃·연령 미확인·권한 로딩: 필터를 렌더링하지 않고 공간도 회수. 미성년에게 성인 인증 유도 문구를 노출하지 않음.\n서버 응답의 권한 정보가 판단 기준. 클라이언트 나이 계산이나 로컬 설정만으로 허용하지 않음.\n필터 전환 시 권한에 맞는 새 목록을 요청. 권한 변경/로그아웃 시 이전 콘텐츠 캐시를 비우며, 실패 시 마지막 확인된 필터 상태로 복귀.\n서버가 검색·목록·추천·상세·이미지 접근을 일관되게 제한해야 함. 이번 산출물은 디자인 명세이며 서버 구현은 별도.'],
 ['06 · 현재 API와 연결 시 확인','현재 AuthUser는 id/email/email_verified만 제공. 성인 권한 필드는 아직 없음.\nCatalogItem은 id/title/description/snapshot_id/created_at. 표지, 장르, 작가명, 추천정보는 추가 계약 필요.\n시안의 추천·장르·이미지·최근 대화는 실제 기존 샘플 또는 시연 데이터. 운영 통계·랭킹을 임의로 만들지 않음.\n카드에 없는 필드는 숨기며 표지 없음은 대체 표지 사용. API 이름은 구현 단계에 합의.\n프로토타입 이동은 시각 검토용. 검색·성인 필터·로그인·대화는 실제 서비스에 연결되지 않음.']
];
function notesBoard(){return col('Handoff notes',1152,null,28,40,'paper',[txt('Title','모서리 · 구현을 위한 디자인 메모','H1'),...notes.map(([h,p])=>col(h,1072,null,12,0,null,[txt('Heading',h,'Title'),txt('Body',p,'Body','muted',1072)]))]);}
root.MOSEORI={colors,typography,works,icons,defs,row,col,txt,ic,art,ref,screen,stateBoard,componentBoard,notesBoard};
})(typeof globalThis!=='undefined'?globalThis:this);

/* Native Figma Plugin API. No API key, external network, or application-code changes. */
figma.showUI(__html__,{width:420,height:320});
figma.ui.onmessage=async msg=>{
 if(msg.type!=='build')return;
 try{
  const M=MOSEORI,runName='모서리 · 발견 v1 · 2026-10-12';
  const prior=figma.root.children.find(p=>p.name===runName);
  if(prior){await figma.setCurrentPageAsync(prior);figma.viewport.scrollAndZoomIntoView(prior.children);figma.ui.postMessage({type:'done',message:'이미 생성된 페이지를 열었습니다. 중복 생성하지 않았습니다.'});return;}
  const available=await figma.listAvailableFontsAsync();
  for(const style of ['Regular','Medium','Bold']){if(!available.some(f=>f.fontName.family==='Noto Sans KR'&&f.fontName.style===style))throw Error('Noto Sans KR '+style+' 글꼴이 필요합니다.');await figma.loadFontAsync({family:'Noto Sans KR',style});}
  const page=figma.createPage();page.name=runName+' · 생성 중';await figma.setCurrentPageAsync(page);
  const created=[],styles={},vars={},components={},sets={},artHashes={},iconComponents={};
  const status=s=>figma.ui.postMessage({type:'progress',message:s});status('이미지와 테마 토큰 준비 중…');
  for(const [key,data] of Object.entries(msg.assets))artHashes[key]=figma.createImage(new Uint8Array(data)).hash;
  const primitives=figma.variables.createVariableCollection('모서리 v1 / Primitives');primitives.renameMode(primitives.defaultModeId,'Base');
  const themeCollection=figma.variables.createVariableCollection('모서리 v1 / Theme');themeCollection.renameMode(themeCollection.defaultModeId,'Light');
  let darkMode=null;try{darkMode=themeCollection.addMode('Dark');}catch(_){themeCollection.renameMode(themeCollection.defaultModeId,'Theme tokens');}
  const layout=figma.variables.createVariableCollection('모서리 v1 / Layout');layout.renameMode(layout.defaultModeId,'Base');
  const rgb=h=>({r:parseInt(h.slice(1,3),16)/255,g:parseInt(h.slice(3,5),16)/255,b:parseInt(h.slice(5,7),16)/255});
  // Adapted from figma-generate-library/scripts/createSemanticTokens.js.
  function variable(name,coll,type,values,scopes,css){const v=figma.variables.createVariable(name,coll,type);for(const [mode,val]of Object.entries(values))v.setValueForMode(mode,val);v.scopes=scopes;v.setVariableCodeSyntax('WEB','var(--'+css+')');return v;}
  const primitiveVars={};for(const theme of ['Light','Dark'])for(const [key,hex]of Object.entries(M.colors[theme])){primitiveVars[theme+'/'+key]=variable(theme+'/'+key,primitives,'COLOR',{[primitives.defaultModeId]:{...rgb(hex),a:1}},[],'primitive-'+theme.toLowerCase()+'-'+key);}
  for(const key of Object.keys(M.colors.Light)){
   const scopes=key==='line'?['STROKE_COLOR']:['FRAME_FILL','SHAPE_FILL','TEXT_FILL','STROKE_COLOR'];
   if(darkMode){const v=variable(key,themeCollection,'COLOR',{[themeCollection.defaultModeId]:{type:'VARIABLE_ALIAS',id:primitiveVars['Light/'+key].id},[darkMode]:{type:'VARIABLE_ALIAS',id:primitiveVars['Dark/'+key].id}},scopes,key);vars['Light/'+key]=v;vars['Dark/'+key]=v;}
   else for(const theme of ['Light','Dark'])vars[theme+'/'+key]=variable(theme+'/'+key,themeCollection,'COLOR',{[themeCollection.defaultModeId]:{type:'VARIABLE_ALIAS',id:primitiveVars[theme+'/'+key].id}},scopes,key);
  }
  for(const value of [0,2,3,4,6,8,10,12,14,16,20,24,28,32,40,44,48,64])vars['space/'+value]=variable('space/'+value,layout,'FLOAT',{[layout.defaultModeId]:value},['GAP'],'space-'+value);
  for(const value of [8,12,16,20,24,999])vars['radius/'+value]=variable('radius/'+value,layout,'FLOAT',{[layout.defaultModeId]:value},['CORNER_RADIUS'],'radius-'+value);
  for(const [name,[size,line,weight]]of Object.entries(M.typography)){const s=figma.createTextStyle();s.name='모서리 v1/'+name;s.fontName={family:'Noto Sans KR',style:weight};s.fontSize=size;s.lineHeight={unit:'PIXELS',value:line};styles[name]=s;}
  function track(node){created.push(node.id);return node;}
  function paint(key,theme){return figma.variables.setBoundVariableForPaint({type:'SOLID',color:rgb(M.colors[theme][key])},'color',vars[theme+'/'+key]);}
  function color(node,key,theme,field='fills'){node[field]=[paint(key,theme)];}
  function numeric(node,field,val,prefix){node[field]=val;const v=vars[prefix+'/'+val];if(v)node.setBoundVariable(field,v);}
  function radius(node,r){if(!r)return;node.cornerRadius=r;for(const prop of ['topLeftRadius','topRightRadius','bottomLeftRadius','bottomRightRadius'])if(vars['radius/'+r])node.setBoundVariable(prop,vars['radius/'+r]);}
  function paddings(p){if(!Array.isArray(p))return[p||0,p||0,p||0,p||0];return p.length===2?[p[0],p[1],p[0],p[1]]:p;}
  function key(f,t,v){return f+'|'+t+'|'+v;}
  function iconSvg(o,theme){return '<svg xmlns="http://www.w3.org/2000/svg" width="'+o.w+'" height="'+o.h+'" viewBox="0 0 24 24" fill="none" stroke="'+M.colors[theme][o.color]+'" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+M.icons[o.icon]+'</svg>';}
  function overrideNode(node,patch,theme){if(patch.text!==undefined&&node.type==='TEXT')node.characters=patch.text;if(patch.asset&&'fills'in node&&Array.isArray(node.fills)&&node.fills.some(p=>p.type==='IMAGE'))node.fills=[{type:'IMAGE',imageHash:artHashes[patch.asset],scaleMode:'FILL'}];if(patch.icon&&node.type==='INSTANCE'){const w=node.width,h=node.height;node.swapComponent(iconComponents[theme+'/'+patch.icon]);node.resize(w,h);}}
  for(const theme of ['Light','Dark'])for(const [index,icon]of Object.keys(M.icons).entries()){const c=track(figma.createComponent());c.name='Icon/'+theme+'/'+icon;c.resize(24,24);c.fills=[];const svg=figma.createNodeFromSvg(iconSvg({icon,w:24,h:24,color:'muted'},theme));for(const child of [...svg.children])c.appendChild(child);svg.remove();c.x=5000+index*48;c.y=theme==='Light'?-200:-120;iconComponents[theme+'/'+icon]=c;}
  async function build(o,parent,theme,isComponent=false){
   let node;
   if(o.type==='instance'){
    const master=components[key(o.family,o.theme,o.variant)];if(!master)throw Error('컴포넌트 누락: '+key(o.family,o.theme,o.variant));node=track(master.createInstance());parent.appendChild(node);node.name=o.family+'/'+o.variant;
    for(const target of [node,...node.findAll(()=>true)])if(o.overrides[target.name])overrideNode(target,o.overrides[target.name],theme);
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
  for(const family of families){const variants=[];for(const d of M.defs.filter(d=>d.family===family)){const comp=await build(d.tree,page,d.theme,true);comp.name='Theme='+d.theme+', Variant='+d.variant;comp.description='모서리 '+family+' · '+d.variant;for(const text of comp.findAllWithCriteria({types:['TEXT']})){if(['Label','Value','Title','Description','Genre','Author'].includes(text.name)){const property=comp.addComponentProperty(text.name,'TEXT',text.characters);text.componentPropertyReferences={characters:property};}}
   components[key(family,d.theme,d.variant)]=comp;variants.push(comp);}
   const set=track(figma.combineAsVariants(variants,page));set.name='모서리/'+family;set.description='Light/Dark 테마와 상태 변형. 모든 화면은 이 컴포넌트의 인스턴스를 사용합니다.';const maxW=Math.max(...variants.map(n=>n.width)),maxH=Math.max(...variants.map(n=>n.height));variants.forEach((c,i)=>{c.x=32+(i%5)*(maxW+32);c.y=32+Math.floor(i/5)*(maxH+32);});set.resize(64+5*(maxW+32),64+Math.ceil(variants.length/5)*(maxH+32));set.x=5000;set.y=libraryY;libraryY+=set.height+120;sets[family]=set.id;}
  status('PC·모바일 메인과 상태 보드 생성 중…');const screens={};
  for(const [theme,mobile,x,y]of [['Light',false,200,200],['Dark',false,1800,200],['Light',true,3400,200],['Dark',true,3900,200]]){const f=await build(M.screen(theme,mobile,true),page,theme);f.x=x;f.y=y;screens[(mobile?'Mobile':'Desktop')+' '+theme]=f;}
  for(const [theme,x]of [['Light',200],['Dark',1800]]){const state=await build(M.stateBoard(theme),page,theme);state.x=x;state.y=2000;const board=await build(M.componentBoard(theme),page,theme);board.x=x;board.y=3800;}
  const notes=await build(M.notesBoard(),page,'Light');notes.x=3400;notes.y=2200;
  for(const [name,f]of Object.entries(screens)){const target=screens[name.replace(/Light|Dark/,name.includes('Light')?'Dark':'Light')];for(const toggle of f.findAll(n=>n.type==='INSTANCE'&&n.name.startsWith('ThemeToggle/')))await toggle.setReactionsAsync([{trigger:{type:'ON_CLICK'},actions:[{type:'NODE',destinationId:target.id,navigation:'NAVIGATE',transition:null,preserveScrollPosition:true}]}]);}
  const all=[...created,...page.findAll(()=>true).map(n=>n.id)];const texts=page.findAllWithCriteria({types:['TEXT']});const zero=texts.filter(t=>t.width<=0||t.height<=0).map(n=>n.id);
  page.name=runName;figma.currentPage.selection=[screens['Desktop Light']];figma.viewport.scrollAndZoomIntoView([screens['Desktop Light'],screens['Mobile Light']]);
  const report={pageId:page.id,screens:Object.fromEntries(Object.entries(screens).map(([k,n])=>[k,{id:n.id,width:n.width,height:n.height}])),sets,variantCount:M.defs.length,textCount:texts.length,zeroSizeText:zero,themeMode:darkMode?'Native Light/Dark modes':'Single-mode plan: separate Light/Dark tokens and component variants',createdNodeIds:[...new Set(all)]};figma.ui.postMessage({type:'done',message:'메인 4개, 상태 2개, 컴포넌트 보드 2개와 구현 메모를 생성했습니다.',report});
 }catch(error){figma.ui.postMessage({type:'error',message:String(error&&error.message||error)});}
};
