# Gemini 검토에서 확인한 세 결함 수정

검증일: 2026-11-03. 기존 미커밋 변경을 유지한 현재 작업 트리에서 필요한 부분만 수정했다.
입력 보고서는 `tmp/gemini-report-review/REPORT.ko.md`이며 원본 재현 파일은 변경하지 않았다.

## 원인·수정·보존 계약

### 스튜디오 발행 설정 무시

문서 D → E → D 저장 뒤 문서 digest만 같은 것으로 판단해 새 모델·추론 설정과 메모 검증을
건너뛰고 이전 스냅샷에 새 영수증을 연결했다. `studio_publication.py`는 이제 새 요청의
메모를 먼저 검증하고, 같은 문서라면 product 공개 snapshot 조회로 **이전 불변 스냅샷의**
model.id/reasoning_effort까지 비교한다. 현재 상품의 가변 설정을 비교 근거로 사용하지 않는다.
설정이 다르거나 legacy snapshot에 비교할 모델 정보가 없으면 기존 정상 발행 경로를 실행한다.

기록된 동일 revision/fingerprint는 최신 초안·메모 검증보다 먼저 쓰기 없이 재생한다.
같은 revision의 다른 요청은 409다. 문서와 발행 설정이 모두 같은 새 revision은 기존처럼
스냅샷 생성을 생략하고 영수증만 기록한다. 이 경우 유효한 메모만 바꿔도 이전 release를
반환하는 기존 생략 정책은 유지하지만 공백 메모는 422다. legacy 매핑 채택·영수증 복구도
같은 불변 snapshot 비교를 적용한다. 저장 JSON·fingerprint 계산 형식은 바꾸지 않았다.
원본·설정·스냅샷·매핑·영수증은 기존 한 트랜잭션에서 확정하며 과거 snapshot은 수정하지 않는다.

### S3 종료 잠금 대기의 추가 worker 점유

read await가 취소돼도 실제 Body.read worker는 계속 실행한다. 기존 close는 다른 worker에서
같은 threading.Lock을 기다려 스트림 하나가 worker 두 개를 점유할 수 있었다.
별도 `_closing`으로 새 읽기 접수를 막고 **이미 접수한 읽기의 실제 worker 종료**와 결과/예외를
이벤트 루프에서 먼저 회수한 후 Body.close를 제출하도록 바꿨다. 아직 worker가 시작하지 않은
접수된 읽기도 허용한다. 실제 Body.read/close의 threading.Lock 직렬화는 유지한다.

AssetReadInfo가 소유하는 단일 close 태스크, 동시 close 대기, 반복 취소의 첫 취소 우선순위,
완료된 close 성공/실패의 재시도 금지, 기존 스트림 오류 우선순위는 변경하지 않았다.
추가 실행기·스레드·백그라운드 소유자는 없다. 진행 중 읽기는 여전히 worker 하나를 사용하고,
소켓 timeout은 전체 deadline이 아니며 close로 강제 중단하지 않는다.

### 태그 rename과 resolve의 교착

관리자가 잠근 beta를 alpha로 바꾸며 UNIQUE를 기다리는 동안 resolver가 삽입한 alpha를
보유하고 beta의 SHARE를 기다리면 이름순 정렬만으로 순환 대기를 끊지 못한다.
update/deactivate는 인가 후 행 잠금 전에 `LOCK TABLE tags IN EXCLUSIVE MODE NOWAIT`를
확보해 최상위 트랜잭션 종료까지 유지한다. resolve/create의 ROW EXCLUSIVE 및 ROW SHARE를
모두 차단한다. **NOWAIT가 핵심**이며 상위 트랜잭션이 먼저 잠근 행/쓰기와 500개 배치에 걸친
선행 잠금을 가진 상태에서도 새 테이블 잠금을 기다려 순환 대기에 들어가지 않는다.

55P03만 `ValueError("Tag dictionary is busy; retry the request.")`로 변환한다.
기존 HTTP 오류 경계에서 422가 된다. 실패한 트랜잭션을 재사용하거나 자동 재시도하지 않으며,
상위가 예외를 잡아도 use_case_transaction의 rollback-only가 전체 쓰기를 취소한다.
23505 이름 UNIQUE 충돌은 기존 오류를 유지한다. resolve/create 간 동시성·정확한 이름 UNIQUE,
trim/중복 제거/입력 반환 순서, 500개 배치, 기존 메타데이터, 비활성/retained_ids 정책은 보존한다.

## 실행한 검증

프로젝트 `.venv/Scripts/python.exe`를 사용했다. 실제 DB 검증은
`tools/run_postgres_audit_tests.py`가 허용하는 전용 localhost 감사 DB 두 개와 테스트별 UUID
임시 스키마를 사용했다. 실제 S3·LLM·운영 DB는 사용하지 않았다.

| 검사 | 결과 |
|---|---|
| 수정 전 원본 재현 두 파일 | 11 passed. 결함 존재 및 범위 제외 계약을 확인한 결과이며 수정 성공 근거가 아님 |
| 아래 관련 회귀 22개 파일 | **333 passed**, 59.34s, skip 없음 |
| 마지막 500개 선행 배치 취소 검증 보완 후 `test_u25_postgres_concurrency.py` | **17 passed**, 11.12s |
| 최종 명명/회귀 상태 비교 정리 후 발행 3개 파일 | **26 passed**, 6.97s |
| `python tools/check_backend_quality.py` 최종 실행 | 패턴 0 기존 진단/새 위반 없음, Ruff 388개 파일 통과, mypy 367개 소스 통과, 아키텍처/검사기 회귀 **13 passed** |
| 변경한 형식화 대상 회귀 파일 Ruff lint 및 변경 파일 diff 공백 검사 | 통과 |

