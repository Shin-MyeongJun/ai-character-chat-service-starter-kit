# 통합 검증·배포 준비 점검

검토일: 2026-11-02 (Asia/Seoul). 대상은 기존 미커밋 변경을 포함한 현재 작업 트리다.
PG는 PostgreSQL을 뜻한다. 결제 게이트웨이 실결제 검증은 수행하지 않았다.

**판정: 로컬 통합 검증 후 스테이징 검증으로 진행할 수 있다. 운영 배포 완료 판정은 보류한다.**
실제 외부 공급자/S3와 운영 HTTPS·쿠키·proxy·서비스 감독/알림, 사용자 웹의 인증부터
발행·답변까지 실제 API 브라우저 E2E는 남아 있다. U19 이미지 전반 재설계와 U28 업로드
잠금·전체 deadline 잔여 범위도 완료로 바꾸지 않는다.

## 실행 결과

| 검사 | 최신 결과 | 검증 범위 |
| --- | --- | --- |
| 전체 API 오프라인 | **1706 passed / 446 skipped / 0 failed**, 경고 2개 | 공급자 키·두 테스트 DB URL 제거, 2152개 수집 |
| 전체 API + 실제 PG + Mailpit | **2149 passed / 3 skipped / 0 failed**, 경고 22개, 330.09초 | 전용 localhost 감사/인증 DB, 실행별 UUID 스키마 |
| backend quality | **통과** | 패턴 진단/예외 0, Ruff 388파일, mypy 367소스, 아키텍처/검사기 13 passed |
| 지갑 migration 지정 회귀 | **3 passed**, 경고 2개 | 온라인 Alembic·init·ORM의 지갑 제약/기본값/인덱스·실제 지급/예약/확정·rollback |
| 웹·관리자 node 계약 검사 | **81 passed / 0 skipped** | 사용자 웹 72개 + 관리자 9개, fetch/hook 대역 포함 |
| 웹·관리자 TypeScript | 양쪽 통과 | 실제 프로젝트 tsc |
| 웹·관리자 production build | 양쪽 통과 | 실제 Next.js build |
| 관리자 Edge 브라우저 | **26 passed**, uncaught error 0 | 실제 Next dev + 합성 HTTP API, 실제 인증 DB E2E와 구별 |
| 사용자 Edge production 렌더 | **20 passed**, uncaught error 0 | 10경로 × 1440/390px, HTTP 200·가로 넘침 없음; 실제 backend 연결 없음 |
| 로컬 실제 SMTP | **1 passed** | 임의 테스트 주소의 인증·재설정 링크 발송/사용, 기존 메일 삭제 없음 |
| 별도 온라인 migration/초기 SQL | head **0036**, **76테이블** 일치 | 온라인 upgrade head + 재실행, 열/타입/NULL/FK/UNIQUE 비교 |
| CHECK/인덱스 추가 비교 | 구조 동일, 이름 차이 1곳 | payments UNIQUE의 이름만 다름, 아래 설명 |
| migration 후 빈 큐 실행 | 4개 CLI 성공 | memory/mail --once, 통계 --limit 1, auth cleanup; 모든 임시 스키마 정리 |
| OpenAPI·ORM 계약 | 이전 U27 해시와 일치 | 84경로·114연산, ORM 76테이블, 모델 export 58개, 진입점 8개 import |

각 실행은 중복 테스트를 포함하므로 통과 수를 합산하지 않는다. 오프라인의 DB skip은
실제 PG 실행에서 실행된다. Mailpit 지정 1건 역시 전체 PG 실행에 포함되므로 중복 합산하지 않는다.
SQL 경합 테스트 통과를 모든 스케줄·격리 수준·운영 부하의 교착 부재로 확대하지 않는다.
최종 PG의 skip 3건은 실제 S3 2건과 live Voyage 1건이다. 경고 22개는 Alembic 설정의
path_separator 20개와 기존 Starlette 422 명칭 2개다.

## 발견·수정 및 남은 차이

