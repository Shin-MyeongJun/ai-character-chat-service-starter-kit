# U23 작업 기록 — 로컬 reader·파일·락 수명

작성일: 2026-10-29 (Asia/Seoul)

상태: **구현·오프라인 검증·기록 완료.**

## 시작 상태와 재현

AGENTS.md, 모듈 아키텍처/명명 규칙, 백엔드 코드 작성 규칙, 원본 감사 U23,
최신 U15/U25 통합 기록과 asset_storage ARCHITECTURE를 읽고 대상의 staged/unstaged diff를
확인했다. 로컬 adapter와 test_asset_storage.py는 시작 시 변경이 없었고 기존 S3 adapter·
ARCHITECTURE의 U08 변경은 보존했다. reset/clean·무관한 복원/삭제·별도 대화/서브에이전트·
commit/push는 하지 않았다. 시작 전체 API 기준은 1337 passed / 288 skipped였다.

신규 회귀를 먼저 실행해 **10 failed / 0 passed / 0 skipped**를 확인했다.
실제 Windows 파일로 열린 reader 삭제·덮어쓰기 충돌과 누적 키 락을 재현했다.
제어된 worker thread로 취소 후 파일 작업이 계속되는데 키 락이 먼저 풀리거나 늦은 reader가
버려지는 문제, read와 close가 겹치는 문제도 확인했다. 이들은 같은 reader/락 소유 수명에
속하므로 로컬 adapter 내부에서 함께 수정했다. S3와 공유 AssetReadInfo는 변경하지 않았다.
수정 전 로그: [u23-regression-before.txt](../../../tmp/u23-regression-before.txt).

## 채택한 정책과 구현

1. 키 락 캐시를 WeakValueDictionary로 변경했다. 락 소유자·대기자가 강한 참조를 갖는 동안
   같은 키를 직렬화하고 마지막 사용 뒤 캐시 키를 제거한다. 여러 키를 성공/실패 경로로
   순회한 회귀에서 idle 캐시가 0개임을 확인했다. 장시간 RSS 측정 결과라는 의미는 아니다.
2. reader는 획득 당시 파일 버전과 metadata를 유지한다. 삭제 후 새 read/metadata는
   AssetNotFoundError이고, 같은 키를 즉시 다시 저장할 수 있다. 이전 reader의 닫기는
   재사용된 새 키를 삭제하지 않는다. reader가 열린 채 연속 덮어써도 각각 자기 본문을 읽는다.
3. Windows에서는 CPython _winapi.CreateFile의 읽기·삭제 공유를 사용하고
   msvcrt.open_osfhandle→os.fdopen으로 소유권을 이전한다. 변환 실패 시 native handle 또는
   descriptor를 해당 단계에서 닫는다. 다른 플랫폼은 기존 Path.open("rb")다.
4. 실제 Windows 실험에서 삭제 공유만으로는 열린 대상을 os.replace하는 동작이 거절됐다.
   그 경우에만 기존 본문 이름을 같은 디렉터리의 임시 .old로 옮겨 새 본문을 발행하고,
   이전 이름을 unlink한다. 새 발행 또는 .old 정리 실패 시 기존 본문 이름을 복원하고
   바깥 저장 로직이 기존 sidecar를 복원한다. 두 단계 실패 주입에서 본문·metadata·열린
   reader와 임시 파일 정리를 확인했다. 일반 권한 오류는 기존 공급자 중립 오류로 전달한다.
5. 전체 파일 복사·메모리 적재·영속 버전 manifest·새 sidecar 필드를 추가하지 않았다.
   공개 Command/Info/object_key와 root/object_key 및 기존 metadata 레이아웃은 유지한다.
6. store/delete/metadata의 스레드 작업은 shield한 태스크로 끝까지 회수하고 키 락을
   해제한다. 첫 CancelledError를 보존하며 반복 취소로 소유권을 버리지 않는다. 취소된
   쓰기는 이미 반영됐을 수 있고, 입력 stream을 닫아도 되는 시점은 작업 종료 후다.
7. read 획득도 태스크를 소유하며 취소 뒤 늦게 얻은 reader를 닫고 첫 취소를 전달한다.
   reader별 read/close 락으로 진행 중인 스레드 read와 close의 겹침을 막는다. close의
   락 대기·실제 종료까지 회수해, 대기/close 중 반복 취소로 파일이 버려지지 않게 했다.
   취소와 작업/close 오류가 함께 있으면 오류를 회수하고 첫 취소를 최종 전달한다.
