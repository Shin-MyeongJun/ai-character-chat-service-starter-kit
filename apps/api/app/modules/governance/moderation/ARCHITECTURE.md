# Moderation 모듈

모더레이터의 기존 콘텐츠 상태 변경 HTTP 경계와 내부 신고·평가·조치 요청을 담당한다.

- `character_router.py`, `lorebook_router.py`: 기존 `/characters/status`, `/lorebooks/status` 경로 및 moderation 의존성 가드.
- `mapper/character.py`, `mapper/lorebook.py`: 요청 → 대상 모듈 Command, Info → 공유 HTTP DTO.
- `schemas.py`: app/http/contracts의 동일 콘텐츠 DTO 정의를 참조한다.
- 원본 변경은 character/lorebook 공개 service에 위임하며 직접 저장소를 접근하지 않는다. 인가 JOIN 예외는 없다.

`moderation_flags`는 기존 데이터와 계약을 유지하는 legacy 영역이다. 기존 콘텐츠 상태 변경
라우터는 여전히 신고 기록을 자동 생성하지 않는다. 신규 신고 서비스는 review 테이블을
사용하고 수동 관리자 변경은 기존 `audit_logs`에 기록한다. 기존 owner_id 전달과
별도 moderation HTTP 가드는 보존하며 HTTP 인증·권한 정책 자체는 바꾸지 않았다.

관리자 조회와 모더레이터 변경은 접근 주체가 달라 별도 모듈에 두었다. 저장 로직을 복제하거나 빈 업무 계층을 추가하지 않았다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: character/lorebook_router → HTTP moderator dependency → mapper → content change_*_status → content repository. owner_id 이름은 이 경로에서 요청 행위자이며 상태 변경 서비스가 대상 소유자 조회와 동일한 정책을 적용한다고 가정하지 않는다.

현재 두 moderator dependency는 기본 503이며 main의 일반 authenticate 주입과 별도 연결이 필요하다. `test_content_actor_routes`는 거절된 가드가 변경 호출을 막는지 확인하고 실제 운영 인증 제공자는 검증하지 않는다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.

## 신고·평가·조치 DB (2026-10-14)

소유 테이블에 `moderation_reports`, `moderation_assessments`,
`moderation_assessment_reports`, `moderation_actions`를 추가했다. 모델은
`app/db/models/moderation_review.py`에 분리하고 기존 moderation.py의 공개
ModerationFlag/AuditLog와 두 테이블은 그대로 보존한다. 내부 서비스는 아래 계약으로
구현했으며 신규 HTTP API는 없다.

- reports는 접수 내용·증거 object·첨부 참조 array를 함께 저장한다.
- assessments는 자동/수동 평가 입력·정책 버전·결과·근거를 한 행에 저장한다.
- assessment_reports는 다대다 근거 연결과 신고별 disposition을 저장한다.
- actions는 평가별 여러 조치 요청과 적용 성공/실패를 저장한다.
- cases/evidence/decisions, 통계/outbox/이의신청 테이블은 만들지 않는다.

0027/초기 SQL 018은 기존 flags를 삭제하지 않고 같은 ID의 reports로 한 번 복사한다.
request_key는 기존 ID를 재사용한다. reason은 reason_detail로 보존하며 reason_code는
분류 정보가 없다는 뜻의 `legacy_unclassified`이다. reviewed/dismissed도 intake_status는
received로 복사하므로 신규 검토 대기열은 legacy provenance를 확인해야 한다.
원래 status/reviewed_by/reviewed_at은 evidence_snapshot.legacy_moderation_flag에
보존하며 실제 증거 확보 시각은 추정하지 않는다. 평가·정책·조치는 합성하지 않는다.
legacy와 신규 테이블 사이 자동 동기화는 없다. 후속 구현은 신규 쓰기 경로를 선택하고
추가 legacy 쓰기가 있었다면 별도 이관을 명시해야 한다. 신규 데이터가 있으면 downgrade를
거절한다. 기존 테이블 확장 대신 신규 테이블을 선택해 legacy 열·상태 계약을 보존했다.

