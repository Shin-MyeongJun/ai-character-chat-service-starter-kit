# 회원가입부터 첫 답변까지 통합 검증

2026-09-20 현재 기본 `app.main.create_app()`은 identity의 실제 쿠키 인증에 연결되어 있다. `authenticate` 주입이나 인증 dependency override 없이 가입→이메일 인증→로그인→콘텐츠 준비→대화 생성→사용자 메시지 저장→비스트리밍 답변→대화 내역 조회가 동작한다. 외부 API 계약과 상품 이용 권한은 변경하지 않았다.

`references_document/work/nonstream-chat-orchestration.md`의 “인증 미구현/기본 앱 503/검증된 Bearer 주입 필요”는 당시 진행 기록이다. 현재의 실행 지침은 이 문서와 [인증 문서](authentication.md)를 따른다. 개별 라우터의 미연결 훅은 여전히 503이지만 기본 앱이 실제 identity 의존성을 연결한다.

## 자동 재현

저장소 루트 PowerShell, Python 3.12, Docker에서 실행한다. 기존 개발·운영 DB와 분리된 새 컨테이너를 사용한다. 아래 비밀번호는 이 로컬 테스트 컨테이너 전용이다. 동일 이름의 컨테이너가 이미 있으면 새 이름/빈 포트로 바꾸거나 자신이 만든 테스트 컨테이너만 재사용한다.

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
docker run --detach --name chatkit-first-answer-test --publish 127.0.0.1:55439:5432 --env POSTGRES_USER=chatkit_test --env POSTGRES_PASSWORD=isolated_test_only --env POSTGRES_DB=chatkit_first_answer_test pgvector/pgvector:pg17
docker exec chatkit-first-answer-test pg_isready -U chatkit_test -d chatkit_first_answer_test
# accepting connections 확인 후:
$env:PYTHONPATH='apps/api'
$env:PYTHONIOENCODING='utf-8'
$env:TEST_DATABASE_URL='postgresql+asyncpg://chatkit_test:isolated_test_only@127.0.0.1:55439/chatkit_first_answer_test'
$env:TEST_AUTH_DATABASE_URL=$env:TEST_DATABASE_URL
$runId=[guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe -m pytest apps/api/tests/test_first_answer_integration.py -q -rs --basetemp="tmp/fa-$runId"
```

테스트는 `.env`를 읽지 않고 임시 인증 키와 HTTPS/Secure 쿠키 설정을 주입한다. `TEST_DATABASE_URL`의 DB 이름에 `test`가 있어야 한다. 공통 `db` fixture가 UUID 스키마에 모든 ORM 테이블을 생성하고 테스트 종료 시 그 스키마만 삭제한다. 기본 앱의 실제 엔진 생성 함수에는 해당 스키마의 `search_path`만 추가하며, 인증·저장소·오케스트레이터·트랜잭션은 교체하지 않는다. 앱 lifespan도 실제로 실행해 세션 팩토리, 인증 서비스, 공급자 어댑터, 복구 supervisor를 조립/종료한다. 각 테스트에서 앱 연결의 `current_schema()`를 확인한다.

`TEST_DATABASE_URL` 없이 실행하면 저장소 관례에 따라 DB 테스트가 skip된다. 그 결과는 통합 검증 성공이 아니다. 첫 답변 파일의 완료 기준은 **10 passed, 0 failed, 0 skipped**다.

전체 회귀 재현:

```powershell
# 실제 외부 서비스 검사는 별도 opt-in이다. 실제 공급자 키를 넣지 않는다.
Remove-Item Env:VOYAGE_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:RUN_ASSET_STORAGE_S3_INTEGRATION -ErrorAction SilentlyContinue
Remove-Item Env:TEST_MAILPIT_HTTP_URL -ErrorAction SilentlyContinue
$runId=[guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe -m pytest apps/api/tests -q -rs --basetemp="tmp/fa-$runId"
docker stop chatkit-first-answer-test
```

테스트별 스키마는 정리되며 컨테이너는 중지 후 재사용할 수 있다. 위 명령은 기존 Compose DB/볼륨을 초기화하거나 삭제하지 않는다. 공통 DB fixture는 ORM 스키마로 검사하고, 전체 회귀의 migration 테스트는 별도 스키마에서 Alembic/초기 SQL 및 기존 데이터 보존을 확인한다.

## 직접 준비하는 데이터와 외부 경계

직접 INSERT하는 선행 데이터는 공개 생성 API가 없는 `providers` 1행과 `models` 1행뿐이다. `first_answer_app` fixture 안에서 현재 테스트 스키마에 넣는다.

| 데이터 | 테스트 값/이유 |
|---|---|
| Provider | `name=openai`, 활성. 모델 실행 공급자를 결정하는 시스템 설정 |
| Model | `model_name=gpt-test`, 활성, `context_window=32000`, `reasoning_efforts=[low]`, `model_family=test`, input/output price=1. 상품 설정·발행·실행 모델 검증에 필요하며 실제 공급자 모델명이 아니다 |
| 사용자·세션·메일 증명 | 직접 INSERT 없음. 회원가입/검증/로그인 API로 생성 |
| 캐릭터·로어북·시작 항목·상품·발행본 | 직접 INSERT 없음. 소유자 공개 API로 생성 |
| 대화·메시지·생성·usage·memory 작업 | 직접 INSERT 없음. 실제 유스케이스에서 저장 |

메일은 기존 `SMTPMailSender.send_mail` 경계에서 `RecordingMailer`로 전달을 기록하고 인증 링크 fragment의 토큰을 가져온다. 토큰 생성/해시 저장/만료/일회 사용 검증은 실제 구현이다. 토큰 반환 API를 추가하지 않았다. 미인증 로그인 거절과 인증 토큰 재사용 거절도 확인한다.

LLM은 `OpenAI AsyncResponses.create`만 결정적인 결과(한국어 답변, input=100/output=30 tokens)로 대체한다. 실제 OpenAI 어댑터의 입력 변환·결과 파싱, LLM 서비스, 프롬프트, 답변 예약/staging/완료, billing과 memory 저장을 통과한다. Voyage SDK의 `AsyncClient.embed`에도 결정적인 대역을 설치한다. 첫 대화에는 검색할 기억이 없으므로 실제 memory 조회가 임베딩을 생략하며 호출 0회를 검증한다. 이 테스트로 벡터 검색이나 memory worker 실행까지 검증했다고 해석하지 않는다.

상품은 신규 사용자의 **비공개 소유 상품**으로 발행한다. 소유자는 기존 정책상 사용할 수 있으므로 승인 상태를 직접 바꾸거나 관리자 권한을 부여하지 않는다. 다른 사용자의 상품 조회와 해당 상품으로 대화 시작은 404로 거절되는지 검사한다. 다른 사람이 만든 상품을 사용하려면 기존 `approved` + `public/unlisted` 정책을 충족해야 하며 이번 작업은 검수/관리자 연결을 확장하지 않는다.

## HTTP 단계별 재현

실제 서버로 수동 실행할 경우 [인증 실행 설정](authentication.md)의 DB/SMTP/키/asset 설정을 먼저 준비하고 기본 `app.main:app`을 시작한다. 기존 마이그레이션 절차를 따르며 운영 DB를 초기화하지 않는다. 사용 가능한 서버 모델 ID는 운영자가 미리 설정해야 한다. 아래 `MODEL_ID`는 그 ID이며, 위 자동 테스트에서는 fixture의 임시 ID를 사용한다. 자동 테스트의 SDK mock은 테스트 프로세스에서만 적용된다. 서버에서 실제 모델을 선택하면 실제 공급자 호출이므로 이번 검증 결과와 별개다.

모든 요청은 같은 쿠키 저장소를 사용한다. POST/PUT/DELETE에는 `Origin: AUTH_PUBLIC_ORIGIN`, `X-CSRF-Token: GET /auth/csrf에서 받은 값`, `Content-Type: application/json`을 보낸다. GET에도 로그인 쿠키를 전송한다. Bearer나 임의 owner ID를 보내지 않는다.

| 순서 | 요청 및 본문 | 결과/다음 입력 |
|---|---|---|
| 1 | `GET /auth/csrf` | JSON `csrf_token`과 CSRF 쿠키 보관 |
| 2 | `POST /auth/register` `{email,password}` | 202. 비밀번호 12~128자. 아직 로그인 불가 |
| 3 | 메일 수신 링크의 `#token=...` 확인 후 `POST /auth/email/verify` `{token}` | 200, `email_verified=true`. Mailpit 또는 테스트 기록 메일 사용 |
| 4 | `POST /auth/login` `{email,password}` | 200, Access/Refresh 쿠키. `GET /auth/me`로 확인 |
| 5 | `POST /characters` `{"name":"길잡이","persona_prompt":"친절하게 여행을 안내한다."}` | 201, `character.id` → C |
| 6 | `POST /lorebooks` `{"title":"출발 설정"}` | 201, `lorebook.id` → B |
| 7 | `POST /lorebooks/entries` `{"lorebook_id":"B","title":"광장","content":"여행자가 광장에서 길잡이를 만난다.","entry_type":"start_set"}` | 201, `entry.id` → E. 시작 항목 제목을 명시 |
| 8 | `POST /products` `{"title":"첫 여행","opening_message":"어서 와요, 여행자님."}` | 201, `id` → P. 기본 private/draft 유지 |
| 9 | `PUT /products/P/composition` `{"characters":[{"character_id":"C","is_primary":true}],"lorebooks":[{"lorebook_id":"B","role":"main"}]}` | 200 |
| 10 | `PUT /products/P/settings` `{"model_id":"MODEL_ID","reasoning_effort":"low","start_entry_ids":["E"]}` | 200. 선택 모델이 low를 지원해야 함 |
| 11 | `POST /products/P/releases` `{"summary":"첫 발행","body":"여행 시작"}` | 201, 발행 snapshot ID |
| 12 | `GET /products/P` | `start_options[0].id` → S. 원본 E와 다른 발행 시작 ID |
| 13 | `POST /conversations` `{"product_id":"P","start_set_id":"S"}` | 201, `id` → CID |
| 14 | `GET /conversations/CID/messages` | 첫 인사 메시지의 `product_character_id` → PC. 원본 C와 다른 발행 참여 슬롯 ID |
| 15 | `POST /conversations/CID/messages` `{"request_key":"input-1","content":"어디로 갈까요?"}` | 201, `id` → M, `revision` → R |
| 16 | `POST /conversations/CID/answers` `{"request_key":"answer-1","input_message_id":"M","expected_revision":R,"product_character_id":"PC"}` | 200, `status=succeeded`, 답변/생성 ID |
| 17 | 같은 answers 요청 재전송 후 `GET /conversations/CID/messages` | 기존 답변 반환, 인사·사용자 입력·AI 답변 3개. `GET /conversations/CID/updates`도 가능 |

대화 조회는 현재 공개된 messages/updates API를 사용한다. 별도 `GET /conversations/{id}`를 새로 만들지 않았다. 시작 인사는 작성자가 제공한 `generated_by_ai=false` 메시지이고 실제 첫 생성 답변만 true다.

## 검증 결과

Windows/Python 3.12, 독립 `pgvector/pgvector:pg17` 컨테이너에서 실행했다.

| 검사 | 결과 |
|---|---|
| 신규 통합 파일 | 10 passed, 0 failed, 0 skipped |
| 전체 `apps/api/tests` | 444 passed, 0 failed, 4 skipped (74.66초) |
| DB 테스트 skip | 0 |
| 기본 Ruff: `ruff check apps/api/app apps/api/tests/test_first_answer_integration.py` | 통과 |
| 신규 테스트 확장 Ruff `--select E,F,I` 및 `ruff format --check` | 통과 |
| 전체 app mypy | 실패: 기존 6개 파일에서 32개 오류 |
| 전체 app 확장 Ruff `--select E,F,I` | 실패: 기존 E501 줄 길이 232개 |

전체 회귀는 인증/세션 경쟁·마이그레이션, 상품 발행/권한, 메시지, 답변 중복·실패·복구, usage, memory, 아키텍처 계약을 포함한다. skip 4개는 실 S3 2개, 실제 Mailpit 1개, 실제 Voyage 1개다. 이번 메일 토큰 확보는 허용된 기록 메일 경계를 사용했으며 SMTP 수신 자체를 검증하지 않았다.

신규 검사는 fresh DB 세션으로 메시지·생성·usage의 사용자/대화/상품/발행본/모델/생성 ID 및 토큰 사용량 일치를 확인한다. 동일 키 완료 재전송 전후 답변 메시지/usage/생성은 각각 하나이고 LLM 호출도 1회, memory 예약 세대도 1이다. 입력 ID/revision/대상 캐릭터가 달라진 동일 키는 409다. 다른 실제 가입 사용자의 조회·버전 수정·메시지 수정/삭제/생성·답변 및 완료 결과 접근은 404다. 비로그인과 로그아웃 후 이전 쿠키의 매 요청 재사용은 401, CSRF 누락/불일치 및 외부 Origin은 403이며 거절 뒤 데이터 변화나 LLM 호출이 없다.

실행 코드의 연결 오류는 발견되지 않았다. 새 테스트의 초기 기대값 두 곳은 기존 계약에 맞췄다: 완료 생성의 lease 필드는 반드시 NULL이 되는 계약이 아니며, 무인증 쓰기도 먼저 CSRF를 검사하므로 인증 자체의 401 검사는 유효 CSRF와 로그인 쿠키 부재를 조합한다. 최종 테스트는 모두 통과했다. 과거 문서의 인증 미구현 설명을 관련 ARCHITECTURE에 정정했으며 모듈 책임/공개 인터페이스 변경은 없다. 기존 미추적 `references_document/`는 수정하지 않았다.

## 남은 정적 검사와 제한

현재 앱 소스 전체의 mypy 오류는 boto3/botocore 타입 정보 부재 4건, identity의 Optional 처리 4건, character 미디어의 Optional 처리 22건, HTTP 미디어 BinaryIO 타입 1건, main 예외 핸들러 타입 1건이다. 이번 변경에 실행 Python 소스 수정이 없으며 무관한 미디어 리팩터링이나 검사 옵션 완화로 감추지 않았다. 재현 명령:

```powershell
.venv/Scripts/python.exe -m mypy apps/api/app
.venv/Scripts/python.exe -m ruff check --select E,F,I apps/api/app --statistics
```

Docker 조회는 초기 샌드박스의 named pipe 접근 제한 때문에 실패했으나 승인된 Docker 실행 경로로 해결했고, 기존 DB 대신 새 컨테이너를 사용했다. Windows pytest 임시 디렉터리는 저장소 안의 짧고 새로운 `--basetemp` 경로를 사용했다.

실제 OpenAI/Anthropic/Voyage API, 운영 SMTP/HTTPS 프록시·브라우저, 프런트엔드, 스트리밍은 검증 범위 밖이다. billing은 기존 token/`cost_credit=0` 기록 계약을 검증했으며 실제 가격 계산·결제·잔액 차감은 구현하거나 검증하지 않았다. 커밋과 푸시는 수행하지 않았다.
