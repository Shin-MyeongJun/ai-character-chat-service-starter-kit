# U28 작업 기록 — 업로드 해싱 offload와 취소 시 파일 수명

작성일: 2026-11-02 (Asia/Seoul)

상태: **요청된 해싱 개선 구현·검증 완료.** 외부 저장 중 잠금 재설계는 별도 범위다.

## 변경과 보존 계약

`CharacterMediaService.reserve_upload`는 `_read_upload_fingerprint`를 기다린다.
이 내부 함수는 기존 `_fingerprint_upload`의 검증·seek/read·SHA-256 전체를 하나의
`asyncio.to_thread` 태스크로 실행하며, shield로 실제 종료까지 태스크를 소유한다.
파일 청크마다 별도 태스크를 만들거나 전체 파일을 추가 복제하지 않는다.

최초 호출자 취소를 보관하고 반복 취소에도 종료를 계속 기다린다. 작업 성공/실패를
회수한 뒤 같은 최초 CancelledError를 전달하므로, 이후 소유권 조회·예약 생성·저장으로
진행하지 않는다. 취소가 없으면 원래 결과 또는 동일한 I/O 예외를 전달한다.
HTTP 핸들러의 임시 파일 context는 서비스 반환 뒤 종료하며, 서비스는 입력 파일을
직접 닫지 않는다. 취소 반환은 실제 파일 작업이 끝날 때까지 늦어질 수 있다.

기존 64 KiB 읽기·32 MiB 상한·메타데이터 검증과 오류·SHA-256·성공 시 시작 위치로
되감기·같은 키의 지문/메타데이터 비교를 보존했다. 예약 commit → 잠금 → 외부 저장
종료 대기 → ready commit과 GC/재시도 계약, HTTP 경로/헤더/DTO는 변경하지 않았다.
기존 파일 처리 책임 안에 내부 async 보조 함수만 추가했다. 공개 service/types를
추가하거나 service가 workflow를 역호출하는 구조를 만들지 않았다.

시작 시 작업 트리에 있던 다른 변경은 보존했다. 타입 기준선이나 검사 예외를 늘리지
않았고 commit/push·운영 설정/데이터 변경은 수행하지 않았다.

## 검증

- 신규 `test_media_fingerprint_contracts.py`: **16 passed**.
  메모리/실제 디스크 spool의 다중 청크 지문·EOF 입력 되감기·완료 재전송·다른 내용
  충돌, MIME/파일명/purpose/빈 파일/크기 제한, 취소 없는 I/O 예외의 정체성과 호출자
  소유권을 확인했다. 실제 worker thread의 읽기/최종 되감기를 gate로 막고, 성공/실패
  × 단일/3회 취소의 8조합에서 이벤트 루프 진행·파일 유지·첫 취소 보존·작업 종료 후
  HTTP 파일 종료·예약/저장 미실행을 확인했다.
- 신규 테스트 + 기존 media cancellation/transport/character media contracts:
  **47 passed / 0 failed / 0 skipped**.
- 전용 로컬 PostgreSQL의 `test_character_media.py`, `test_media_http.py`:
  **32 passed / 0 failed / 0 skipped**. 로컬 저장소/가짜 S3의 예약·멱등성·실패 복구·
  취소·참조/GC 경쟁·인증별 HTTP 계약을 기존 회귀로 확인했다.
- 필수 `tools/check_backend_quality.py`: 통과. 패턴 진단 0, Ruff format/check 통과,
  mypy 376 source files 통과, 아키텍처/패턴 **13 passed**.
- 신규 테스트 Ruff format/check와 변경 파일 diff 공백 검사 통과.

실행 명령(프로젝트 `.venv/Scripts/python.exe` 사용):

```powershell
$env:PYTHONPATH='apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests/test_media_fingerprint_contracts.py apps/api/tests/test_media_cancellation_contracts.py apps/api/tests/test_media_transport_contracts.py apps/api/tests/test_character_media_contracts.py -q --tb=short --basetemp=tmp/u28-media-offline-final
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_character_media.py apps/api/tests/test_media_http.py
$env:PYTEST_ADDOPTS='--basetemp=tmp/u28-quality-temp'
.venv/Scripts/python.exe tools/check_backend_quality.py
```

초기 품질 검사의 pytest 기본 임시 경로 생성 오류는 작업 폴더 아래 basetemp로 해결했다.
샌드박스에서 asyncio 이벤트 루프 생성 자체가 socketpair의 accept에 멈추는 것을
독립 실행의 faulthandler로 확인하고, 멈춘 테스트를 종료한 뒤 샌드박스 밖에서 비동기/
PostgreSQL 테스트를 실행했다. 첫 회귀 실행의 8건 실패는 테스트 대역이 spool의
context 종료를 close override로 관찰하려 한 문제였고, 실제 __exit__ 종료를 관찰하도록
수정한 뒤 위 47건이 통과했다. 제품 코드의 오류로 분류하지 않는다.

최종 실행 로그: `tmp/u28-media-offline.txt`, `tmp/u28-media-postgres.txt`,
`tmp/u28-backend-quality.txt`.

실제 AWS/S3 네트워크·브라우저 연결 종료·프로세스 강제 종료·운영 처리량/지연은
미검증이다. 전체 업로드 deadline, 전송 중 DB 잠금을 대체할 실행 토큰/상태 소유권,
동일 입력 stream을 여러 호출자가 동시에 조작하는 경우는 이번에 재설계하지 않았다.