### 후속 서비스 계약

- target_id, 당시 owner/snapshot, domain_action_id는 보존용 식별자이며 FK가 아니다.
  공개 도메인 서비스로 존재·소유권·신고 가능 범위와 버전 일치를 검증한다.
- reporter/evaluator FK는 사용자 삭제 시 SET NULL. 이력 간 FK는 RESTRICT이며
  사용자·작품 삭제로 신고·평가·조치를 연쇄 삭제하지 않는다.
- 연결된 신고와 평가의 대상 일치, 이전 평가와 대상 일치, 해제 대상 조치의
  대상/범위 일치 및 자기 참조의 간접 순환 금지는 서비스가 검증한다.
- request_key/evaluation_key/idempotency_key 충돌은 전체 입력 비교 후 재사용하거나
  거절한다. UNIQUE만으로 요청 내용 동일성이 보장되지는 않는다.
- 평가 재검토는 새 행과 supersedes 연결로 기록한다. DB UPDATE 금지 트리거는 없으며
  append-only는 서비스 계약이다. 신고 누적과 확정 위반을 분리하고 증거 부족을
  허위 신고로 바꾸지 않는다. form_elapsed_ms는 조작 가능한 참고 신호다.
- 평가 결과와 조치 적용은 구분한다. scope는 비어 있지 않은 코드이며 대상 도메인의
  허용 목록을 서비스가 검증한다. 실제 사용자/작품 제한은 각 도메인이 소유한다.
- 증거 JSON의 개인정보 최소화·보존기간·삭제와 검토자의 조회 인가는 후속 서비스 책임이다.
- audit_logs는 변경하지 않았다. 자동 행위자 지원은 후속 확장이다.

검증: test_moderation_review_schema의 고정 DDL/초기 SQL 일치 및 PostgreSQL 이관·제약·
다대다 연결 검사. TEST_DATABASE_URL 없으면 실제 DB 검사는 skip이며 성공으로 간주하지 않는다.

2026-10-14 실행: 신규 스키마 테스트, content_actor_routes, architecture_contracts,
product_migrations, credit_wallet_migrations 합계 14 passed / 6 skipped.
Docker 데몬 및 TEST_DATABASE_URL 부재로 실제 PostgreSQL 이관·제약·초기 설치 비교는
미실행이다. 오프라인 upgrade/downgrade SQL 생성과 DDL 일치 검사는 통과했다.

## 내부 업무 서비스 (2026-10-14)

빈 service.py/repository.py는 동일 이름의 패키지로 전환했다. 기존 검수 router/mapper의
import와 HTTP 계약은 변경하지 않았다. 신고·평가·조치의 변경 이유를 분리하고,
함께 사용하는 작은 저장소 연산은 repository/review.py에 유지했다. views/workflow는
추가하지 않았다. 추가·수정 함수에는 한국어 docstring을, 조율 순서에는 단계 주석을 둔다.

| 파일 | 공개 함수 / 책임 |
| --- | --- |
| types.py | Command, 별도 ActorCommand, Info, Cursor/PageInfo, ModerationError(code) |
| repository/review.py | 소유 테이블 조회·잠금·저장과 기존 수동 관리자 audit_logs 쓰기 |
| mapper/persistence.py | JSON 깊은 복사, Row/Entity→Info, 신고자 요약·페이지 변환 |
| service/command/reports.py | submit_report, change_report_intake |
| service/query/reports.py | get_own_report, list_own_reports, get_admin_report, list_admin_reports |
| service/command/assessments.py | record_manual_assessment, record_automatic_assessment(명시적 비활성) |
| service/query/assessments.py | get_assessment, list_assessments |
| service/command/actions.py | request_action, cancel_pending_action |
| service/query/actions.py | get_action, list_actions, list_retry_actions |
| service/util/validation.py | 내부 권한·입력·멱등 지문 검증 |

