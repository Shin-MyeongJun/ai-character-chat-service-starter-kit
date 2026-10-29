# Operations reporting

관리자 운영 조회의 독립 모듈이다. 사용자 reporting 결과를 재사용하지 않는다.
현재 위치는 `reporting/operations_reporting`이며 다른 reporting 영역과 공개 경계를 분리한다.

| 파일 | 책임 |
| --- | --- |
| types.py | 관리자 전용 작품 View, 기록된 전체 합계, 큐 현황 |
| service/views.py | get_product_report, get_recorded_service_report, get_statistics_queue_report |
| mapper/persistence.py | 허용 지표 선택·최신성·최신 요청 시각 경과 계산 |

## 구현 지표와 데이터 근거

- get_product_report: product.get_admin_reporting_statistics를 통해 비공개 작품도
  존재/버전 소속을 검증하고 기존 작품/버전 사용량을 조회한다.
- get_recorded_service_report: product.get_recorded_service_statistics의 기록된
  ProductDailyStats만 합산한다. 기간·작품을 가로질러 user 활동 ID를 DISTINCT로 세며
  버전 집계를 다시 더하지 않아 작품/버전 이중 계산을 피한다.
- 전체 합계의 coverage는 all_product_day_coverage_not_verified다. 기존 registry로
  모든 과거 작품-날짜 수집을 증명할 수 없으므로 확정 totals를 제공하지 않는다.
  기록 행이 없으면 recorded_totals=None, 행 수·작품 수와 pending 작업 수를 함께 반환한다.
- get_statistics_queue_report는 전체 dirty 작품-날짜 수와 min(requested_at)를 반환한다.
  재요청이 requested_at을 갱신하므로 경과 시간은 오래된 최신 요청의 나이이며
  최초 적체·최초 실패 이후 경과 시간이라고 주장하지 않는다.
- 활성 admin만 허용한다. moderator 별도 역할, 원본 수정·재집계·claim은 제공하지 않는다.
- 작품 지표 정의는 기존 product 집계 계약과 같다. finished_at 완료 상태, 생성 성공의
  원래 출력 메시지 수, usage.created_at 토큰/크레딧, 성공 생성 사용자 DISTINCT다.
- 오류 코드/지연·신고·크레딧 정합성 통계는 이번 제외다. 작은 공개 사실 조회를
  해당 원본 도메인에 마련한 뒤 추가한다. 매출/실PG·원가·이익도 제공하지 않는다.

## 커버리지와 최신성

- 누락 날짜의 metrics는 None이다. 기록된 부분 합계는 recorded_totals이며,
  모든 선택 날짜의 부모 집계가 있고 dirty 날짜가 없을 때만 totals를 제공한다.
- state는 empty/partial/pending/complete다. pending과 누락은 함께 존재할 수 있다.
  dirty 날짜의 기존 값은 stale일 수 있고 확정 합계에는 사용하지 않는다.
- 버전 행이 없어도 부모 작품 일별 집계가 있으면 해당 버전의 0을 확인할 수 있다.
  부모까지 없으면 0으로 채우지 않는다. 생성/발행 이전 날짜도 집계가 없으면
  보수적으로 missing으로 표시하고 활동 0으로 추정하지 않는다.
- oldest/newest_updated_at은 포함한 집계 행 갱신 시각의 범위다.
  newest 하나를 전체 기간 완료 시각으로 표시하지 않는다.
- partial/complete는 저장된 집계의 날짜 커버리지에 대한 설명이다. 상위 작업 누락·
  원본 삭제까지 검증한 완전한 역사나 지금 시점의 실시간 사실을 보장하지 않는다.

## 공통 조회 계약

- 소유 테이블과 repository는 없다. 기존 집계 조회는 HTTP에 노출하지 않으며,
  아래 최종 답변 프롬프트 조회 두 경로에 한해 HTTP schemas/router를 제공한다.
- service/views.py가 도메인 공개 service/types를 조합하고 mapper/persistence.py가
  허용 필드만 별도 View로 구성한다. 다른 reporting 영역의 service/types를 참조하지 않는다.
- ActorCommand는 인증 경계가 검증한 ID로 생성한다. 토큰 인증을 대신하지 않으며
  identity 공개 조회로 최신 상태/역할을 검사한다. is_admin 플래그는 받지 않는다.
- core/reporting.py는 순수 날짜·최신성 값/검증만 공유하고 영역 모듈에 의존하지 않는다.
- 서울 날짜 양 끝 포함, 최대 731일이며 원본 시각 범위는 UTC [start,end)다.
- 조회는 no_autoflush에서 수행한다. commit/flush/집계 요청/지갑 준비/큐 claim은 없다.
  앞서 열려 있는 쓰기 트랜잭션 자체를 읽기 전용으로 바꾸지는 않는다.
- 여러 SELECT 사이 전체 스냅샷 일치는 보장하지 않는다. consistency=separate_read_queries다.
  queried_at은 응답 조합 시각이며 데이터 수집 완료 시각이 아니다. 일관된 스냅샷이 필요하면
  호출자가 별도 읽기 전용 REPEATABLE READ 트랜잭션을 제공해야 한다.
- 권한은 forbidden, 접근 불가능한 작품·버전은 not_found, 잘못된 식별자는 invalid_input,
  날짜는 공통 ReportingError(invalid_period)다. 저장소 실패를 0/빈 성공으로 바꾸지 않는다.