1. **지갑 온라인 migration 테스트 수정.** 최초 전체 PG는 2147 passed / 1 failed /
   4 skipped였다. 실패는 전용 최소 권한 계정에 없는 CREATE DATABASE 요구였다.
   해당 테스트는 head 기대값도 0031로 고정하고 있었다. UUID 스키마 2개를 생성하고
   Alembic의 실제 온라인 env/upgrade를 실행하도록 바꿨다. 현재 단일 head를 조회하고,
   기존 모든 지갑 schema signature와 실제 지급·예약·확정·잔액 검증을 유지했다.
   실패 시에도 연결·스키마를 정리한다. DB 권한 확대·skip 추가·업무 코드 변경은 없다.
   전체 재실행 뒤 public의 기존 version table 재사용 방지도 보강하고 해당 3건을 다시
   통과시켰다. 전체 테스트 수는 그대로이며 업무 동작 변경은 없다.
2. **migration 경로의 이름 차이.** 초기 SQL 002의 payments.pg_transaction_id는
   익명 UNIQUE여서 `payments_pg_transaction_id_key`이고, Alembic baseline/ORM은
   `uq_payments_pg_transaction_id`다. 같은 열의 같은 UNIQUE이며 CHECK/인덱스 구조에
   추가 차이는 없었다. 기존 DB와 초기 SQL의 DDL은 이번에 변경하지 않았다.
   향후 제약을 이름으로 변경/삭제하는 migration에서는 두 경로를 고려해야 한다.
3. **감사 문서 정합성.** 공통 요약표에 과거 미수정으로 남은 U01~U16/U22/U23/U29와
   U27 후속 정리를 반영하고 역사 기록을 구분했다. 누락된 U05 기록을 현재 코드·
   실행 근거로 보완했다. 과거 구현자의 미기록 성능 수치를 새로 만들어 쓰지 않았다.
4. **운영 절차 연결.** [운영 절차](operations-runbook.md)에 stop/drain → migration →
   같은 버전 기동, 상시 worker·예약 작업, 큐 관측과 downgrade 거절 대응을 연결했다.
   Compose가 API/worker 전체 배포·스케줄러·외부 알림을 제공하지 않는 점을 명시했다.

새 migration, 운영 DB 변경, 인프라/서비스 등록, 실제 결제·외부 AI/S3 요청,
commit/push·배포는 실행하지 않았다. 기존 작업 트리 변경은 보존했다.

## migration·감사·worker 확인

- Alembic은 단일 연쇄의 head **0036**이다. 새 DB 초기 SQL 끝은 **026**이며 두 경로의
  76테이블 스키마 비교가 성공했다. create_all만 통과한 결과와 구별한다.
- 0033 이력 trigger, 0035 pending 부분 인덱스, 0036 복구 횟수·감사 테이블과 downgrade
  거절은 기존 PG 회귀에 포함된다. 실제 운영 DB 이관/백업 복구는 수행하지 않았다.
- 복구 동시 선점, 횟수/대기/격리, 수동 operator/reason 감사, commit 응답 유실 후 terminal
  확인, 과금/메시지/기억 단일 반영을 테스트한다. `failure_class IS NULL`인 감사 행만으로
  성공을 판단하지 않는다. 테스트의 예외 주입은 실제 네트워크 단절 검증과 구별한다.
- mail worker는 API와 별개 상시 프로세스다. SMTP 성공은 최종 수신함 도착 보장이 아니며
  lease 만료·ack 유실로 동일 링크 중복이 가능하다. outbox 결과는 증명 정리 시 삭제되므로
  장기 운영 감사·지표 보존은 별도다.
- memory worker timeout 240초 < lease 300초, claim token과 새 실행의 상태 덮어쓰기 거절,
  후속 작업 drain과 실패/종료 자원 정리를 기존 회귀에서 확인했다. 빈 migrated schema의
  CLI 실행은 provider를 호출하지 않는 시작/종료 확인이다.

## 재현 및 증거

프로젝트 가상환경 Python을 사용한다. 실제 PG runner는 `.env.audit-test.local`의
허용된 localhost 테스트 DB/계정만 받고 외부 공급자 키를 제거한다. 비밀번호/URL은
결과 문서와 로그에 복사하지 않는다. 해당 비추적 설정은 새 clone에 포함되지 않는다.

