"""Build editable Korean report and complete evidence/diagram inputs from inventory."""
import ast,csv,hashlib,json,re,xml.etree.ElementTree as ET
from collections import Counter,defaultdict
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
D=json.loads((OUT/'inventory.json').read_text(encoding='utf8'))
FILES={f['path']:f for f in D['files']};TABLES={t['name']:t for t in D['tables']}
M='apps/api/app/modules/';APP='apps/api/app/'
evidence=[];parts=[];diagrams=[]
def p(s=''):parts.append(s.strip()+'\n')
def ref(path,symbol=None):
    if not path.startswith(('apps/','infra/','references_')):path=APP+path
    f=FILES.get(path,{})
    line=next((x['line'] for x in f.get('symbols',[]) if x['name']==symbol),1)
    if symbol and line==1:
        lines=(ROOT/path).read_text(encoding='utf-8-sig').splitlines()
        line=next((i+1 for i,s in enumerate(lines) if symbol in s),1)
    record=dict(path=path,line=line,symbol=symbol or 'file',sha256=f.get('sha256'))
    if record not in evidence:evidence.append(record)
    return f"{path}:{line}"+(f" ({symbol})" if symbol else '')
def table(headers,rows):
    p('| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(str(c).replace('|',' / ').replace('\n',' ') for c in row)+' |' for row in rows))
def diagram(id,title,kind,**kwargs):
    diagrams.append(dict(id=id,title=title,kind=kind,**kwargs));p(f'![{title}](diagrams/{id}.svg)')
def module(path):
    tail=path.split('/modules/')[-1].split('/')
    return '/'.join(tail[:2]) if tail[0] in {'content','chatting','commerce','governance','reporting'} else tail[0]
mods=sorted({module(f) for f in FILES if f.startswith(M) and not f.endswith('/__init__.py')})
mods=[m for m in mods if '/' in m or m in ['identity','llm','asset_storage']]
edges=defaultdict(list)
for f in D['files']:
    if not f['path'].startswith(M):continue
    own=module(f['path'])
    for imp in f.get('imports',[]):
        if imp['module'].startswith('app.modules.'):
            other=module(imp['module'].replace('.','/')+'/dummy')
            if own!=other and other in mods:edges[(own,other)].append(f"{f['path']}:{imp['line']}")
reach={m:{b for a,b in edges if a==m} for m in mods}
for k in mods:
    for a in mods:
        if k in reach[a]:reach[a]|=reach[k]
cycles=[];seen=set()
for a in mods:
    group=sorted({a}|{b for b in mods if b in reach[a] and a in reach[b]})
    if len(group)>1 and tuple(group) not in seen:cycles.append(group);seen.add(tuple(group))
def owner(t):
    if t in {'users','user_oauth_accounts','auth_sessions','auth_action_tokens','auth_oauth_attempts','auth_rate_limits'}:return 'identity'
    if t.startswith('credit_'):return 'commerce/credit'
    if t in {'payments','usage_logs','product_payment_events','billing_quotes','billing_credit_bindings','subscription_plans','user_subscriptions'}:return 'commerce/billing'
    if t in {'providers','models','model_replacements'}:return 'llm'
    if t.startswith('moderation_') or t=='audit_logs':return 'governance/moderation'
    if t in {'messages','chat_message_requests','product_generations','generation_prompts'}:return 'chatting/chat'
    if t in {'conversation_memories','memory_jobs'}:return 'chatting/memory'
    if t.startswith('conversation'):return 'chatting/conversation'
    if t.startswith('character'):return 'content/character'
    if t.startswith('lorebook'):return 'content/lorebook'
    if t=='tags':return 'content/tag'
    return 'content/product'
model_sources={}
for path in FILES:
    if not path.startswith(APP+'db/models/') or not path.endswith('.py'):continue
    tree=ast.parse((ROOT/path).read_text(encoding='utf8'))
    for n in tree.body:
        if isinstance(n,ast.ClassDef):
            for x in n.body:
                if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__tablename__' for t in x.targets):model_sources[ast.literal_eval(x.value)]=(path,n.name)
fkrows=[]
for t in D['tables']:
    for fk in t['fks']:
        cols=set(fk['columns']);unique=any(c['kind'] in {'PrimaryKeyConstraint','UniqueConstraint'} and set(c['columns'])<=cols and c['columns'] for c in t['constraints']) or any(i['unique'] and i['where']=='None' and {c.split('.')[-1] for c in i['columns']}<=cols for i in t['indexes'])
        optional=any(c['nullable'] for c in t['columns'] if c['name'] in cols)
        fkrows.append(dict(child=t['name'],parent=fk['target'],columns=','.join(fk['columns']),target=','.join(fk['target_columns']),child_per_parent='0..1' if unique else '0..N',parent_per_child='0..1' if optional else '1',delete=fk['ondelete'],update=fk['onupdate'],owner=owner(t['name'])))
with (OUT/'relationships.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(fkrows[0]));w.writeheader();w.writerows(fkrows)
with (OUT/'api-inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['method','path','function','source','dependencies'])
    for r in D['routes']:w.writerow([','.join(r['methods']),r['path'],r['function'],f"{r['file']}:{r['line']}",'; '.join(r['dependencies'])])

p('# 백엔드 아키텍처 및 코드 검토 보고서')
p('CHAT STARTER KIT · 현재 작업 트리 기준 · 2026-10-21 (Asia/Seoul)')
p('시스템 이해, 변경 영향 추적, 생성 코드의 검토 우선순위를 위한 기술 보고서')
p(f"브랜치: {D['branch']}\n\n기준 커밋: {D['commit']}\n\n미커밋 변경: 있음. 커밋 이후의 staged·unstaged 파일을 포함한 작업 트리를 조사했다. 파일별 SHA-256은 inventory.json에 보존했다. 운영 DB나 실제 사용자 데이터는 열람하지 않았다.")
p('이 문서는 현재 구현의 지도와 검토 기록이다. 코드 수정, 스키마 변경, 운영 시스템 검증 완료를 의미하지 않는다. 기존 문서의 과거 테스트 결과는 이번 실행 결과로 대체하여 읽어야 한다.')
p('[TOC]')
p('# 1. 요약')
p('이 백엔드는 캐릭터와 로어북으로 작품을 구성·발행하고, 발행 스냅샷(발행 시 고정한 데이터 복사본)을 사용하는 대화에서 LLM(대규모 언어 모델) 답변을 생성하는 모듈형 단일 애플리케이션이다. 인증, 미디어, 모델 실행, 크레딧, 통계, 검수 업무가 Python 모듈로 분리되어 있으며 DB(데이터베이스)는 공유한다. 모듈 경계가 독립 프로세스나 독립 DB를 뜻하지 않는다.')
p('용어: ORM은 객체와 DB 테이블을 연결하는 매핑, PK는 행을 식별하는 기본키, FK는 다른 행을 참조하는 외래키다. API는 프로그램 간 공개 호출 계약이고 HTTP는 요청·응답 통신 규약이다. DTO는 요청·응답 전달 객체, 트랜잭션은 함께 확정하거나 취소하는 DB 작업 단위, commit은 확정, rollback은 취소다. lease는 일정 시간만 유효한 작업 소유권이며 멱등성은 같은 요청을 반복해도 업무 효과가 중복되지 않는 성질이다. 뒤의 ERD는 테이블 관계도, 의존성 주입은 필요한 객체를 외부 조립 지점에서 제공하는 방식이다.')
table(['규모 / 검증','현재 작업 트리의 결과'],[['애플리케이션',f"363 Python 파일 / {len(mods)} 업무 모듈"],['데이터',f"73 ORM 테이블 / 600 컬럼 / {len(fkrows)} FK 제약"],['HTTP','114 메서드·경로 조합 / 84 경로'],['기존 테스트','529 passed / 4 failed / 290 skipped (총 823)'],['아키텍처 계약','기존 계약 검사 10개 통과'],['정적 검사','Ruff 61건 / Alembic 단일 head 0030'],['추가 확인','null 제목 응답 불일치·미연결 권한 가드·검수자/소유자 인자 혼용을 합성 입력으로 확인']])
p('강점은 저장소 접근과 순수 변환을 분리하고, 공개 service/types 경계를 검사하는 테스트를 보유했다는 점이다. 답변은 생성·견적·크레딧 예약·최종 프롬프트를 함께 저장하고 외부 LLM을 호출한다. 결과가 불확실하면 무조건 재호출하지 않고 저장된 상태와 lease로 복구한다. 이 설계를 문서에 명시적으로 남기는 것이 유지보수에 중요하다.')
p('우선 해결할 항목은 시작 옵션의 nullable 제목 계약(F01), 운영에 노출할 관리자/검수 경로의 인증 연결(F02), 검수자 ID를 소유자 조건으로 사용하는 호출(F03), 현재 변경과 어긋난 회귀 테스트(F05)다. 두 번째 기본 이미지 입력의 DB 제약 오류 노출(F04)도 정상 업무 오류로 정리할 필요가 있다. 치명적 운영 사고나 실제 데이터 유출을 재현한 것은 아니다.')
p('읽는 순서: 3장의 전체 구조 → 6장의 답변·발행 흐름 → 7장의 데이터 경계 → 11장의 발견 사항. 특정 기능을 수정할 때에는 4장의 모듈별 읽기 순서와 부록의 API·테이블 사전을 함께 확인한다.')

p('# 2. 검토 범위와 방법')
p('AGENTS.md, 모듈 아키텍처 및 명명 규칙, 업무 모듈 18개와 db/use_cases의 ARCHITECTURE.md를 읽고 코드와 대조했다. apps/api/app 전체 Python을 AST로 분석하여 import·심볼·줄 수를 수집했고 ORM 메타데이터와 앱 라우트 조립을 연결했다. 각 모듈의 대표 구현과 위험한 교차 경계를 직접 확인했다. 모든 함수의 모든 분기를 수작업으로 검증한 전수 감사라고 주장하지 않는다.')
p('검토 깊이는 다음과 같다. 목록 확인은 AST/파일/메타데이터의 전수 수집이다. 구현 확인은 보고서에 인용한 심볼 및 호출 경로를 직접 대조한 상태다. 실행 검증은 이번 로컬 테스트 또는 합성 재현에 한하며 실제 PostgreSQL·공급자 통신 성공으로 확장하지 않는다. coverage.csv와 evidence.json은 이 차이를 기록한다.')
table(['범위','방법 / 한계'],[['app 363 Python','전수 AST·import·등록 정보 확인; 중요 흐름 선별 심층 검토'],['tests / alembic / 초기 SQL','파일 목록 및 기존 전체 테스트; 최신 DDL 대조; DB 실행 없음'],['프런트엔드','백엔드 호출 주체 설명에만 사용. UI·브라우저·접근성 검토 제외'],['배포 / 운영','Dockerfile·작업 진입점 정적 확인. 실제 배포·DB 현황·부하·백업 복구 제외'],['외부 공급자','OpenAI/Anthropic/Voyage/S3/SMTP/Google 어댑터 구조와 대역 테스트. 실제 API 미호출'],['과거 검토 문서','탐색 보조로만 사용. 과거 지적을 현재 결함으로 자동 승계하지 않음']])
p('기술 스택: Python 3.12 로컬 런타임(프로젝트 최소 3.11), FastAPI, Pydantic, SQLAlchemy async, asyncpg, PostgreSQL/pgvector, Alembic. 외부 서비스는 OpenAI·Anthropic 텍스트 생성, Voyage 임베딩, S3 또는 로컬 저장, SMTP와 Google OIDC다. Redis가 개발 의존성에 있어도 현재 업무 코드의 큐는 PostgreSQL 테이블을 사용한다.')
p('근거: '+ref('apps/api/pyproject.toml')+'; '+ref('apps/api/requirements.txt')+'; '+ref('main.py','create_app')+'; '+ref('memory_worker.py','run_worker'))
p('안전한 실행을 위해 테스트 프로세스에서 DB URL 및 외부 서비스 opt-in 환경변수를 제거했다. .env, .env.local과 비밀키 파일은 읽지 않았다. 제한 환경에서는 FastAPI TestClient의 첫 요청이 멈췄고, 해당 실행을 중단한 뒤 같은 테스트를 일반 로컬 권한에서 재실행했다. 이후 전체 테스트는 13.82초에 종료했다. 앱 lifespan을 실제 서비스 설정으로 시작하지 않았다.')

p('# 3. 전체 아키텍처')
diagram('system','시스템 구성과 실행 호출','boxes',nodes=[['web','웹 / 로컬 클라이언트',0,0],['api','FastAPI · main',1,0],['domains','업무 모듈 / use_cases',1,1],['db','PostgreSQL + pgvector',1,2],['workers','memory / statistics / cleanup',0,2],['providers','LLM / embedding / S3 / SMTP / OIDC',2,1]],edges=[['web','api','HTTP'],['api','domains','실행'],['domains','db','SQL'],['workers','db','claim / 저장'],['workers','providers','외부 호출'],['domains','providers','어댑터']])
p('실선 화살표는 실행 호출 방향이다. main의 lifespan은 DB 엔진, 세션 팩토리, 인증, 저장소, LLM 어댑터, AnswerOrchestrator와 15초 답변 복구 루프를 조립한다. memory worker·통계 job·정리 CLI는 별도 프로세스로 실행해야 한다. provider 호출과 DB commit은 하나의 분산 트랜잭션으로 묶이지 않는다.')
diagram('layers','대표 모듈의 호출과 값 변환','boxes',nodes=[['http','router / HTTP DTO',0,0],['sm','mapper/schema',1,0],['svc','command / query / views',0,1],['wf','선택적 workflow',2,0],['repo','repository',0,2],['pm','mapper/persistence',1,2],['db','자기 소유 테이블',0,3],['values','types: Command / Info / View',2,2]],edges=[['http','sm','변환'],['http','svc','직접 호출'],['http','wf','다단계'],['wf','svc','조합'],['svc','repo','조회 / 쓰기'],['repo','db','SQL'],['svc','pm','Row 변환']])
p('이 그림은 규칙의 대표 형태다. mapper는 repository를 호출하지 않으며 service가 원시 결과를 mapper로 전달한다. types는 값 계약이다. 조회도 Command를 입력으로 받는다. asset_storage처럼 DB가 없는 모듈에는 repository가 없고, reporting은 다른 공개 서비스의 결과를 조합한다. 단순 기능마다 workflow를 추가하지 않는다.')
p('근거: '+ref('db/transaction.py','use_case_transaction')+'; '+ref(M+'content/character/service/command.py','create_character')+'; '+ref(M+'chatting/chat/service/workflow/answers.py','AnswerOrchestrator'))
p('정적 import 그래프의 간선은 호출 실행 횟수나 런타임 순서를 뜻하지 않는다. 공개 service/types만 쓰더라도 모듈 수준에서는 순환 의존이 남을 수 있다. 아래 표는 전체 모듈 간 import를 축약한 것이다. 개별 간선 근거는 module-dependencies.json에 있다.')
table(['가져오는 모듈','참조하는 다른 모듈'],[[m,', '.join(sorted({b for a,b in edges if a==m})) or '없음'] for m in mods])
diagram('backend-modules','백엔드 전체 모듈 의존 지도','module',nodes=mods,counts={m:sum(1 for path in FILES if path.startswith(M+m+'/') and path.endswith('.py')) for m in mods},edges=[list(e) for e in edges])
p('상호 도달 가능한 모듈군: '+('; '.join(' ↔ '.join(g) for g in cycles) or '없음')+'. 이는 정적 의존 그래프의 순환이다. 현재 import 실패나 런타임 무한 호출을 의미하지 않는다. product의 공개 View, conversation의 런타임 구성, llm의 대체 정책이 서로의 타입·공개 서비스를 참조하는 구조는 향후 변경 영향 검토 지점이다.')

DESCRIPTIONS={
'identity':('인증·세션·증명·요청 제한','router.py → service/authentication.py → repository.py → security.py; 외부 통신은 service/workflow/mail.py·google.py','AuthenticationService; AuthenticationMailWorkflow; GoogleLoginService; require_active_user / require_admin','JWT 서명만 확인하지 않고 현재 사용자·세션 상태를 조회한다. refresh 재사용 폐기는 commit 이후 오류를 낸다. SMTP 전송은 증명 commit 이후다.','service/authentication.py','refresh_session'),
'asset_storage':('공급자 중립 파일 저장·읽기·삭제','types.py → service/settings.py → service/factory.py → service/storage.py → adapters/','AssetStorageService.store_asset / read_asset / delete_asset / aclose','호출자가 도메인 권한과 reader 수명을 소유한다. S3 boto3는 thread로 실행한다. 로컬 두 파일(본문·메타데이터)의 다중 프로세스 원자성까지 보장하지 않는다.','service/storage.py','AssetStorageService'),
'llm':('텍스트 생성·임베딩·모델 카탈로그·대체 정책','service/text_generation.py·embedding.py → adapters/protocols.py → 개별 adapter; DB 모델 선택은 service/command/replacement.py','TextGenerationService.generate_text; EmbeddingService.embed_texts; resolve_execution','텍스트와 임베딩 등록소를 분리한다. request_json을 공급자별 메시지로 변환한다. DB 모델 활성 정책과 SDK의 지원 모델 판단은 별개다.','service/text_generation.py','TextGenerationService'),
'content/character':('캐릭터 원본·발행 스냅샷·미디어 참조','router.py → service/command.py·query.py → repository.py → mapper/; 업로드는 workflow/media.py','create_character / update_character / freeze_character; CharacterMediaWorkflow','업로드 예약→공급자 작업→ready, 정리는 deleting→삭제→deleted다. 스냅샷 FK가 남아 있으면 원본을 삭제해도 객체 정리는 막는다.','service/workflow/media.py','upload_character_media'),
'content/lorebook':('로어 항목·스냅샷·활성화 규칙','router.py → service/command.py·query.py → service/activation.py → repository.py','create_lorebook_entry / freeze_lorebook / activate_snapshot_entries','현재 activation.py는 v1 옵션의 깊이·화자·대소문자·배타 그룹·항목 예산·manual 선택을 지원한다. semantic은 미지원이다. 기존 문서의 manual/예산 미지원 설명과 구분해야 한다.','service/activation.py','diagnose_entries'),
'content/product':('작품 구성·발행·정책·일별 통계','router.py → command/composition.py·settings.py → releases.py·publication.py → views/ → repository/','create_product / publish_product / get_accessible_product / get_snapshot_runtime','원본과 발행본을 분리한다. product_generations와 product_payment_events는 이름과 달리 이 모듈 소유가 아니다. studio 후속 발행은 use_cases가 조합한다.','service/command/publication.py','_build_publication'),
'content/tag':('공통 태그 사전','service/command.py → service/query.py → repository.py → mapper/persistence.py','resolve_tags / create_tag / update_tag / deactivate_tag','이름의 앞뒤 공백만 정규화하며 대소문자·동의어를 통합하지 않는다. 콘텐츠별 연결 6개는 각 콘텐츠 모듈 소유다. 사전 비활성화는 기존 연결을 보존한다.','service/command.py','resolve_tags'),
'chatting/conversation':('대화방·참여자·현재/최초 버전','router.py → command/__init__.py·versions.py·context.py → views.py → repository.py','start_conversation / prepare_runtime_context / get_owned_conversation','현재 product_snapshot_id와 최초 initial_snapshot_id는 다르다. 신규 고정 첫 대사는 messages에 저장하지 않고 시작 문맥으로 제공한다. 버전 변경이 이미 생성 중인 결과를 stale로 만들 수 있다.','service/command/context.py','prepare_runtime_context'),
'chatting/chat':('메시지·생성 실행권·최종 프롬프트','router/messages.py·answers.py → command/messages.py·generation.py → workflow/answers.py → repository.py','create_user_message / begin_generation / finish_generation; AnswerOrchestrator','대화방 잠금·revision·request_key를 사용한다. 답변 요청키는 사용자 범위다. 결과·usage·기억 예약·크레딧 확정은 같은 최종 트랜잭션이다. stream.py는 빈 파일이며 답변 SSE 구현의 증거가 아니다.','service/workflow/answers.py','generate_answer'),
'chatting/memory':('요약·벡터 검색·durable 작업','command/scheduling.py·summarization.py·indexing.py → query/retrieval.py → repository.py','SummaryGenerator / MemoryIndexer / MemoryRetriever; claim_memory_work','메시지 원본은 chat이 제공한다. 1536차원 및 공급자·모델 일치로 벡터를 선택한다. 편집 시 history_revision을 올리고 요약을 무효화한다. lease 갱신 루프는 없다.','service/command/scheduling.py','claim_memory_work'),
'chatting/prompt':('최종 공급자 중립 프롬프트 구성','resources/default.json → service.py → types.py → llm/adapters/messages.py','load_template / build_prompt','DB 없음. 서버 규칙은 system, 사용자가 작성한 참조는 user 데이터다. 현재 로어 placement에 따라 이력 앞·현재 입력 근처에 나눈다. 바이트 기반 보수적 예산은 실제 공급자 usage와 다르다.','service.py','build_prompt'),
'commerce/billing':('가격·견적·사용량·매출 귀속','service/pricing.py → quotes.py → credits.py → repository.py; 사용량은 command/','calculate_billing_price / create_billing_quote / reserve_credit / record_usage','고정 견적 예약액을 성공 시 확정한다. credit으로 지갑 쓰기를 위임한다. 현금 PG 승인·구독 실행은 구현되지 않았다. 정책 슬롯의 무효과 구현을 실제 할인 기능으로 읽으면 안 된다.','service/credits.py','reserve_credit'),
'commerce/credit':('재화별 지갑·무료/유료 배분·원장','types.py → service/command.py·query.py → repository.py → mapper/persistence.py','prepare_credit_wallet / grant_credit / reserve_credit / commit_credit_reservation','명시적인 상위 transaction이 필요하다. 무료분을 우선 예약하고 최초 배분을 확정/해제에 재사용한다. legacy 미분류 데이터는 자동 활성화하지 않는다.','service/command.py','reserve_credit'),
'governance/admin':('관리자 HTTP 및 도메인 조율','product_router.py·model_router.py·tag_router.py → service/command.py → 대상 공개 service','상품 상태·만료, 모델 종료, 태그 관리 경로','자체 테이블이 없다. 태그·상품·모델 경로는 서비스에서 역할을 재확인한다. 기존 캐릭터·로어 전역 조회는 미연결 전용 guard에 의존한다.','character_router.py','router'),
'governance/moderation':('신고·평가·조치 요청·기존 검수 HTTP','service/command/reports.py → assessments.py → actions.py → repository/review.py','submit_report / record_manual_assessment / request_action / cancel_pending_action','신고 접수와 위반 확정, 조치 요청과 실제 제재 적용을 분리한다. 신규 내부 서비스 HTTP와 실제 적용자는 없다. applied 상태를 만드는 공개 실행 구현은 확인되지 않았다.','service/command/actions.py','request_action'),
'reporting/account_reporting':('본인 생성·기록 사용량 조합','service/views.py → chat·billing 공개 query → mapper/persistence.py','get_account_report','소유 테이블 없음. 생성 created_at과 usage created_at이 다른 코호트라 두 건수의 일치를 보장하지 않는다. 공급자 전체 비용이나 원장 잔액을 뜻하지 않는다.','service/views.py','get_account_report'),
'reporting/creator_reporting':('소유 작품의 집계 조회','service/views.py → product 공개 reporting → mapper/persistence.py','get_product_report','소유자 범위를 재검증한다. missing은 0이 아니며 dirty/누락이 있을 때 확정 totals를 제공하지 않는다. 작가에게 원문·개별 사용자·매출은 노출하지 않는다.','service/views.py','get_product_report'),
'reporting/operations_reporting':('관리자 집계·최종 프롬프트 조회','router.py → service/prompts.py·views.py → chat·product 공개 query','get_recorded_service_report / get_statistics_queue_report / get_generation_prompt','일반 집계는 내부 서비스다. 프롬프트 목록/상세만 HTTP에 노출한다. 목록은 원문 제외, 상세는 활성 admin 재검증 및 no-store다. 저장은 실제 전송 성공의 증거가 아니다.','service/prompts.py','get_generation_prompt'),
}
p('# 4. 모듈별 상세 소개')
p('각 절의 diagram은 실제 파일에서 추출한 같은 모듈 내부 import를 계층별로 축약한다. 화살표는 “참조한다”이며 반환 데이터 흐름이 아니다. 공개 인터페이스는 주요 진입점 위주이고 전체 심볼은 inventory.json에 있다.')
for m in mods:
    title,order,public,notes,source,sym=DESCRIPTIONS[m]
    fs=[f for f in D['files'] if f['path'].startswith(M+m+'/') and f['path'].endswith('.py')]
    owned=[t for t in TABLES if owner(t)==m]
    p('## '+m+' · '+title)
    p('책임과 계약: '+notes)
    p('읽는 순서: '+order+'\n\n주요 공개 진입점: '+public)
    p('소유 테이블: '+(', '.join(owned) if owned else '없음')+'.')
    p('참조 모듈: '+(', '.join(sorted({b for a,b in edges if a==m})) or '없음')+f". Python 파일 {len(fs)}개, {sum(f['lines'] for f in fs):,}줄(주석·공백 포함).")
    def layer(path):
        tail=path[len(M+m+'/'):].split('/')[0]
        if 'router' in tail:return 'router'
        if tail.startswith('service'):return 'service'
        return tail.split('.')[0]
    counts=Counter(layer(f['path']) for f in fs if f['lines']>0)
    allowed={'router','service','repository','mapper','types','schemas','adapters','security','settings','http_security','dependencies'}
    nodes=[x for x in counts if x in allowed]
    ledges=set()
    for f in fs:
        src=layer(f['path'])
        for imp in f.get('imports',[]):
            base=imp['module']
            for name in imp['names']:
                full=(base+'.'+name).replace('.','/')
                pref='app/modules/'+m+'/'
                if full.startswith(pref):
                    target=full[len(pref):].split('/')[0]
                    if 'router' in target:target='router'
                    if src in nodes and target in nodes and src!=target:ledges.add((src,target))
    diagram('module-'+m.replace('/','-'),m+' 내부 구조','module',nodes=nodes,counts=dict(counts),edges=sorted(ledges))
    p('코드 근거: '+ref(M+m+'/'+source,sym)+'. 모듈 의도: '+ref(M+m+'/ARCHITECTURE.md'))
    keyfiles=[f for f in fs if ('/service/' in f['path'] or f['path'].endswith('/service.py')) and f.get('symbols')]
    table(['서비스 파일','주요 함수 / 책임 탐색'],[[f['path'][len(M+m+'/'):],', '.join(s['name'] for s in f['symbols'] if not s['name'].startswith('_'))[:420] or '내부 보조 / 재노출'] for f in keyfiles])
p('## 모듈 밖의 조립 계층')
p('http는 전체 라우트와 공유 HTTP 계약·의존성을 소유한다. use_cases는 product_statistics, conversation_directory, account_overview와 studio_content/components/diagnostics/publication을 조합한다. studio_publication은 현재 후속 발행 receipt를 revision별로 보존하며, 원본 컴포넌트 ID를 재사용하고 이전 스냅샷을 수정하지 않는다. use_cases/ARCHITECTURE.md의 세 파일만 존재한다는 설명은 최신 구현을 포괄하지 못한다.')
p('근거: '+ref('http/routes.py')+'; '+ref('use_cases/studio_publication.py','publish_studio')+'; '+ref('use_cases/studio_components.py','component_mapping')+'; '+ref('use_cases/product_statistics.py','rebuild_day'))

p('# 5. 전반적인 코드 패턴')
table(['패턴','현재 구현 / 평가'],[['입력','Pydantic RequestDto → Command. product/chat은 extra=forbid, 일부 character DTO는 기본 extra 무시. 사용자 owner_id를 신뢰하지 않고 dependency의 ID를 mapper가 주입.'],['업무 판단','service는 mapper가 만든 Info로 존재·소유권·상태를 판단. repository는 SQL/flush. router가 SQL을 실행하지 않는지 기존 AST 테스트로 검사.'],['응답','Info/View → ResponseDto. product는 from_attributes model_validate. 이 경계의 nullable 불일치는 성공 조회 뒤 응답 오류가 될 수 있음(F01).'],['트랜잭션','일반 command는 use_case_transaction. 중첩 실패는 rollback-only. credit/billing 예약은 명시 상위 transaction+SAVEPOINT.'],['의존성 주입','main이 sessions·storage·LLM·인증 객체를 구성하고 FastAPI hook을 override. 모듈 단독 router 기본값은 503.'],['예외','identity는 error.code, 일반 content는 detail, chat은 도메인별 HTTP 변환. 의도된 계약 차이이며 일괄 변경 시 클라이언트 호환성 주의.'],['비동기','SQLAlchemy async·공급자 async; boto3는 to_thread. 미디어 취소는 실제 저장 작업 종료를 기다린 뒤 DB lock 해제.'],['설정','auth/storage는 시작 시 검증. 가격표 미설정은 기존 조회·복구를 허용하되 신규 답변을 거절.'],['관측','structlog의 정규화 error_kind 및 식별자. 기본 API 엔진 hide_parameters=True. auth 접근 로그는 query string 제거.']])
p('실제 예: character.create_character는 use_case_transaction 안에서 프로필을 검증하고 repository 결과를 persistence mapper에 전달한다. 태그가 있으면 같은 transaction에서 태그 공개 서비스로 연결한다. 이 구조를 새 코드의 기준 예제로 삼을 수 있다.')
p('근거: '+ref(M+'content/character/service/command.py','create_character')+'; '+ref(M+'content/product/mapper/schema.py','published_view_to_response')+'; '+ref('http/dependencies.py','errors')+'; '+ref(M+'identity/http_security.py','AuthRoute'))
p('현재 구현의 예외: use_cases/account_overview는 dict[str,int]를 반환하고 http/account_credits가 즉석 DTO를 정의한다. 외부 서비스·폴더 구조만을 이유로 전면 리팩터링할 필요는 없지만 공개 응답 계약의 명시성과 테스트 범위를 맞추는 편이 좋다. 기본 패턴 차이가 곧 버그는 아니다.')
p('유지보수 제안: 구조 규칙을 기계적으로 적용하기 전에 유스케이스 경계, 호출자의 신뢰 수준, 예외를 누가 HTTP로 바꾸는지부터 확인한다. Ruff의 광범위 예외 지적도 답변의 모호한 commit 복구 의도와 함께 판단해야 한다.')

p('## 짧은 실제 코드 발췌')
p('다음은 실제 파일에서 가져온 한 줄씩의 발췌다. 독립 실행 예제가 아니며 주변 검증·예외·트랜잭션 코드는 생략했다. 구현을 수정할 때에는 표시한 심볼 전체를 읽는다.')
snippet_specs=[
    ('입력 계약', 'http/contracts/tags.py', 'model_config = ConfigDict(extra="forbid")', '알 수 없는 입력 필드를 거절한다. 모든 DTO가 같은 정책인 것은 아니다.'),
    ('업무 트랜잭션', 'modules/content/character/service/command.py', 'async with use_case_transaction(session):', '업무 단위의 commit/rollback을 공통 컨텍스트에 맡긴다.'),
    ('저장소 접근', 'modules/content/character/service/command.py', 'row = await Repository.create_character_command(session, command)', 'service가 repository의 SQL 실행 결과를 받아 mapper로 넘긴다.'),
    ('응답 변환', 'modules/content/product/mapper/schema.py', 'return Schemas.PublishedProductInfoResponseDto.model_validate(result)', '반환 계약을 다시 검증한다. nullable 불일치가 이 단계에서 드러날 수 있다.'),
    ('인증 객체 주입', 'http/dependencies.py', 'Owner = Annotated[UUID, Depends(get_current_owner_id)]', '검증된 호출자 ID의 주입 지점이다. 데이터 소유권 검사는 service의 별도 책임이다.'),
    ('오류 응답', 'http/dependencies.py', 'raise HTTPException(422, str(exc)) from exc', 'ValueError를 업무 입력 오류로 변환한다. DB 제약 예외는 이 분기에 자동 포함되지 않는다.'),
    ('취소 처리', 'modules/content/character/service/workflow/media.py', 'await asyncio.shield(task)', '저장 작업의 종료를 기다리기 위해 취소 전파를 제어한다. 실패·종료 경로까지 함께 읽어야 한다.'),
    ('DB 로그 설정', 'main.py', 'os.environ["DATABASE_URL"], pool_pre_ping=True, hide_parameters=True', '엔진 연결 검사와 SQL 바인딩 값 은닉을 설정한다. URL 값 자체는 보고서에 수록하지 않는다.'),
]
rows=[]
for topic,path,needle,explanation in snippet_specs:
    line=next(s.strip() for s in (ROOT/APP/path).read_text(encoding='utf-8-sig').splitlines() if needle in s)
    rows.append([topic+' — '+line, explanation+' 근거: '+ref(path,needle)])
table(['패턴 / 실제 코드 발췌','역할과 근거'],rows)
p('# 6. 핵심 요청 흐름')
diagram('answer-sequence','답변 생성: 예약·외부 호출·결과 확정','sequence',actors=['Client / HTTP','Answer workflow','DB services','LLM'],steps=[(0,1,'입력 ID / revision / request_key + 인증 사용자'),(1,2,'기존 요청 조회 · 소유권 · 참여자 · runtime 확인'),(1,2,'문맥 수집; 필요한 memory retrieval'),(1,2,'재검증 + generation / quote / reservation / prompt COMMIT'),(1,2,'phase=calling 저장 COMMIT'),(1,3,'DB 트랜잭션 밖 generate_text'),(3,1,'content / usage 또는 정규화 오류'),(1,2,'result_ready staging COMMIT'),(1,2,'메시지 + usage + memory 예약 + credit 확정/해제 COMMIT'),(1,0,'저장된 답변 · pending 재전송 202')])
p('준비 후 DB 잠금을 재획득해 준비 digest와 실행 조건을 비교한다. 최종 프롬프트는 어댑터 변환 전 request_json 그대로 저장한다. 실패·취소·stale는 청구 0이며 예약을 해제한다. 불확실한 외부 호출은 같은 키로 조회·복구하되 다시 실행하지 않는다. result_ready가 있으면 저장 결과를 재사용하고, calling 단계에서 결과가 없으면 불확실 실패를 기록한다. 이 계약은 exactly-once 외부 호출을 보장한다는 뜻이 아니다.')
p('근거: '+ref(M+'chatting/chat/service/workflow/answers.py','generate_answer')+'; '+ref(M+'chatting/chat/service/workflow/answers.py','_finalize')+'; '+ref(M+'chatting/chat/service/command/prompts.py','save_generation_prompt'))
diagram('publication-sequence','스튜디오 발행과 재전송','sequence',actors=['HTTP','studio use case','공개 content services','DB'],steps=[(0,1,'인증 owner + expected_revision + 모델 / 노트'),(1,2,'상품 / 초안 잠금 · 소유권'),(2,3,'저장 draft 및 receipt 읽기'),(1,1,'기존 revision receipt의 fingerprint 비교'),(1,2,'캐릭터 / 로어 원본 및 미디어 연결 갱신'),(1,2,'composition / settings / publish_product'),(2,3,'원본별 snapshot + 상품 snapshot + release'),(1,2,'revision receipt와 컴포넌트 mapping 저장'),(1,3,'단일 transaction COMMIT; 실패 시 전체 ROLLBACK'),(1,0,'release; 응답 유실 재호출은 저장 receipt')])
p('상품 → 소스 캐릭터 → 로어북의 잠금과 같은 DB 세션을 공유한다. 업로드된 파일은 이미 ready여야 하며 발행 과정에서 파일을 새로 업로드하지 않는다. raw publish_product는 요청키 멱등 API가 아니고, studio use case의 revision receipt가 재전송 계약을 추가한다. 현재 후속 발행을 지원하는 코드와 기존 문서·테스트의 “첫 발행 후 수정 거절” 설명이 다르다(F05/F06).')
p('근거: '+ref('use_cases/studio_publication.py','publish_studio')+'; '+ref(M+'content/product/service/command/studio.py','save_studio_draft')+'; '+ref(M+'content/product/service/command/releases.py','publish_product'))
diagram('media-sequence','미디어 업로드·취소·정리','sequence',actors=['HTTP','Media workflow','DB','Storage'],steps=[(0,1,'소유자 / request UUID / 본문 metadata'),(1,2,'pending 예약 COMMIT'),(1,2,'캐릭터 / 미디어 row 잠금'),(1,3,'store_asset; 취소 시에도 작업 종료 대기'),(3,1,'저장 결과'),(1,2,'ready COMMIT; 모호한 실패는 pending 재개'),(1,0,'앱 내부 content URL'),(1,2,'정리 CLI: 24h 보존·참조 없음 → deleting COMMIT'),(1,3,'객체 삭제; 실패 시 deleting 재시도'),(1,2,'deleted COMMIT')])
p('답변 생성과 달리 미디어는 저장소 작업이 실제로 끝날 때까지 DB 잠금을 유지하는 의도된 예외다. S3 thread 작업을 취소했다고 서버 측 쓰기가 즉시 종료되는 것은 아니기 때문이다. HTTP reader는 StreamingResponse 종료 시 닫는다. 이 파일 스트리밍과 답변 토큰 스트리밍을 구분해야 한다.')
p('근거: '+ref(M+'content/character/service/workflow/media.py','_settle_storage')+'; '+ref('http/media.py')+'; '+ref('media_cleanup.py'))
diagram('auth-sequence','이메일 인증과 refresh 경쟁','sequence',actors=['Client','Identity workflow','DB','SMTP'],steps=[(0,1,'가입 · Origin / CSRF · 입력 제한'),(1,2,'정규화 이메일 잠금 / pending 계정 / 증명 hash'),(1,2,'COMMIT'),(1,3,'증명 메일 발송'),(1,0,'정상 또는 mail_unavailable; 계정은 유지'),(0,1,'refresh JWT'),(1,2,'사용자→세션 잠금 / 현재 refresh hash 비교'),(1,2,'일치: 회전; 재사용: 계열 폐기 COMMIT'),(1,0,'새 쿠키 또는 refresh_reused')])
p('refresh 응답 유실 뒤 예전 토큰을 재전송하면 계열 폐기가 발생할 수 있다. 이 정책은 문서화된 계약이다. 클라이언트 탭 간 갱신 직렬화가 필요하다. Google 로그인은 state를 외부 통신 전에 소모하고, 실패 시 새 로그인 흐름으로 다시 시작한다.')
p('근거: '+ref(M+'identity/service/authentication.py','refresh_session')+'; '+ref(M+'identity/service/workflow/mail.py')+'; '+ref(M+'identity/service/workflow/google.py'))
diagram('memory-sequence','기억 작업: claim·외부 처리·출처 재검증','sequence',actors=['Worker','Memory/chat','DB','LLM / embedding'],steps=[(0,1,'claim(worker_id, lease)'),(1,2,'FOR UPDATE SKIP LOCKED · scope 고정 COMMIT'),(0,1,'pending 색인 먼저; 원문·revision 읽기'),(1,3,'요약 / 임베딩; 읽기 세션 종료 상태'),(1,2,'conversation lock + 원문 digest / revision 재검증'),(1,2,'pending summary → ready vector'),(1,2,'worker/scope 확인; 완료 또는 다음 generation pending'),(1,0,'실패 시 정규화 종류 + 제한 backoff')])
p('동시에 메시지가 편집되면 저장 직전에 source ID·position·revision·digest를 다시 확인한다. append만으로 이전 범위의 요약이 무효화되지는 않는다. lease 기간보다 작업이 오래 걸릴 때 외부 호출 중복 가능성은 별도로 관리해야 한다(F07).')
p('근거: '+ref(M+'chatting/chat/service/workflow/memory.py','_persist_summary')+'; '+ref(M+'chatting/memory/repository.py','claim_memory_work'))

p('# 7. DB 구조와 관계도')
p('ERD는 현재 SQLAlchemy 메타데이터로 생성했다. 운영 DB introspection이 아니다. PostgreSQL migration이 적용된 실환경과 일치한다고 단정하지 않는다. 전체 ERD는 도메인 개요와 모든 FK의 도메인별 분할 그림으로 구성하고, 테이블 사전에 600개 컬럼 및 제약을 수록했다. 독립 테이블도 사전에서 누락하지 않았다.')
groups=defaultdict(list)
for t in TABLES:groups[owner(t)].append(t)
domain_edges=Counter((owner(r['child']),owner(r['parent'])) for r in fkrows if owner(r['child'])!=owner(r['parent']))
diagram('erd-overview','전체 ERD: 소유 도메인과 물리 FK','module',nodes=list(groups),counts={g:len(ts) for g,ts in groups.items()},edges=sorted(domain_edges),count_label='tables')
p('화살표는 자식의 FK → 참조 부모 방향이다. 숫자는 도메인 소유 테이블 수다. 이 그림의 도메인 간 선은 물리 FK가 존재함을 뜻하며 서비스 import나 호출 권한을 뜻하지 않는다. 세부 그림은 FK 하나를 한 행으로 펼쳐 교차선을 줄였다.')
table(['소유 도메인','주요 생성·수정·삭제 주체'],[['identity','가입/로그인/증명/refresh; auth_cleanup 만료 정리'],['character / lorebook','owner command; product 발행이 공개 freeze 호출; media cleanup은 참조 없는 객체만 삭제'],['product','편집·발행 command; statistics use case가 집계/dirty queue 갱신'],['conversation / chat','시작·버전 command; 메시지 편집·rewind; 답변 workflow; 관리자 prompt 조회는 읽기'],['memory','worker 저장·색인; chat 편집 시 공개 무효화 서비스; conversation FK CASCADE'],['billing / credit','견적·usage·결제 귀속; 서버 전용 지급/예약/정산. 현금 승인 실행자는 없음'],['moderation','report/assessment/action command; actual 제재 적용자는 미구현'],['tag / llm','관리자 사전·종료 정책; content가 연결 소유; 원본 상태와 발행 snapshot 분리']])
p('범례: 부모/자식의 수량은 FK nullable 및 자식 FK 컬럼의 PK/UNIQUE로 추론했다. “자식당 부모 1”은 필수 FK, “0..1”은 nullable FK다. “부모당 자식 0..1”은 유일 FK, “0..N”은 반복 가능 FK다. 부분 UNIQUE와 복합 MATCH SIMPLE의 NULL 조합은 도표보다 세부 제약을 우선한다. DELETE/UPDATE가 NO ACTION이면 자동 연쇄 변경을 지정하지 않은 것이다.')
for g,ts in groups.items():
    p('## '+g+' 관계')
    p('소유 테이블: '+', '.join(ts)+'.')
    rows=[r for r in fkrows if r['owner']==g]
    if not rows:p('이 도메인은 물리 FK가 없다.')
    for i in range(0,len(rows),9):diagram('erd-'+g.replace('/','-')+'-'+str(i//9+1),g+' 상세 FK '+str(i//9+1),'relations',rows=rows[i:i+9])
p('## 물리 FK와 논리적 참조의 차이')
table(['연결','의미 / 검증 책임'],[['character_media.owner_id / character_id','정리·복구 기록 보존을 위해 cascade FK가 없다. 업로드와 첨부 service가 실제 소유권 검증.'],['moderation target_id / domain_action_id','다형 대상·과거 보존 식별자. 직접 FK가 아니며 대상 공개 서비스로 확인.'],['billing quote의 모델·작품 실행 snapshot','발급 당시 사실 보존. 현재 카탈로그를 JOIN해서 과거 값을 재작성하지 않음.'],['credit reference_id / result_id','호출자가 공급하는 업무 식별자. credit은 의미나 타 도메인의 존재를 조회하지 않음.'],['snapshot JSON 및 generation prompt 원문','행의 FK와 별개로 본문 불변성은 애플리케이션 계약. DB 직접 UPDATE 방지 트리거가 있는 것은 아님.'],['tag 연결','현재 태그 이름이 바뀌면 조회에 반영. 발행 snapshot으로 복사되지 않음.']])
p('## 마이그레이션 경로와 대조')
p('Alembic은 0001 고정 baseline부터 revision 체인으로 적용하며 현재 head는 0030이다. 새 DB 초기화는 infra/postgres/init SQL 경로다. ORM create_all은 테스트용 현재 스키마 생성이며 운영 업그레이드를 대체하지 않는다. 초기화 SQL과 Alembic을 같은 기존 DB에 무조건 겹쳐 적용해서는 안 된다.')
p('0030 generation_prompts의 고정 SQL과 초기 SQL 020은 byte 비교로 대조하고 결과를 schema-comparison.json에 남겼다. 0027 검수 DDL도 대응 초기 SQL과 대조한다. 0029 태그는 기존 kind 제거 및 다중 모듈 연결로 전환하므로 과거 DDL과 단순 파일 동일성을 요구할 수 없다. 전 revision의 실제 upgrade·downgrade 및 CHECK/인덱스/기본값 동일성은 PostgreSQL 실행 없이는 확정하지 못했다.')
p('근거: '+ref('apps/api/alembic/env.py')+'; '+ref('apps/api/alembic/versions/0030_generation_prompts.py')+'; '+ref('apps/api/tests/test_product_migrations.py')+'; '+ref('apps/api/tests/conftest.py'))

p('# 8. API와 보안 경계')
table(['경로군','인증 / 인가 / 주의점'],[['/auth/*','AuthRoute의 rate limit·CSRF·Origin·안전한 오류; access/refresh HttpOnly 쿠키'],['/products/catalog, /products/catalog/{id}','익명 조회. 목록은 approved+public+현재 snapshot 만료 제외; 상세는 기존 accessible 정책(비private)을 사용. unlisted는 목록 제외와 직접 링크 접근 허용을 구분.'],['/models/available','익명 조회(Session만 의존). 활성·종료 전 모델의 ID·이름·추론 수준 반환. 모델 조회와 유료 생성 인가는 별개.'],['/characters/me, /lorebooks/me, /products/* 편집','인증 owner와 경로 ID를 조합하여 서비스 소유권 검사'],['/conversations/* /messages /answers','소유 대화 범위. 공개 사용자 메시지 쓰기와 내부 AI 출력 쓰기 분리. revision·pending 충돌은 409.'],['/account/credits*','인증 사용자·CREDIT 재화로 스코프. 내부 지급·구매 API가 아님.'],['/admin/tags 및 내부 태그','identity.require_admin으로 활성 관리자 재검증. source·assigned_by를 클라이언트에서 받지 않음.'],['/admin/reporting/generation-prompts','목록·상세에 활성 admin 검사. 목록 원문 제외; 상세 no-store.'],['기존 character/lorebook 관리자·검수','전용 guard 기본 503, main에 override 없음(F02). 일반 owner 인증 연결로 자동 해결되지 않음.']])
p('CSRF(Cross-Site Request Forgery)는 브라우저 쿠키가 붙는 상태 변경 요청을 다른 사이트가 유도하는 공격이다. 이 코드에서는 Origin 허용 목록과 서명된 CSRF cookie/header 일치를 확인한다. 인증 엔드포인트는 누락 Origin도 거절한다. 일반 쿠키 인증 상태 변경도 middleware에서 검사한다. 프록시 신뢰 범위와 TLS 설정은 실제 배포에서 별도로 검증해야 한다.')
p('오류 계약: 인증은 {error:{code}}, 일반 HTTPException은 {detail}, 입력 검증은 FastAPI 422 구조가 기본이다. 인증 DTO 오류는 비밀번호·토큰 입력이 반사되지 않도록 변환된다. 다른 업무의 입력/예외 로그 전체가 같은 보장을 갖는다고 추정하지 않는다.')
p('근거: '+ref(M+'identity/http_security.py','verify_csrf')+'; '+ref(M+'identity/http_security.py','error_response')+'; '+ref(M+'identity/settings.py','AuthSettings')+'; '+ref(M+'reporting/operations_reporting/router.py'))
p('민감한 최종 프롬프트에는 캐릭터·로어·기억·대화 원문이 들어간다. 현재 원문 조회는 관리자 전용으로 제한되지만, 운영 보존기간·삭제 요청·조회 감사 정책은 별도의 결정이 필요하다. 본 보고서는 실데이터를 수집하지 않았고 규제 준수 여부를 판단하지 않는다.')

p('# 9. 정합성·동시성·실패 처리')
table(['경계','보장과 한계'],[['use_case_transaction','같은 session.info 표식이면 참여. 중첩 실패를 외부에서 잡아도 rollback-only. 기존 AUTOBEGIN을 임의 채택하지 않음.'],['멱등성','DB advisory lock은 아직 행이 없는 요청도 직렬화. UNIQUE만으로 입력 동일성을 증명하지 않으므로 각 서비스가 지문·필드 비교.'],['메시지','conversation FOR UPDATE, position 순서, expected_revision. rewind 이후 receipt를 재생성 허가로 사용하지 않음.'],['답변','예약 commit→LLM→staging→최종 commit. 실행 token/lease로 늦은 staging 차단. 공급자 성공과 DB 저장 사이에는 불확실 구간 존재.'],['크레딧','wallet lock→예약/balance 쓰기. free/paid 배분 보존. 원장 header/entry/잔액 누계는 애플리케이션과 통합 검증 책임.'],['발행','동일 DB transaction으로 component snapshot·상품 snapshot·release·receipt 저장. 외부 파일은 이미 준비되어야 함.'],['미디어','외부 작업 종료까지 row lock 유지. 프로세스 중단 뒤 pending/deleting에서 재개. DB+S3 원자성 보장 아님.'],['기억','출처 revision/digest와 unique로 저장 충돌 방어. lease 재claim은 외부 호출 중복 방지와 별개.'],['통계','dirty day 재집계; 실패 rollback으로 작업 유지. reporting의 여러 SELECT는 고정 snapshot 보장 안 함.']])
p('잠금 순서 검토 시 단일 파일만 보면 안 된다. 답변은 conversation→generation과 billing request→credit wallet의 순서를 조합하고, 발행은 product→정렬된 source를 사용한다. 공유 트랜잭션에서 이미 수행한 조회가 AUTOBEGIN을 시작했는지 확인해야 한다. DB deadlock과 serialization failure의 실제 빈도는 이번 검토로 측정하지 않았다.')
p('근거: '+ref('db/transaction.py','use_case_transaction')+'; '+ref('db/idempotency.py','lock_key')+'; '+ref(M+'commerce/credit/service/command.py','_require_credit_transaction')+'; '+ref(M+'commerce/billing/service/credits.py','reserve_credit'))

p('# 10. 테스트와 운영 관측')
p('이번 실행의 전체 결과는 529 통과·4 실패·290 건너뜀이다. DB 및 실제 공급자 설정을 의도적으로 제거했으므로 PostgreSQL 잠금·실제 SQL·마이그레이션·외부 SDK 통신을 검증하지 않았다. 건너뜀은 성공이 아니다. 전체 항목과 사유는 tests.xml에 있다.')
tree=ET.parse(OUT/'tests.xml');cases=tree.findall('.//testcase')
failures=[x for x in cases if x.find('failure') is not None]
table(['실패 테스트','직접 실패 원인 / 해석'],[['catalog_title_and_description…','fixture는 snapshot_data.product.title, 현재 발행/mapper는 snapshot_data.title. fixture 형태 불일치; 실제 발행본 오류로 바로 단정할 수 없음.'],['edit_after_first_publication…','불완전 SimpleNamespace에 product_id가 없어 mapper에서 실패. 테스트는 과거 수정 금지 계약을 기대; 현재 구현은 새 초안 저장 후 후속 발행.'],['same_revision_publication_retry…','삭제된 publication.ProductQuery를 monkeypatch하려다 AttributeError. 본문 검증 전 실패.'],['initial_publication_uses_one…','같은 ProductQuery 참조로 setup 실패. 현재 원자성 검증 완료를 의미하지 않음.']])
p('기존 계약 테스트 10개는 모듈 간 공개 경계, ORM 접근 제한, credit 소유권, OpenAPI 기준을 검사한다. 다만 OpenAPI 검사는 app.main 전체 HTTP 조립 대신 modules의 router를 수집한다. app/http의 catalog 상세·account·studio 조립은 별도 테스트를 함께 봐야 한다. AST는 별칭·동적 호출 전체를 증명하는 정적 분석기는 아니다.')
p('Ruff는 61건을 보고했다. 포맷·import 정렬·테스트 표현 및 예외 정책이 섞여 있다. 자동 수정은 수행하지 않았다. 답변 복구의 except Exception은 “외부 작업을 재실행하지 않고 durable 상태를 조회”하려는 의도가 있으므로 모두 동일한 버그로 분류하지 않았다. Alembic heads는 0030 단일 head를 확인했다.')
p('운영 관측 보완 제안: 답변 pending/lease 만료와 recovery 실패 수, 크레딧 RESERVED 장기 체류, memory job age/attempts, 미디어 pending/deleting 장기 체류, 통계 dirty 날짜를 모니터링 지표로 잡는다. 구조화 로그는 존재하지만 전체 요청 correlation ID, readiness, 정리 작업 실행 주기를 이번 코드만으로 운영 적용 완료라고 확인할 수 없다.')
p('근거: '+ref('apps/api/tests/test_architecture_contracts.py','test_openapi_contract_is_unchanged')+'; '+ref('main.py','recover')+'; '+ref('memory_worker.py','run_worker')+'; '+ref(M+'content/product/statistics_job.py'))

FINDINGS=[
('F01','P2 · 버그','시작 옵션 제목의 nullable 계약 불일치','즉시 수정','start_set 로어의 title=None이 생성·발행 검증을 통과하고 snapshot title도 nullable인데 StartOptionInfoResponseDto.title은 str이다.','공개 작품 상세의 응답 변환에서 ValidationError가 발생할 수 있다. 일반 입력으로 만들어진 발행본을 읽지 못하는 조건부 오류다.','원본의 nullable 계약을 유지하려면 시작 옵션에 한정한 표시 fallback 또는 DTO nullable 정책을 명확히 정하고 기존 소비자와 맞춘다.','제목 없는 start_set 생성→발행→공개 상세를 실제 PostgreSQL+HTTP로 검증하고 기존 title 있는 응답도 비교한다.','합성 입력으로 entry 검증 통과·응답 ValidationError 재현. DB 발행 E2E 미실행.',[(M+'content/lorebook/service/command.py','_validate_lorebook_entry'),(M+'content/product/service/command/settings.py','_validate_publication'),(M+'content/product/repository/publication.py','add_snapshot_start'),(M+'content/product/schemas.py','StartOptionInfoResponseDto')]),
('F02','P2 · 버그','관리자·검수 전용 인증 가드가 기본 앱에 연결되지 않음','노출 전 즉시 수정','character/lorebook admin 및 moderator 함수는 항상 503을 내며 create_app의 override 목록은 owner/DB hook만 포함한다.','일반 사용자 인증이 작동해도 기존 전역 조회·검수 API를 정상 사용할 수 없다. 거절 기본값이므로 인증 우회 취약점으로 분류하지 않는다.','역할 정책을 정하고 identity 공개 서비스에 연결하거나 미지원 경로를 명시적으로 비활성화한다. 가드를 무조건 통과시키는 수정은 피한다.','기본 create_app 경로에서 비인증/일반/관리자/검수자별 401·403·성공 및 도메인 호출 차단을 검증한다.','합성 가드 호출에서 503, 앱 override 부재 확인. 실제 배포의 별도 override는 미확인.',[('http/character_dependencies.py','require_character_admin'),('http/lorebook_dependencies.py','require_lorebook_moderator'),('main.py','create_app')]),
('F03','P2 · 버그','검수자 ID가 대상 콘텐츠의 소유자 필터로 사용됨','F02 연결과 함께 수정','검수 mapper가 인증된 행위자 ID를 owner_id에 넣고 change_character_status/change_lorebook_status가 소유자 조회로 대상을 제한한다.','전용 guard를 연결해도 다른 사용자의 콘텐츠를 검수하면 404가 될 수 있다. 현재 기본 503이 먼저 발생해 경로가 가려져 있다.','actor_id와 대상 ID를 분리한 관리자/검수 command를 정의하고 서비스에서 역할 및 대상 상태 전이를 검증한다. 일반 소유자 update 권한을 넓히지 않는다.','A 소유 콘텐츠에 관리자 B의 승인/거절 성공, 일반 C 거절, 삭제된 대상 404, 감사행위자 B 보존을 검증한다.','character 경로의 mapper→service repository 인자 합성 재현. lorebook은 동일 구조 정적 확인.',[(M+'governance/moderation/mapper/character.py','change_character_status_request_to_command'),(M+'content/character/service/command.py','change_character_status'),(M+'content/lorebook/service/command.py','change_lorebook_status')]),
('F04','P2 · 버그','중복 기본 이미지/감정 태그 제약이 일반 업무 오류로 변환되지 않음','다음 개선','두 번째 is_default=True 이미지 또는 동일 emotion_tag 추가 시 create_media_attachment는 INSERT/flush하며 부분 UNIQUE·UNIQUE가 충돌한다. router는 LookupError/ValueError만 주로 변환한다.','정합성은 DB가 보호하지만 예상 가능한 사용자 충돌이 500 계열로 전달될 수 있다. 기존 기본 이미지를 바꾸는 set_default 경로와 의미가 다르다.','같은 캐릭터 잠금 안에서 업무 정책을 정하고 충돌을 409/422로 변환한다. 기존 기본값 해제 여부도 명시한다.','실제 PostgreSQL에서 연속·동시 기본 이미지 추가, 감정 태그 중복, managed binding rollback을 검증한다.','DDL와 호출 경로 정적 확인; PostgreSQL HTTP 재현 미실행.',[('db/models/character.py','CharacterImage'),(M+'content/character/service/media.py','_attach_character_media'),(M+'content/character/repository.py','create_media_attachment'),(M+'content/character/router.py','_service_errors')]),
('F05','P2 · 유지보수','현재 스튜디오·카탈로그 변경과 회귀 테스트가 불일치','즉시 수정','기존 전체 suite에서 4개 실패. fixture snapshot 구조·필수 필드·삭제된 import alias가 현재 코드와 다르다.','회귀 신호를 신뢰하기 어렵고 발행 원자성·재전송 검사가 실행 본문에 도달하지 못한다. 운영 버그 4개가 확인됐다는 뜻은 아니다.','현재 공개 계약 기준으로 대역을 재작성하고 세부 내부 alias 대신 공개 경계로 검증한다. 후속 발행이 의도된 변경인지 문서와 테스트를 함께 맞춘다.','전체 suite 0 실패와 실제 PostgreSQL test_repository_workflows·발행/과금 회귀를 실행한다.','이번 실행 4 failed/529 passed/290 skipped로 확인.', [('apps/api/tests/test_product_catalog_page.py','test_catalog_title_and_description_come_from_published_snapshot'),('apps/api/tests/test_studio_draft_guard.py','test_edit_after_first_publication_does_not_change_product_visibility'),('apps/api/tests/test_studio_publication.py','test_initial_publication_uses_one_composed_transaction')]),
('F06','P3 · 유지보수','ARCHITECTURE와 현재 공개 기능의 설명이 어긋남','다음 개선','product/use_cases는 후속 발행 미지원이라고 설명하지만 현재 revision receipt와 후속 편집·발행 코드가 있다. lorebook/prompt는 manual·배치·예산 설명이 새 activation 구현을 반영하지 못한다.','새 코드를 검토할 때 잘못된 전제로 영향 범위를 판단하거나 이미 구현된 기능을 다시 생성할 수 있다.','현행 계약과 과거 이력을 분리하고 새 공개 인터페이스 변경 시 ARCHITECTURE 갱신을 완료 조건으로 둔다.','문서의 파일 경로·함수와 실제 구현의 대응을 확인하고 대표 흐름 테스트 링크를 갱신한다.','문서/코드 대조 확인. 원본 문서는 수정하지 않음.',[(M+'content/product/ARCHITECTURE.md',None),('use_cases/ARCHITECTURE.md',None),(M+'content/lorebook/ARCHITECTURE.md',None),(M+'content/lorebook/service/activation.py','diagnose_entries'),('use_cases/studio_publication.py','publish_studio')]),
('F07','P2 · 성능','memory lease 만료 이후 외부 작업이 중복될 수 있음','장기 작업 운영 전 개선','worker는 기본 300초 lease로 claim하고 heartbeat 갱신이 없다. 작업 전체의 강제 상한이 lease보다 짧음을 보장하는 공통 경계도 없다.','요약/임베딩 지연이 lease를 넘으면 다른 worker가 같은 대화를 재claim해 공급자 호출을 중복할 수 있다. UNIQUE·revision 검증은 저장 정합성과 별개이며 외부 비용을 되돌리지 못한다.','작업별 실행 token/lease 갱신과 종료 조건, 또는 보수적인 전체 timeout을 설계한다. 외부 성공 후 저장 실패 복구도 함께 다룬다.','2 worker에서 공급자 대역을 lease 이상 지연시키고 호출 횟수·오래된 worker 저장 차단·회수 가능성을 검증한다.','정적 조건부 위험. 다중 worker·실제 지연 재현 미실행.',[('memory_worker.py','run_worker'),(M+'chatting/memory/repository.py','claim_memory_work'),(M+'chatting/chat/service/workflow/memory.py','_process_memory_work')])]
p('# 11. 발견 사항과 개선 순서')
p('P2는 특정 정상 사용 조건에서 기능 오류 또는 검증 공백을 만드는 항목, P3는 유지보수 위험이다. 운영 장애·유출이 관찰되지 않은 항목을 P0/P1로 올리지 않았다. 서로 다른 신뢰 수준의 근거를 각 항목에 명시했다.')
for id,level,title,priority,condition,impact,fix,validation,confidence,refs in FINDINGS:
    p('## '+id+' · '+title)
    table(['항목','내용'],[['유형 / 심각도',level],['우선순위',priority],['발생 조건',condition],['영향',impact],['수정 방향',fix],['수정 후 검증',validation],['확인 수준 / 한계',confidence]])
    p('근거: '+'; '.join(ref(a,b) for a,b in refs))
p('권장 순서: F05로 신뢰할 수 있는 회귀 기준을 먼저 회복하면서 F01의 공개 응답 결함을 수정한다. 운영 관리자/검수 경로를 사용할 계획이면 F02와 F03을 하나의 권한 계약 변경으로 처리한다. 이후 F04, 문서 갱신 F06, 장시간 worker 조건 F07을 진행한다. 전체 구조의 일괄 재작성보다 작은 공개 계약 단위로 검증하는 편이 적합하다.')

p('# 12. 향후 코드 검토 체크리스트')
for s in ['새 파일을 만들기 전에 해당 모듈의 책임과 소유 테이블을 확인했는가?','다른 모듈의 repository·mapper·ORM 대신 공개 service/types만 사용하는가?','router가 받은 owner/actor는 검증된 인증 dependency에서 왔는가? 역할과 소유권은 구분했는가?','공개 Command·Info·DTO의 nullable·범위·enum이 저장 제약과 일치하는가?','최상위 transaction과 중첩 참여 방식, AUTOBEGIN·SAVEPOINT 차이를 확인했는가?','동일 요청키·다른 입력·응답 유실·동시 요청 시 의미가 명시되어 있는가?','DB와 외부 호출 사이의 불확실 상태, 취소, lease 복구를 설명할 수 있는가?','원본 편집이 발행 snapshot·과거 청구·프롬프트 이력을 바꾸지 않는가?','테스트가 현재 공개 계약을 검증하는가? setup에서 실패하거나 DB skip을 성공으로 보고하지 않는가?','OpenAPI·HTTP 조립 경로·기존 응답 필드와 dependency override 계약을 확인했는가?','로그/오류에 원문·토큰·바인드 값이 노출되지 않는가?','ARCHITECTURE.md·ERD·마이그레이션 양 경로·운영 진입점 문서를 갱신했는가?']:p('- '+s)

p('# 부록 A. 전체 API 목록')
p('실제 create_app의 중첩 router prefix를 합산하여 추출했다. 각 dependency는 함수명 기준이고 서비스 내부의 추가 권한 검사는 별도다. 세부 필드·상태 코드는 현재 schema와 테스트를 확인한다. CSV는 기계 처리용 전체 목록이다.')
for group in ['auth','account','characters','lorebooks','products','conversations','admin','models']:
    rs=[r for r in D['routes'] if r['path'].split('/')[1]==group]
    if not rs:continue
    p('## /'+group)
    table(['메서드 / 경로','진입 함수 / 의존성'],[[','.join(r['methods'])+' '+r['path'],r['function']+'; '+(', '.join(x.split('.')[-1] for x in r['dependencies']) or '없음')] for r in rs])
    p('원본: '+', '.join(sorted({r['file'] for r in rs})))

p('# 부록 B. 전체 테이블 사전')
p('각 표는 현재 ORM의 모든 컬럼을 포함한다. PK=기본키, NULL=선택값, UQ=유일 제약. UUID·생성시각 기본값 등은 schema.json의 server default를 참조한다. 제약·인덱스는 실제 이름과 컬럼을 기록하되 길이가 긴 CHECK 식은 schema.json에 원문을 보존했다. UPDATE 정책은 FK 그림 및 relationships.csv에 있다.')
for g,ts in groups.items():
    p('## '+g+' 테이블')
    for name in ts:
        t=TABLES[name];p('### '+name)
        src,cls=model_sources[name];p('근거: '+ref(src,cls))
        table(['컬럼','타입','제약'],[[c['name'],c['type'],('PK ' if c['pk'] else '')+('NULL' if c['nullable'] else 'NOT NULL')] for c in t['columns']])
        constraints=[]
        for c in t['constraints']:
            if c['kind']=='UniqueConstraint':constraints.append('UQ '+str(c['name'])+' ('+', '.join(c['columns'])+')')
            elif c['kind']=='CheckConstraint':constraints.append('CHECK '+str(c['name'])+': '+c['sql'])
        for i in t['indexes']:constraints.append(('UNIQUE INDEX ' if i['unique'] else 'INDEX ')+str(i['name'])+' ('+', '.join(i['columns'])+')'+(' WHERE '+i['where'] if i['where']!='None' else ''))
        for line in constraints:p('- '+line)
        if not constraints:p('별도의 UQ/CHECK/일반 인덱스 선언 없음. PK와 FK는 별도 참조.')
        if t['fks']:p('FK: '+'; '.join(','.join(fk['columns'])+' → '+fk['target']+'('+','.join(fk['target_columns'])+'), DELETE '+fk['ondelete'] for fk in t['fks']))
        else:p('물리 FK 없음. 논리적 참조가 있는지는 7장의 설명을 함께 확인한다.')

p('# 부록 C. 근거·재생성·남은 검증')
p('보고서 원본은 backend-review.md다. render_report.py는 이 원본과 diagrams/*.json으로 PDF를 다시 만든다. author_report.py는 조사 입력에서 원본을 생성하므로 수동 수정한 Markdown을 덮어쓸 수 있다. 반복 편집에서는 render_report.py만 실행한다. README.md에 런타임과 명령을 기록했다.')
p('첨부 데이터: inventory.json(파일 해시·심볼·ORM·라우트), schema.json(전체 제약 원문), relationships.csv(FK 139개), api-inventory.csv(HTTP 114개), module-dependencies.json(import 근거), coverage.csv(검토 깊이), evidence.json(인용 근거), tests.xml 및 pytest-verified.log, ruff.json, probes.json, schema-comparison.json, source-integrity.json. 다이어그램은 JSON 원본과 SVG/PDF/PNG 렌더링을 보존한다.')
p('남은 검증: 별도 테스트 PostgreSQL에서 전 migration과 ORM/초기 SQL 비교, 실제 row lock 경쟁·rollback·동시 생성·후속 발행, 운영 역할 연결, 공급자 timeout/취소·S3 복구, 부하/인덱스 실행계획, 운영 보존·백업·스케줄러. 이 검증을 끝내기 전에는 본 보고서를 운영 준비 완료 판정으로 사용하지 않는다.')

(OUT/'backend-review.md').write_text('\n'.join(parts),encoding='utf8')
(OUT/'diagrams').mkdir(exist_ok=True)
for d in diagrams:(OUT/'diagrams'/f"{d['id']}.json").write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'schema.json').write_text(json.dumps(D['tables'],ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'module-dependencies.json').write_text(json.dumps(dict(edges=[dict(source=a,target=b,evidence=v) for (a,b),v in sorted(edges.items())],strongly_connected_groups=cycles),ensure_ascii=False,indent=2),encoding='utf8')
cited={r['path'] for r in evidence}
with (OUT/'coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['path','lines','depth','sha256','note'])
    for file in D['files']:
        depth='구현 확인(인용 심볼 중심)' if file['path'] in cited else '목록/AST/메타데이터 확인'
        if '/tests/' in file['path'] and file['path'].endswith('.py'):depth='전체 suite 수집·실행; 개별 통과/실패/skip은 tests.xml'
        w.writerow([file['path'],file['lines'],depth,file['sha256'],'파일 전체 분기 수작업 전수 감사 아님'])
comparisons=[]
for a,b in [('apps/api/alembic/sql/0030_generation_prompts.sql','infra/postgres/init/020_generation_prompts.sql'),('apps/api/alembic/sql/0027_moderation_review.sql','infra/postgres/init/018_moderation_review.sql')]:comparisons.append(dict(a=a,b=b,bytes_equal=(ROOT/a).read_bytes()==(ROOT/b).read_bytes(),text_equal=(ROOT/a).read_text(encoding='utf8')==(ROOT/b).read_text(encoding='utf8')))
(OUT/'schema-comparison.json').write_text(json.dumps(comparisons,indent=2),encoding='utf8')
print('report chars',sum(len(x) for x in parts),'diagrams',len(diagrams),'evidence',len(evidence),'modules',len(mods),'cycles',cycles,'DDL',comparisons)