- 함수에는 한국어 docstring을, 여러 서비스/집계 상태 조합에는 이유와 단계 주석을 둔다.
- 기존 집계의 HTTP·캐시·내보내기·실행 이미지/DB 계정 분리는 범위 밖이다. 코드 모듈 경계만으로
  관리자 데이터의 배포/DB 접근 격리를 완료했다고 주장하지 않는다.

## 위치와 검증 기록

modules 최상위의 독립 모듈로 두어 기존 모듈 소유 경계 검사에서도 각 영역이
별도 소유자로 인식되게 했다. reporting 하위의 한 모듈로 합치지 않았고,
공통 core는 날짜/최신성 값만 담당한다. 중복된 작은 결과 필드는 의도적인 노출 계약 분리다.

2026-10-15 전체 백엔드 회귀: 462 passed / 269 skipped.
Ruff와 git diff --check 통과. TEST_DATABASE_URL과 Docker 데몬 부재로
신규 reporting_db 4개 및 기존 product_statistics DB 3개를 포함한
DB/외부 환경 검증은 미실행이다. 실제 SQL 쓰기 금지·스코프·DISTINCT·서울 경계는
DB 테스트로 작성했으나 DB 검증 완료라고 표시하지 않는다.

## 관리자 최종 답변 프롬프트 조회 (2026-10-21)

이번 기능에 한해 기존 HTTP 미노출 계약을 확장한다. `router.py`, `schemas.py`,
`mapper/schema.py`는 `/admin/reporting/generation-prompts` 목록과 `/{generation_id}` 상세
GET만 제공한다. 기존 작품/전체/큐 reporting 서비스는 계속 미노출이다.

`service/prompts.py`는 인증된 ActorCommand를 identity로 활성 admin 재검증한 후
chat의 공개 `service/query/prompts.py`와 공개 types만 호출한다. chat repository/ORM 접근은 없다.
chat 자체도 관리자 역할을 재검증하며 저장·원본 조회의 소유자는 chat이다.
`mapper/prompts.py`는 허용 메타데이터와 원문을 운영 영역의 독립 View로 변환한다.

목록은 서울 날짜 양 끝 포함(최대 731일), conversation_id, status 및 page/page_size를 받는다.
created_at/id 내림차순, SQL 필터 후 offset pagination이며 목록에 원문·digest·answer_metadata를
반환하지 않는다. 상세는 실패 생성도 포함하고 저장 원문/digest/format_version/시각/provider/
출력 예산과 생성의 기존 model_id/model_name/reasoning_effort를 반환한다.
과거 원문 미기록은 200 + prompt:null, 생성 미존재 404, 권한 부족 403, 입력 오류 422다.
비인증은 기존 identity 계약을 따른다. 정상 응답은 Cache-Control: no-store다.

저장됨은 SDK HTTP 전송/성공을 증명하지 않는다. 별도의 전송 성공 상태를 만들지 않는다.
API 키/인증 헤더를 수집하지 않으며, 일반 사용자·작가에게 조회 경로를 제공하지 않는다.
작가 부분 조회는 후속 정책 설계 과제로만 남긴다. 기존 관리자 reporting 프런트엔드가 없어
이번에는 백엔드까지만 제공한다. 기간/페이지 중 쓰기가 발생하면 total과 페이지 간 결과가
달라질 수 있으며 일관된 과거 스냅샷이라고 주장하지 않는다.

공개 함수의 이름/인가/예제와 현재 검증 결과는
[프롬프트 조회 계약](../../../../../../docs/generation-prompts.md)에 기록한다.

## 타입·패턴 검증 경계 (2026-10-28)

- service의 AsyncSession·이 영역 Command·ActorCommand와 product/chat 공개 Info를
  mapper의 구체 입력·반환에 연결했다. 기간은 PeriodInfo, 조합 시각은 datetime이다.
- 작품/서비스/큐 mapper는 nullable 합계·요청 시각과 일별 tuple 요소 타입을 보존한다.
  지표를 명시적으로 선택하며 기간 DISTINCT 재합산이나 coverage 확대를 하지 않는다.
- 프롬프트 mapper는 chat 공개 summary/page/detail Info에서 독립 운영 View로,
  schema mapper는 구체 RequestDto → Command와 View → ResponseDto로 변환한다.
  목록은 메타데이터만 선택하며 상세 prompt=None과 생성 미존재 오류를 구분한다.
- HTTP 반환 주석은 기존 명시 response_model DTO와 동일하다. 경로·DTO·필드·오류 변환은
  유지했으며 변경 전후 이 라우터의 전체 OpenAPI JSON SHA-256이 동일함을 확인했다.
- 상태 문자열·생성자·영역 간 공개 경계는 유지한다. 새 공통 계층이나 파일 분리 없이
  기존 책임을 유지하며 전체 모듈 디렉터리를 직접 Ruff format/check 및 mypy로 검사한다.

이번 범위 검증: 세 모듈과 reporting 전용 회귀 및 프롬프트 HTTP/Command 검증은
70 passed / 14 skipped였다. TEST_DATABASE_URL을 제거해 reporting DB 4건과
프롬프트 DB 10건은 미검증이며 통과에 포함하지 않는다. DB migration/초기화/삭제 및
외부 모델 호출은 수행하지 않았다. 필수 check_backend_quality.py는 샌드박스의
임시 디렉터리 권한 문제를 피해 재실행해 통과했다. 공용 기준선/검사 범위 파일은
이 작업에서 수정하지 않았고, 엄격 범위 편입은 주 대화의 통합 작업으로 남긴다.
