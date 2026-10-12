# Account reporting

본인 사용 통계만 조합하는 독립 모듈이다. 계정·지갑 관리 기능은 소유하지 않는다.

| 파일 | 책임 |
| --- | --- |
| types.py | ActorCommand, GetAccountReportCommand, 본인 생성/usage 결과 |
| service/views.py | get_account_report, 활성 사용자 검증과 chat/billing 공개 조회 |
| mapper/persistence.py | 생성 상태와 별도 사용량 기록의 순수 조합 |

## 구현 지표와 데이터 근거

| 지표 | 구현/정의 |
| --- | --- |
| 생성 pending/succeeded/failed/cancelled/stale | chat.get_account_generation_statistics 공개 조회 추가. user_id SQL 스코프 및 예약 created_at 코호트의 현재 상태 |
| 입력/출력 토큰·기록된 청구 크레딧·usage 행 수 | billing.get_account_usage_statistics 공개 조회 추가. UsageLog.created_at 범위. legacy 행도 기록된 값만 포함 |
| 작품별 본인 사용량 | 이번 제외. 기간/작품별 제한된 사실 조회 계약을 추가해야 함 |
| 현재 잔액·가용/예약 금액 | credit 업무 조회 유지. 통계로 대체하지 않음 |
| 공급자 전체 비용·실결제 | 실패/요약/임베딩 및 PG 기록 부족으로 제외 |

- source 조회는 SQL에서 user_id를 제한한다. Command에는 조회할 다른 사용자 ID가 없다.
- 생성이 기간 안에 예약되고 다음 기간에 완료되면 생성 상태와 usage 기간이 다를 수 있다.
  성공 생성 수=usage 행 수를 가정하지 않는다. 생성 상태는 조회 시점에 변할 수 있다.
- usage는 저장된 토큰/청구 값만이며 실패 호출까지 포함한 공급자 전체 사용량이 아니다.
  recorded_cost_credit는 기록된 CREDIT 청구 합계이며 원장 잔액·환불 후 순소비·매출이 아니다.
- state=empty는 두 원본에서 기록이 없다는 뜻이다. 집계 지연의 의미로 쓰지 않는다.
- 다른 이용자·관리자·공급자 정보와 대화 내용·오류 상세는 반환하지 않는다.
- 원본 삭제/보존 정책에 따라 과거 값 재현에 제한이 있다. 실시간 계측 통계는 아니다.

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