처음 격리 환경에서는 asyncio 초기화가 진행되지 않아 해당 실행을 중단하고 같은 전용 DB
runner를 격리 밖에서 실행했다. 검증 실패를 통과로 계산하지 않았다. 첫 구현 회귀 실행의
179 passed / 3 failed는 새 테스트가 실제 컬럼 default_model_id 대신 model_id를 조회한
오류였으며 이를 바로잡은 뒤 위 333건 및 최종 26건으로 다시 검증했다.
타입 예외·baseline·검증 우회 옵션은 늘리지 않았다.

실행 명령:

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py -s tmp/gemini-report-review/test_review_probes.py tmp/gemini-report-review/test_postgres_probes.py

.venv/Scripts/python.exe tools/run_postgres_audit_tests.py `
  apps/api/tests/test_studio_publication.py `
  apps/api/tests/test_studio_republication_contracts.py `
  apps/api/tests/test_studio_publication_db.py `
  apps/api/tests/test_studio_settings_republication_db.py `
  apps/api/tests/test_tag_admin_locking_db.py `
  apps/api/tests/test_tag_resolve_batch_contracts.py `
  apps/api/tests/test_u25_postgres_concurrency.py `
  apps/api/tests/test_tag_management.py `
  apps/api/tests/test_tag_management_db.py `
  apps/api/tests/test_s3_reader_lifecycle.py `
  apps/api/tests/test_media_cancellation_contracts.py `
  apps/api/tests/test_use_case_transaction.py `
  apps/api/tests/test_studio_locking_db.py `
  apps/api/tests/test_studio_validation_contracts.py `
  apps/api/tests/test_studio_type_contracts.py `
  apps/api/tests/test_studio_draft_guard.py `
  apps/api/tests/test_product_studio_contracts.py `
  apps/api/tests/test_asset_storage.py `
  apps/api/tests/test_asset_storage_type_contracts.py `
  apps/api/tests/test_media_transport_contracts.py `
  apps/api/tests/test_tag_policy.py `
  apps/api/tests/test_tag_schema.py

.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_u25_postgres_concurrency.py
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_studio_publication.py apps/api/tests/test_studio_republication_contracts.py apps/api/tests/test_studio_settings_republication_db.py
.venv/Scripts/python.exe tools/check_backend_quality.py
```

원본 재현 명령은 **수정 전 결과**다. 원본 일부는 결함을 기대하므로 수정 후 통과를 기대하지 않는다.
333건은 모두 통과했으며 그중 태그 6건은 새 fence만 끈 이전 구현 대조군으로 40P01을 기대한다.
대응하는 수정 경로 6건은 2/501개 및 resolve/acquire/create 후 resolve에서 업무 충돌·전체
rollback 후 resolver 정상 완료를 검사한다. 별도로 caught-error rollback과 이름 UNIQUE도 검사한다.
기존 관리자 선행 rename/deactivate, 동시 create, 비활성 retained 정책, studio 교차 발행도 포함한다.

발행 HTTP/PG 회귀는 D → E → D 뒤 모델만/추론만/둘 다 변경, no-op/변경 요청의 공백 메모,
알 수 없는 모델·지원하지 않는 추론 거절, 영수증 저장 직후 실패 시 원본/설정/모든 snapshot/
매핑/영수증 복원, 동일 요청 재생·다른 요청 409·다음 초안 저장 후 재생 및 legacy 복구를 검사한다.
S3는 실제 worker/Event와 botocore StreamingBody로 정체 중 무관한 to_thread 완료,
이미 접수된 queued read 처리, read 실패 회수, 동시/반복 취소·close 실패·ASGI disconnect와
Uvicorn shutdown·자원 및 worker 회수를 검사한다.

## 남은 한계와 별도 개선 후보

- 관리자 태그 변경의 fence는 테이블 전체에 적용된다. 무관한 사전 writer가 있어도 즉시
  충돌할 수 있고 관리자 최상위 트랜잭션이 길면 writer가 기다린다. 일반 SELECT는 허용한다.
  재시도는 새로운 전체 업무 요청/트랜잭션이어야 하며 임의 상위 잠금 조합 전체의 교착 부재를
  주장하지 않는다.
- 실제 AWS·LLM·운영 부하·영구 소켓 정지는 검증하지 않았다. read가 끝나지 않으면 close도
  계속 기다리는 계약이며 전체 deadline/강제 소켓 종료 정책을 새로 추가하지 않았다.
- 메타데이터 오류 뒤 Body.close도 실패하면 원래 오류를 덮는 경계 조건은 별도 개선 후보다.
  이번 세 결함 수정과 섞지 않았다. DB rollback에 shield를 추가하지 않았고 ProtocolError를
  근거로 catch 범위를 넓히지 않았다.

## 변경 위치

- `apps/api/app/use_cases/studio_publication.py`, 같은 디렉터리 `ARCHITECTURE.md`
- `apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py`, 모듈 `ARCHITECTURE.md`
- `apps/api/app/modules/content/tag/repository.py`, `service/command.py`, 모듈 `ARCHITECTURE.md`
- 신규 회귀: `apps/api/tests/test_studio_settings_republication_db.py`, `test_tag_admin_locking_db.py`
- 기존 회귀 보완: `test_s3_reader_lifecycle.py`, `test_studio_publication.py`,
  `test_studio_republication_contracts.py`, `test_studio_publication_db.py`,
  `test_u25_postgres_concurrency.py`, `test_tag_management.py`

관련 책임은 기존 파일에 유지했다. snapshot 조회는 공개 product service, 잠금 SQL은 tag
repository, 잠금 실패의 업무 해석은 tag service, worker/reader 수명은 S3 adapter가 소유한다.
새 계층·모듈·스키마 변경은 필요하지 않았다.
