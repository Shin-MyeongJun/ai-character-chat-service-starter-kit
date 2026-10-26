# 최종 채팅 답변 프롬프트 저장·관리자 조회

2026-10-21. 저장·원본 조회는 chatting/chat, 관리자 HTTP 조회는
reporting/operations_reporting 소유다. prompt는 순수 구성 모듈을 유지한다.

## 저장 및 실행 계약

`generation_prompts`는 `generation_id` PK/FK(CASCADE), `request_json` TEXT, UTF-8
`digest` SHA-256 소문자 hex, `created_at`, `format_version=1`, `provider`,
`max_output_tokens`를 저장한다. 모델 ID/이름/reasoning_effort는 기존 생성 기록의
당시 값이며 현재 모델 카탈로그 설정으로 대체하지 않는다. effort `none`은 기존처럼
LLM 서비스에 None으로 전달된다. 공급자 API 키·인증 헤더는 수집하거나 반환하지 않는다.

원문은 실제 `GenerateTextCommand.request_json`에 전달하는 최종 prompt 문자열 전체다.
system 지침, reference_data의 캐릭터/로어/기억, 역할별 대화 이력과 현재 입력을 포함하며
JSONB 재직렬화나 사후 원본 재구성을 하지 않는다. **공급자 어댑터 변환 전**의 중립 JSON
봉투이며 SDK가 전송한 HTTP 본문 전체를 기록한 것이 아니다.

생성·견적·크레딧 예약·메타데이터·원문 저장을 같은 트랜잭션에서 commit한 후 LLM을 호출한다.
저장 실패는 전체 rollback으로 예약/차감 없이 외부 호출을 차단한다. commit 응답 유실은
기존 요청 키 조회/복구로 처리하며 불확실한 실행을 다시 호출하지 않는다. 현재 생성 ID당
외부 실행권 하나이고, SDK 어댑터 추가 호출이나 lease 복구용 프롬프트 행을 만들지 않는다.
DB PK, 생성 잠금과 실행 token/lease/digest/설정 검사가 중복/덮어쓰기를 막는다.

실패/호출 전 중단/타임아웃에도 commit된 원문은 남는다. `prompt_recorded`는 **저장 사실**만
표현하며 전송 또는 응답 성공 상태가 아니다. 원문 없는 과거/준비 실패 생성은 그대로 둔다.
대화 편집·되돌리기/설정 변경으로 원문을 갱신하지 않는다. 기존 generation/usage/payment
삭제 제약은 유지하고, 의도적인 부모 generation 삭제 시에만 원문을 함께 제거한다.

## 관리자 HTTP 계약

활성 admin만 허용한다. 기존 인증 쿠키로 actor를 식별하고 identity에서 현재 상태/역할을
확인한다. 작가(작품 소유 일반 사용자 포함), 일반 사용자, moderator 및 비활성 admin은
403이다. 비인증은 기존 인증 오류 계약을 따른다. 성공 응답은 `Cache-Control: no-store`다.
이번 두 GET 외 기존 operations 집계 서비스는 계속 HTTP 미노출이다.

### 목록

```http
GET /admin/reporting/generation-prompts?date_from=2026-10-01&date_to=2026-10-21&status=failed&page=1&page_size=50
```

- `date_from`, `date_to`: 필수 서울 날짜 양 끝 포함, 최대 731일. 생성 `created_at` 기준.
- `conversation_id`: 선택 UUID, 해당 대화만 조회.
- `status`: 선택 pending/succeeded/failed/cancelled/stale.
- `page`: 1 이상, 기본 1. `page_size`: 1–100, 기본 50.
- 응답: `items`, `total`, `page`, `page_size`.
- 각 item: generation_id, conversation_id, model_id, model_name, reasoning_effort,
  status, created_at, finished_at, history_invalidated_at, prompt_recorded,
  prompt_created_at, provider. 원문과 digest, answer_metadata는 목록에 없다.

SQL에서 필터링 후 created_at/id 내림차순으로 offset pagination한다. count와 페이지는
별도 읽기이므로 동시 쓰기/페이지 이동 전체에 걸친 고정 스냅샷을 보장하지 않는다.

### 상세

```http
GET /admin/reporting/generation-prompts/00000000-0000-0000-0000-000000000001
```

응답은 `generation`(목록 item과 같은 메타데이터), `prompt`로 구성한다.
기록이 있으면 prompt는 `request_json`, `digest`, `format_version`, `created_at`,
`provider`, `max_output_tokens`를 반환한다. request_json은 JSON **문자열**이며 JSON 응답의
이스케이프를 해제한 UTF-8 문자열의 SHA-256이 digest다. 관리 클라이언트가 역할별 메시지를
표시하려면 해당 문자열을 JSON 파싱한다. digest 계산 전에 파싱/재직렬화하지 않는다.

생성은 존재하지만 기록이 없으면 200 + `generation.prompt_recorded=false`, `prompt=null`이다.
미기록 이유·실제 전송 여부를 추정하지 않는다. 생성 미존재는 404 `not_found`, 권한 부족은
403 `forbidden`, 기간/필터 오류는 422다. 실패 생성도 같은 경로로 조회한다.

일반 답변 DTO와 answer_metadata에 원문을 추가하지 않는다. 애플리케이션 로그/오류에는
원문을 출력하지 않고 기본 API SQL 엔진은 `hide_parameters=True`로 바인드 값도 숨긴다.
프로젝트에 관리자 reporting 화면이 없어 새 UI는 만들지 않았다. 작가용 부분 조회는
공개 범위와 시스템 지침 보호 정책을 별도 설계할 후속 과제다.