8. 기존 OS 오류 kind/operation/object_key/cause와 손상된 metadata 오류, 단건 삭제의
   멱등성과 reader 종료 후 read 거절을 유지한다. 입력 stream·반환 reader의 수명은
   호출자 책임이며 adapter.aclose가 열린 reader를 일괄 종료하지 않는다.

reader 수명 전체의 키 락은 느린 스트리밍에 삭제를 묶기 때문에 채택하지 않았다.
전체 파일을 복사하는 read snapshot도 기존 스트리밍 비용을 바꾸므로 채택하지 않았다.
짧은 키 I/O 직렬화와 OS의 열린 파일 수명으로 처리하며 별도 DB/공통 정책 계층은 없다.

플랫폼 계약 출처:

- FILE_SHARE_DELETE는 열린 handle과 함께 삭제/이름 변경을 허용하는 공유 정책이다.
  [Microsoft CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
- open_osfhandle로 만든 descriptor는 fdopen의 file object로 넘길 수 있다.
  [Python msvcrt](https://docs.python.org/3.12/library/msvcrt.html).
- 성공한 open_osfhandle은 handle 소유권을 descriptor로 넘기므로 CloseHandle과 중복
  종료하지 않는다. [Microsoft CRT ownership](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/open-osfhandle?view=msvc-170).

실제 삭제·재사용·교체 결과는 위 문서만으로 추정하지 않고 이 작업의 Windows 파일 테스트로
확인했다. CPython Windows의 _winapi 래퍼를 사용하므로 다른 Windows Python 구현까지
호환성을 검증했다는 의미는 아니다.

## 수정 파일

| 파일 | 변경 |
|---|---|
| apps/api/app/modules/asset_storage/adapters/test_local_storage/adapter.py | 파일 공유/교체·취소와 reader/키 락 수명 |
| apps/api/tests/test_local_storage_lifecycle.py | 신규 회귀 22건 |
| apps/api/app/modules/asset_storage/ARCHITECTURE.md | 수명·취소·플랫폼·복구 책임과 한계 |
| docs/audits/2026-10-23-structural-review/REPORT.md | U23 완료 상태, 과거 감사 근거 보존 |
| docs/audits/2026-10-26-pattern-standardization/REPORT.md | 11차 작업·전체 검증 기록 |
| docs/audits/2026-10-26-pattern-standardization/U23-WORKLOG.md | 전용 기록 |

## 회귀와 검증

신규 22건은 실제 Windows 파일의 다중 reader 중 삭제·즉시 키 재사용·연속 덮어쓰기와
metadata 유지, 발행/이전 파일 정리 실패 복원, handle/descriptor 변환 실패 종료,
누적 키 락 회수·동일 키 대기/대기 취소·다른 키 진행을 검사한다. 취소 중 store/delete/open,
read/close 순서와 close 락 대기, 반복 취소·close 실패·첫 취소 우선, metadata 손상과
기존 OS 오류도 검증한다. 저장소 결과는 실제 파일이며 스레드 타이밍은 gate로 제어한다.
read/close 내부 경합과 종료 실패는 BytesIO 대역을 쓰고 native handle 단계는 실제 handle을
획득한 뒤 변환 실패만 주입한다. S3와 일부 미디어 경계는 기존 테스트의 대역이다.

| 검사 | passed | failed | skipped | 상세 |
|---|---:|---:|---:|---|
| 수정 전 신규 회귀 | 0 | 10 | 0 | 실패를 확인한 뒤 수정 |
| 관련 업무 최종 7파일 | **86** | **0** | **2** | 신규 22건 포함 |
| 전체 API 최종 | **1359** | **0** | **288** | 기존 422 상수 경고 2개 |
| 필수 check_backend_quality.py | 13 | 0 | 0 | Ruff 390파일·mypy 369소스·기준선 0개 |
| 변경 Python 2파일 Ruff format/check·mypy | — | 0 | — | Windows 대상 2소스 |
| Linux 대상 추가 mypy | — | 0 | — | 2소스, 런타임 실행은 아님 |
| 변경 범위 git diff --check | — | 0 | — | 통과 |

모든 실행은 프로젝트 .venv/Scripts/python.exe를 사용하고 TEST_DATABASE_URL 및
TEST_AUTH_DATABASE_URL을 제거했다. Windows asyncio 샌드박스 제약이 알려진 업무 검증은
승인된 오프라인 실행을 사용했다. 짧은 새 basetemp를 매번 생성했다. skipped를 passed에
포함하지 않았고, 전체 API에 포함되는 품질 테스트 13건도 다시 더하지 않는다.
전체 1359 passed는 이전 U15/U25 통합 1337건에 신규 22건이 더해진 실제 실행 결과다.

개발 중 직접 mypy에서 BytesIO.read 대역의 int/None 인자 호환 오류 2건을 바로잡았고,
추가 Linux 검사에서 플랫폼 import 참조 오류 4건을 양의 플랫폼 분기로 해결했다.
Any/ignore/cast/기준선 예외·공통 검사 설정으로 우회하지 않았다. 수정 뒤 두 플랫폼의
직접 타입 검사와 전체 품질/업무 회귀를 통과했다.

로그: [업무 최종](../../../tmp/u23-business-final.txt),
[전체 API](../../../tmp/u23-api-final.txt), [필수 품질](../../../tmp/u23-quality-final.txt).

## 재실행 명령

저장소 루트 PowerShell에서 실행한다. basetemp는 기존 경로를 재사용하지 않고 짧게 만든다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_AUTH_DATABASE_URL, Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
$u23Temp = 'tmp/u23-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests/test_local_storage_lifecycle.py apps/api/tests/test_asset_storage.py apps/api/tests/test_asset_storage_type_contracts.py apps/api/tests/test_media_cancellation_contracts.py apps/api/tests/test_media_transport_contracts.py apps/api/tests/test_runtime_entrypoint_contracts.py apps/api/tests/test_media_http.py -q -rs --tb=short --basetemp=$u23Temp

$u23AllTemp = 'tmp/u23-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin apps/api/tests -q -rs --tb=short --basetemp=$u23AllTemp

$env:PYTEST_ADDOPTS = '--basetemp=tmp/q23-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue

.venv/Scripts/python.exe -m ruff format --check --config apps/api/pyproject.toml apps/api/app/modules/asset_storage/adapters/test_local_storage/adapter.py apps/api/tests/test_local_storage_lifecycle.py
.venv/Scripts/python.exe -m ruff check --config apps/api/pyproject.toml apps/api/app/modules/asset_storage/adapters/test_local_storage/adapter.py apps/api/tests/test_local_storage_lifecycle.py
.venv/Scripts/python.exe -m mypy --config-file apps/api/pyproject.toml apps/api/app/modules/asset_storage/adapters/test_local_storage/adapter.py apps/api/tests/test_local_storage_lifecycle.py
.venv/Scripts/python.exe -m mypy --platform linux --cache-dir=tmp/u23-mypy-linux --config-file apps/api/pyproject.toml apps/api/app/modules/asset_storage/adapters/test_local_storage/adapter.py apps/api/tests/test_local_storage_lifecycle.py
```

## 한계와 보존 범위

- 검증은 현재 Windows 로컬 파일시스템에서 수행했다. Linux는 타입 검사만 실행했고
  런타임·네트워크 파일시스템·다른 Windows Python 구현은 검증하지 않았다.
- 락은 같은 어댑터 인스턴스의 같은 event loop 범위다. 다중 어댑터/프로세스·직접 파일
  수정에 대한 동시성/두 파일 원자성은 보장하지 않는다. 외부의 삭제 비공유 handle이나
  실제 접근 권한 오류는 여전히 실패할 수 있다.
- 프로세스 중단과 본문/metadata 복원 자체 실패의 완전 복구는 보장하지 않는다.
  임시 .old가 남는 장애에 대해 소유권 확인 없이 지우는 정리기를 추가하지 않았다.
- 스레드의 파일 I/O를 강제 중단하지 않는다. 취소 반환은 해당 I/O/회수 종료까지 지연될 수
  있고 취소된 store/delete가 이미 반영됐을 수 있다. close 실패는 1회 시도를 회수하며
  실제 파일 종료 성공을 보장하지 않는다.
- 장시간 메모리/RSS·운영 성능·실제 S3/DB는 미검증이다. DB migration/초기화/삭제나
  외부 공급자 요청은 실행하지 않았다. 기존 U08/U15/U25와 기타 변경을 보존했다.