### 권한·접수·조회

- `actor=ActorCommand(user_id)`는 인증 경계가 검증된 사용자 ID로 생성한다. 자체 토큰
  인증을 대체하지 않는다. 매 호출에서 identity 공개 서비스로 최신 활성 상태를,
  관리 기능에서는 활성 admin 역할을 확인한다. moderator 별도 role은 현재 지원하지 않는다.
- 신규 접수는 user/product만 지원한다. user는 존재하는 ID만 확인하고 이메일·프로필을
  증거로 복사하지 않는다. product는 get_accessible_product(lock=True)와
  ensure_snapshot_available로 접근·발행·버전 소속·만료를 검사한다. 지정 버전이 없으면
  최초 실행의 최신 발행 버전을 선택한다. 서버 증거는 제목·설명·첫 대사·버전 식별자만
  확보한다. character/message는 기존 신고 이력의 조회·수동 평가만 가능하다.
- 신고 이유 코드는 비어 있지 않은 분류 코드이며 고정 분류 목록은 아직 정하지 않았다.
  legacy_unclassified는 신규 접수에서 거절한다. 첨부는 최대 10개 텍스트 참조 주장만
  받으며 reporter_claim 출처로 저장한다. 파일 조회·다운로드·업로드·저장소 인가는 없다.
- 신고자는 저장소 SQL에서도 본인 범위가 적용되고 ReportSummaryInfo만 받는다.
  증거·첨부·전적 신호·관리자 메모·다른 신고자의 ID는 반환하지 않는다.
- 관리자 목록은 legacy reviewed/dismissed를 기본 제외하고 명시 옵션으로 포함한다.
  본인 신고 내역에는 legacy 완료 건도 포함하고 legacy_review_status를 요약에 제공한다.
  실제 미평가 대기열은 intake_status=received 및 unassessed_only=True를 사용한다.
  평가된 신고의 접수 상태 변경은 거절한다. 접수 결과는 종결이며 되돌리기 API는 없다.
- 재전송은 SHA256 요청 지문을 evidence_snapshot.request_fingerprint에 보관한다.
  actor·신고자 제공 입력만 비교하고 서버 시각·실제 확보 버전·원본 변경은 제외한다.
  최초 신고 반환 시 대상의 새 접근 상태를 재검사하지 않지만 행위자 활성 상태는 검사한다.

### 평가·조치·상태 전이

- 수동 평가만 기록 가능하다. 입력은 근거 신고 1..100건, notes 최대 20건이다.
  신고 ID 중복/순서는 정규화하며 같은 ID의 상충 disposition은 거절한다.
  received 신고와 동일 대상만 허용하고 기간이 있으면 접수 시각의 [start,end)를 검사한다.
  legacy 완료 신고는 acknowledge_legacy_review=True로 명시 재검토한다.
- signals에는 검증한 근거 건수·현재 남아 있는 독립 신고자 수와 출처가 명시된
  관리자 관찰만 저장한다. 전적·임계치·신뢰도 공식을 만들지 않는다. confidence는
  관리자의 판단 값이며 자동 계산된 사실이 아니다. recommended_actions는 빈 목록이고
  구체적인 조치는 request_action으로 별도 요청한다.
- evaluation_key는 정규화 입력과 평가자의 지문을 signals에 저장해 충돌을 비교한다.
  재평가는 새 행으로만 추가한다. 같은 이전 평가를 대체하는 두 요청은 하나만 허용한다.
  초기 평가가 여러 개 존재하는 것은 가능하며 supersedes 연결로 재검토 계열을 표현한다.
- 자동 평가 실행 주체·정책이 없어 record_automatic_assessment는 DB 쓰기 없이
  automatic_assessment_disabled를 반환한다. enum/플래그로 우회할 수 없다.