## 스키마 적용

기존 DB는 백업·검토 후 프로젝트 표준 Alembic `upgrade head`(0030)를 적용한다.
새 DB는 `infra/postgres/init/020_generation_prompts.sql`까지 초기화한다. 두 경로를 같은
DB에 중복 실행하지 않는다. backfill은 없고 원문 기록이 있으면 downgrade를 거절한다.
DBA 직접 UPDATE를 막는 트리거는 없으며 애플리케이션은 UPDATE 경로를 제공하지 않는다.

## 검증

테스트 명령은 저장소 루트의 PowerShell 기준이다.

```powershell
$env:PYTHONPATH='apps/api'
.venv/Scripts/python.exe -m pytest apps/api/tests/test_generation_prompt_http.py apps/api/tests/test_generation_prompt_commands.py apps/api/tests/test_generation_prompt_workflow.py apps/api/tests/test_generation_prompt_migrations.py apps/api/tests/test_generation_prompts_db.py apps/api/tests/test_architecture_contracts.py apps/api/tests/test_reporting.py -q -p no:cacheprovider
```

실 DB 검증에는 이름에 test가 포함된 pgvector PostgreSQL의 `TEST_DATABASE_URL`을 설정한다.
`test_product_migrations.py`는 전체 baseline→head / 초기 SQL / ORM 비교를 수행한다.
`test_nonstream_answers.py`, `test_answer_billing_integration.py`, `test_product_usage.py`는
기존 생성·결제·복구 회귀다. 실제 공급자 호출은 이 검증에 사용하지 않는다.

### 실제 실행 결과 (2026-10-21)

- 관리자 HTTP/인가/필터·페이지·상세/SQL projection/과거 미기록·미존재 구분: 17 passed.
- 저장 Command의 실제 검증과 mapper(저장소 대역 사용): 12 passed.
  UTF-8 digest·정확한 문자열·동일 재호출의 기존 시각 보존·다른 원문/실행 token/provider/
  출력 예산 거절·lease/terminal 상태 검사·원본 조회의 관리자 재검증을 확인했다.
- 실제 AnswerOrchestrator를 실행하고 트랜잭션/외부 경계를 대체한 순서 검사: 3 passed.
  원문과 LLM Command/digest 일치, 저장→예약 commit→호출 순서, 저장 실패의 rollback
  경계/호출 차단, commit 응답 유실 시 호출하지 않고 기존 요청 재조회/복구를 확인했다.
- DDL/ORM 구조와 고정 초기 SQL 일치 및 Alembic offline upgrade/downgrade guard: 2 passed.
- 관련 답변·결제·복구·LLM·API/아키텍처/reporting 회귀 묶음: 105 passed, 76 skipped.
  이후 추가한 저장 Command 테스트 12개도 별도로 통과했다. 위 테스트 수는 서로 중복되므로 합산하지 않는다.
- 최종 전체 백엔드: **529 passed, 4 failed, 290 skipped**. 이 기능 관련 실패는 없다.
  실패 4개는 이번에 수정하지 않은 상품/스튜디오 경로의 다음 테스트다.
  `test_product_catalog_page::test_catalog_title_and_description_come_from_published_snapshot`
  (fixture에 title 없음), `test_studio_draft_guard::test_edit_after_first_publication_does_not_change_product_visibility`
  (fixture에 product_id 없음), `test_studio_publication`의
  `test_same_revision_publication_retry_returns_saved_release` 및
  `test_initial_publication_uses_one_composed_transaction` (ProductQuery 별칭 없음).
  전체 회귀 통과로 표시하지 않고 해당 작업 중인 파일은 변경하지 않았다.
- 변경 Python의 Ruff F/I 및 신규 파일 format check 통과. API/DB/신규 문서 범위
  `git diff --check HEAD` 통과. 저장소 전체 diff check는 기존 web/.next-workflow-check
  생성물의 trailing whitespace 때문에 실패하므로 전체 통과라고 표시하지 않는다.

**실제 PostgreSQL 통합 검증은 미실행이다.** TEST_DATABASE_URL이 없고 Docker Desktop이
오래된 dockerInference 소켓 오류로 시작하지 못했다. 자동 승인 검토에서 프로세스/소켓
정리가 다른 작업을 중단할 수 있다는 이유로 거절되어 사용자에게 확인한 후 명시적 승인을
받아 정리를 시도했다. 프로세스는 종료했으나 소켓 삭제·이름 변경·reparse-point 전용
Windows API 접근이 모두 WinError 1920으로 실패했다. Docker 데이터/설정을 초기화하지 않았다.

신규 PostgreSQL 검사 11개(순서/정확한 원문, 결제 rollback, 동시 최초 요청과 재조회,
실패 생성 조회, reserved/calling/result_ready lease 복구, 덮어쓰기/UNIQUE/이력 변경,
실제 HTTP와 DB 역할 검사, FK/CASCADE, 실행 migration/downgrade 보호)는 작성·수집됐으나
skip되었다. 기존 전체 baseline→head/초기 SQL/ORM 일치와 생성·결제·복구의 실제 DB 회귀도
미검증이다. 저장소/트랜잭션 대역의 통과 결과를 실제 PostgreSQL의 commit·잠금·원자성
검증으로 해석하지 않는다. DB가 준비되면 위 신규 테스트와 기존 관련 DB 회귀를 실행해야 한다.