```powershell
# 오프라인: 자식 실행 환경에서 DB/외부 공급자 설정 제거
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Remove-Item Env:TEST_DATABASE_URL,Env:TEST_AUTH_DATABASE_URL,Env:VOYAGE_API_KEY,Env:OPENAI_API_KEY,Env:ANTHROPIC_API_KEY,Env:RUN_ASSET_STORAGE_S3_INTEGRATION,Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m pytest -p pytest_asyncio.plugin -p anyio.pytest_plugin -p no:cacheprovider --basetemp=('tmp/dv-' + [guid]::NewGuid().ToString('N').Substring(0,8)) apps/api/tests -q -rs --tb=short

# 실제 PG + 로컬 Mailpit
$env:TEST_MAILPIT_HTTP_URL='http://127.0.0.1:8025'
$env:TEST_MAILPIT_SMTP_PORT='1025'
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests -p anyio.pytest_plugin

$env:PYTEST_ADDOPTS='--basetemp=tmp/dq-' + [guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe tools/check_backend_quality.py
node --test apps/web/tests/*.test.cjs apps/admin_web/tests/contracts.test.cjs
pnpm --dir apps/web typecheck
pnpm --dir apps/admin_web typecheck
pnpm --dir apps/web build
pnpm --dir apps/admin_web build
```

로컬 원시 로그·일회 검사 도구·브라우저 PNG는 `tmp/deployment-check-20261102/`에 보존한다.
이 폴더는 저장소의 기존 tmp 제외 정책을 따른다. 공유용 결과·소스 683파일 해시·로그
해시는 [기계 판독 결과](audits/2026-10-26-pattern-standardization/INTEGRATION-2026-11-02.json)에 저장했다.
핵심 로그:

- `api-offline-short.log`, `api-postgres-final.log`, `quality-final.log`, `wallet-migration-final.log`
- `web-contracts.log`, `web-typecheck.log`, `admin-typecheck.log`
- `web-build-approved.log`, `admin-build-approved.log`
- `browser-admin-approved.log`, `browser-admin/verification.json`, `web-smoke.json`, `mailpit.log`
- `worker-migration-smoke.log`, `contracts.log`

초기 환경 실패도 보존했다. Windows 샌드박스에서는 asyncio 초기화가 멈추고 빌드의
mkdir가 EPERM이었다. 같은 검사를 승인된 일반 실행 환경에서 재실행했다. 최초 오프라인의
저장소 22실패는 긴 basetemp의 Windows 경로 길이 제한으로, 제품 코드를 고치지 않고
짧은 새 경로로 전체 검사를 재실행해 모두 통과했다. 실패 로그를 최종 결과로 대체하지 않았다.
빌드가 생성한 next-env.d.ts 변경은 실행 전 상태로 복구했고, 임시 서버는 검증 후 종료한다.
최종 PostgreSQL 17.11 / READ COMMITTED에서 두 테스트 계정의 해당 임시 스키마 잔량은
각각 0개였고, 검사용 3181/3182/8180 포트도 모두 종료를 확인했다.

## 스테이징에서 확인할 항목

- 실제 사용자 웹 가입·메일 인증→스튜디오 저장/후속 발행→채팅→같은 키 재생과 계정 전환,
  관리자 역할 차단을 실제 API·DB·proxy에서 확인한다.
- HTTPS/Secure 쿠키·CSRF·Origin·refresh 회전/응답 유실·다중 탭/사용자 웹 동시 사용을 확인한다.
- 실제 공급자 모델·가격표, 임베딩 차원, S3 네트워크/자격·저장/읽기·취소를 확인한다.
- 배포 환경의 서비스 감독/스케줄러/알림, 백업 복원·업그레이드 유지보수 창을 검증한다.
- U19 설계와 U28 잔여 범위를 출시 요구사항과 대조해 별도 결정한다.

관련 기록: [공통 구현 감사](audits/2026-10-26-pattern-standardization/REPORT.md),
[원본 통합 감사의 최신 표](audits/2026-10-23-structural-review/REPORT.md),
[답변 복구 정책](../references_document/reference/answer-recovery-policy.md).
