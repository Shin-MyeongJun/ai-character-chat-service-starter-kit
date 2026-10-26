# Creator reporting

소유 작품의 기존 집계를 제공하는 독립 모듈이다. 창작/작품 변경 기능은 소유하지 않는다.
2026-10-21: 현재 위치 `reporting/creator_reporting`에 맞춰 내부 import를 갱신했다.
작가용 프롬프트 조회는 구현하지 않으며 부분 조회 정책은 후속 과제로 남긴다.

| 파일 | 책임 |
| --- | --- |
| types.py | ActorCommand, GetCreatorProductReportCommand, 작가 전용 지표·일별 View |
| service/views.py | get_product_report, 활성 사용자 확인과 product 소유자 공개 조회 |
| mapper/persistence.py | 작품 사용량/최신성의 작가 전용 타입 구성 |

## 구현 지표와 데이터 근거

기존 product 집계로 작품/버전별 일별·기간 사용량을 제공한다.
active_users는 성공 생성 사용자의 기간 DISTINCT이며 일별 합이 아니다.
succeeded/failed/cancelled/stale는 finished_at 기준의 완료 생성 상태 건수다.
messages는 성공 생성이 기록한 원래 출력 메시지 수로 현재 DB 메시지 수/사용자 입력 수가 아니다.
conversations는 해당 버전으로 생성한 방 수, transitions는 해당 버전으로 전환한 건수다.
input/output_tokens·cost_credit는 usage.created_at 기준 저장 값이다.
생성 시도 전체나 pending 생성은 기존 작품 집계에 포함하지 않는다.

- product.get_owner_reporting_statistics 공개 조회를 재사용한다. DB의 현재 소유권과
  발행 버전의 작품 소속을 확인하며 비소유자는 공개 작품이라도 통계에 접근할 수 없다.
- 기존 get_statistics 반환 계약은 바꾸지 않고 읽기 전용 공개 조회를 추가했다.
- raw 이용자 ID·대화·개별 결제·매출/환불·원가·내부 태그·신고·관리자 메모는 반환하지 않는다.
- 세부 이용자 코호트를 만들지 않는다. 소수 집계 숨김 정책/임계값은 임의로 정하지 않았다.

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

- 소유 테이블은 없다. repository/HTTP schemas/router를 만들지 않는다.
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
- HTTP·캐시·내보내기·실행 이미지/DB 계정 분리는 이번 범위 밖이다. 코드 모듈 경계만으로
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