- user scope는 login/publish, product scope는 product_access/publish다. warn/restrict/
  suspend/ban/revoke를 허용하되 ban은 user만, warn/ban/revoke는 ends_at 없이 요청한다.
  실제 적용 정책이 아니라 pending 요청의 최소 허용 계약이다. 일반 조치는 violation
  평가만 허용하고, 해제는 다른 outcome도 허용한다. 대체된 평가로 새 조치를 만들지 않는다.
- 조치 대상은 평가 대상 또는 작품의 현재 소유자 user만 가능하다. 소유자 관계는 product
  공개 서비스로 검증한다. 삭제된 작품의 소유자 관계는 검증할 수 없으므로 거절한다.
- revoke는 같은 대상·scope의 applied restrict/suspend/ban만 연결한다. 취소되지 않은
  해제 요청이 있으면 새 키로 중복 생성하지 않는다. 이 계층에는 applied를 만드는 함수가 없다.
- pending→cancelled만 수행하며 cancelled 재취소는 멱등이다. failed/applied 취소는
  거절한다. 같은 조치 키의 재호출은 현재 상태를 반환한다. 키 동일성에는 actor를 포함하지
  않지만 활성 관리자만 재사용할 수 있다. 조치 요청자·취소자는 audit_logs에 보존한다.

### 트랜잭션·동시성·후속 연결

- 모든 쓰기는 use_case_transaction을 소유/참여한다. 조회로 autobegin된 세션에서
  단독 쓰기를 이어가기 전에 호출자가 트랜잭션을 정리하거나 상위 유스케이스 범위를 열어야 한다.
- 멱등 키별 advisory lock을 사용한다. 접수 상태 그래프 편집과 평가 근거 확인은 공통
  intake graph 잠금, 재평가·조치는 대상별 잠금으로 직렬화한다. 커서는 실제 received_at/
  evaluated_at/created_at과 ID를 사용하며 페이지 크기는 1..100이다.
- 수동 관리자 변경의 audit_logs는 같은 트랜잭션에 기록한다. 증거·자유 서술을 audit에
  복제하지 않는다. 감사 기록 실패도 전체 쓰기를 롤백한다. 기존 감사 스키마의 관리자
  FK RESTRICT와 자동 행위자 미지원 계약은 유지한다.
- 오류 코드는 forbidden/not_found/invalid_input/idempotency_conflict/state_conflict/
  invalid_link/target_unavailable/target_unsupported 및 명시적 legacy/자동 제한으로 구분한다.
  HTTP 변환은 없다. SQLAlchemy 저장소 오류를 성공이나 임의 업무 오류로 숨기지 않는다.
- 후속 적용자는 pending/failed 요청을 대상 도메인에 같은 조치 ID로 멱등 적용하고
  domain_action_id·applied_at·실패 코드를 기록해야 한다. 외부 적용 후 결과 저장 실패 시
  대상 도메인 대사·재시도로 복구한다. 현재는 실제 제재·실행자·자동 정책·HTTP 연결이 없다.
- 전적의 종합 조회, 증거 보존기간/파기, 감사 로그 열람, 이의신청, 확정 통계도 후속 범위다.

검증 파일: test_moderation_services(대역 업무·권한·멱등·연결·커서 SQL·주석),
test_moderation_services_db(실제 DB 저장·동시 접수/재평가·작품 접근·legacy 목록),
test_moderation_review_schema(이관/제약/DDL). 대역 검증은 실제 DB 성공으로 간주하지 않는다.

내부 구현 후 전체 실행: `pytest apps/api/tests -q -p no:cacheprovider`는
447 passed / 261 skipped (2026-10-14). Ruff와 git diff --check 통과.
Docker 데몬이 없고 TEST_DATABASE_URL이 설정되지 않아 신규 서비스의 실제 DB 4개와
스키마 DB 2개를 포함한 DB/외부 환경 의존 검사는 미실행이다. 동시 접수·재평가,
실제 SQL 페이지·삭제 정책·Alembic 이관을 DB에서 검증 완료했다고 해석하지 않는다.
