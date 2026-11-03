# IEA-04 S3 reader 취소·정리 수정 보고서

실행일: **2026-11-03 (Asia/Seoul)**. 상태: **구현·오프라인 재현/회귀·필수 품질 검사 완료**.

정상 반환된 S3 reader의 진행 중 read와 close를 직렬화하고, 반복 취소와 동시
`aclose()`에도 하나의 정리 작업을 실제 종료까지 회수하도록 수정했다.
최종 업무 검증은 **145 passed / 0 failed / 30 skipped / setup·collection 오류 0**,
필수 품질 검사의 아키텍처/검사기 테스트는 별도로 **13 passed**다.
skip 30건은 PostgreSQL 환경 부재이며 통과 수에 포함하지 않는다.

## 시작 상태와 작업 경계

작업 경로는 `C:\Users\smj\Desktop\CHAT_STARTER_KIT\chat_kit`이다.
시작 및 최종 HEAD는 `31de1428aba2ea67fc887b004221f7bc3884cf0a`이고 staged 변경은 없었다.
현재 작업 트리를 기준으로 진행했다. 시작 시 이미 여러 unstaged 삭제/변경과
untracked 감사 자료가 있었고, 수정 대상 앱 파일에는 기존 diff가 없었다.

- 최초 읽기 전용 도구 출력에서 HEAD와 전체 `git status --short`를 확인했다.
  [초기 상태](initial-state.txt)에 수정 전 대상 18파일의 SHA256을 기록했다.
  이 파일의 상태 배열은 PowerShell 문자열 변환 때문에 `System.Object[]`로 기록됐다.
  원본 로그를 보존하고, 최초 도구 출력을 [별도 전사](initial-status-from-transcript.txt)했다.
- AGENTS.md, 모듈 아키텍처/명명 규칙, 백엔드 작성 규칙, 독립 재감사 REPORT와 두 S3
  재현 파일, asset_storage ARCHITECTURE, U08 작업 절, U23/U28 WORKLOG를 읽었다.
  실제 S3/local reader, AssetReadInfo, MediaStreamingResponse와 반환 reader 사용처를 대조했다.
- 이 작업은 앱 3파일·모듈 문서 1파일·신규 테스트 1파일과 이 전용 감사 폴더만 작성했다.
  studio_publication·태그/영수증·답변/과금 코드, 공용 검사 설정/타입 기준선,
  기존 감사 REPORT/WORKLOG는 수정하지 않았다. reset/clean/checkout·commit/push,
  별도 대화·서브에이전트를 사용하지 않았다.
- 병렬 작업의 추가 변경은 [중간 상태](pre-validation-state.json)와
  [최종 상태](after-final-state.json)에 보존했다. 최종 검증 전후 앱 Python 전체와
  관련 테스트/문서/원본 증거 **383파일의 해시가 모두 동일**했다.
  [검증 전 해시](before-final-hashes.json), [비교 요약](evidence-summary.json)을 제공한다.
  시작 시 해시 18개 중 바뀐 것은 이 작업의 앱 3파일과 ARCHITECTURE뿐이다.
  local 구현과 원본 재감사 REPORT/재현 두 파일의 해시는 유지됐다.

## 실제 원인과 발생 조건

수정 전 흐름은 다음과 같았다.

1. HTTP 응답 task가 `AssetReadInfo.read(64 KiB)` → S3 reader →
   `asyncio.to_thread(Body.read)`를 기다린다. 실제 read는 worker thread에서 진행한다.
2. ASGI 2.4 응답 task 취소 또는 ASGI 2.3 disconnect의 스트리밍 task 취소가
   read await를 취소한다. 이미 실행 중인 worker thread는 멈추지 않는다.
3. HTTP finally가 `opened.aclose()`를 호출한다. AssetReadInfo는 `_closed=True`를
   먼저 설정하고 S3 reader의 `to_thread(Body.close)`를 기다린다.
4. read가 한 worker를 점유하여 close가 실행기 큐에서 기다릴 때 **추가 취소**가
   close future를 취소한다. read 종료 뒤에도 해당 close 작업은 실행되지 않는다.
   이후 `aclose()`는 `_closed` 때문에 정리를 건너뛴다.

원본 재현을 실제 실행해 이 순서를 확인했다. 정상 disconnect만 있는 대조군은 닫혔다.
설치된 Uvicorn 종료 취소 재현은 `timeout_graceful_shutdown=0`을 **테스트에서 명시**한
경우다. 앱 Docker 기본 명령(`apps/api/Dockerfile:8`)에는 유한 graceful shutdown timeout이
없으며 설치 Uvicorn Config의 기본값은 `None`이다. 기본 실행의 평범한 disconnect가
항상 이 결함을 일으킨다고 주장하지 않는다. 확인한 것은 **명시적 회수 누락**이며,
운영의 영구 소켓 누수·장기 증가량·프로세스 종료 후 자원 잔류는 미입증이다.

## 수정과 수명 소유권

### S3 reader

`_S3AssetReader.read()`는 shield한 read task를 reader의 `_reads` 집합에 강하게 보유한다.
read await가 취소돼도 이 task와 worker future를 취소하지 않는다. read await 자체는
취소를 전달할 수 있지만 **실제 I/O 종료를 뜻하지 않는다**. 완료 callback은 정상/실패
결과를 회수하고 집합에서 제거한다. 늦은 read 오류도 미회수 task 예외로 남기지 않는다.
호출자는 취소된 read 뒤에도 해당 reader의 `aclose` 또는 async context 종료를 책임진다.

실제 `Body.read`와 `Body.close`에는 reader별 `threading.Lock`을 적용했다.
실행 중 read가 락을 보유하므로 close worker가 먼저 실행돼도 read와 물리적으로 겹치지 않는다.
close 시도가 락 안에서 시작된 뒤 락을 얻은 read는 Body에 접근하지 않고 거절한다.
close의 finally는 남은 read task를 gather하여, read가 끝나지 않았는데 정리 완료로
반환하지 않는다. close 실패 시에도 read 결과를 회수한다. 전용 실행기·별도 thread pool이나
스레드 강제 종료는 추가하지 않았다.

### 공유 AssetReadInfo와 local

AssetReadInfo가 `_close_task` 하나를 보유하고 모든 진행 중 `aclose()` 호출이 이를
shield로 **반복해서 끝까지** 기다린다. 각 호출자의 첫 CancelledError를 보관하고,
작업 결과/예외를 회수한 뒤 그 취소를 전달한다. 한 번 shield하고 소유자를 버리는 방식이 아니다.
동시 호출이 실제 close를 중복 실행하지 않는다. 새 내부 task 필드는 생성자·repr·동등성 비교에
참여하지 않는다.

상태 의미는 다음과 같다.

| 상태 | 의미 |
|---|---|
| `_closed=True` | 새 read 차단. 물리적 종료 성공의 증거가 아님 |
| `_close_task` 미완료 | close와 해당 reader의 I/O 회수 진행 중. aclose 호출자는 계속 기다림 |
| `_close_task` 예외 없는 완료 | 정리 작업 성공 |
| `_close_task` 예외 완료 | 정리 시도 종료/실패 회수. 물리적 close 성공은 보장하지 않음 |

완료된 close 시도는 실패해도 재시도하지 않는 기존 멱등 계약을 유지한다. 진행 중 동시
호출자는 동일한 close 결과를 받고, 완료 후 후속 호출은 no-op이다. 취소가 없으면 close
오류와 cause를 전달하며, 취소가 있으면 오류를 회수하고 첫 취소를 우선한다.

local adapter의 파일 열기·키 락·worker I/O 직렬화 코드는 수정하지 않았다.
공유 wrapper 변경에 대해 기존 실제 Windows 파일 수명 22건, 신규 local context/동시
close 경로, 기존 storage/HTTP/소비자 계약을 검증했다. U08의 늦은 reader 획득과
메타데이터 실패/close 실패 회수도 기존 15건의 취소 회귀로 확인했다.

### HTTP와 context 예외 우선순위

MediaStreamingResponse는 전송/read 오류 또는 취소가 있으면 정리를 끝까지 회수하고
처음 발생한 예외를 다시 전달한다. 정리 중 새 취소나 close 오류가 이를 덮지 않는다.
AssetReadInfo의 `__aexit__`에도 같은 우선순위를 적용했다. 기존 본문 오류가 없으면
정리 자체의 첫 취소 또는 close 오류를 전달한다. 오류 없는 전송의 close 실패를 성공으로
숨기지 않는다.

반환 reader는 계속 호출자/HTTP 응답이 소유한다. 주입 client는 호출자가 닫고 adapter는
자기가 생성한 client만 닫는다. SDK connect/read timeout·total_max_attempts/retry 설정,
오류 kind/operation/cause, 객체 키·메타데이터·업로드/삭제 동작은 바꾸지 않았다.
HTTP는 기존 64 KiB 청크를 유지하며 전체 객체 복제/사전 적재를 추가하지 않았다.
read task는 진행 중 읽기의 요청 청크와 결과만 보유한다.

## 변경 파일과 최종 줄 번호

줄 번호는 최종 검증 코드 기준이다. 경로는 저장소 루트 기준이다.

| 파일 | 줄 | 변경 |
|---|---:|---|
| `apps/api/app/modules/asset_storage/adapters/s3_storage/adapter.py` | 70 | read task 소유·결과 회수·물리적 I/O 락·close 후 read 회수 |
| `apps/api/app/modules/asset_storage/types.py` | 175, 188, 218 | 단일 close task·반복 취소/동시 대기·명확한 상태·context 최초 오류 보존 |
| `apps/api/app/http/media.py` | 89 | 정리 회수 뒤 전송의 최초 오류/취소 보존 |
| `apps/api/app/modules/asset_storage/ARCHITECTURE.md` | 3 | 변경된 공유/S3 reader 수명과 책임·한계, U08/U23 역사와 현재 계약 구분 |
| `apps/api/tests/test_s3_reader_lifecycle.py` | 49, 65, 80, 208 | 실제 gate/실행기/본문 관측과 신규 회귀 30건 |
| 이 전용 감사 폴더 | — | 본 보고서·상태/해시·비밀 없는 실행 로그·JUnit 증거 |

## 수정 전후 재현과 관찰

수정 전 원본 감사 두 파일을 그대로 실행한
[로그](before-audit-retry.txt)는 **2 failed / 2 passed / skipped 0**이다.
추가 취소가 있는 ASGI 2.4와 ASGI 2.3+Uvicorn 경로 모두 read 종료 후에도
`close_calls=0`, `raw_closed=False`, `_closed=True`였다. 추가 취소 없는 대조군은
두 경우 모두 close 1회·raw closed였다.

수정 후 원본 대조군 두 개는 다시 **2 passed**였다. 원본의 추가 취소 두 테스트는
`await response_task` **뒤에** read gate를 해제한다. 수정 후 aclose는 실제 I/O 회수를
기다리므로 이 순서는 합성 read의 timeout을 유발한다. 이 두 원본 테스트를 수정하거나
수정 후 passed로 보고하지 않았다. 신규 회귀는 동일한 실제 worker/StreamingBody/HTTP
경로에서 **추가 취소 전달 → 정리가 아직 대기함 확인 → read gate 해제 → 응답 task join**
순서로 검증한다. gate 해제 전에는 close 0회와 미완료 소유 task를 확인하고,
해제 뒤에는 read 종료·close 1회·read/close 겹침 없음·task/worker 회수를 확인한다.

최종 [실행 로그](verification-final.txt)와 [JUnit](verification-final.xml)에 관찰값을 남겼다.
성공 경로는 `read_finished=True`, `close_finished=True`, `close_calls=1`, `raw_closed=True`,
`pending_reads=0`, `close_task_done=True`, `caller_tasks_done=True`, `overlap=False`다.
실행기 shutdown/join 후 `alive=0`, 미회수 예외 handler 관찰은 `unhandled=0`이다.
close 실패 주입에서는 의도대로 `raw_closed=False`이고 **시도 완료와 예외 회수**만 확인한다.
읽기를 시작하지 않는 close 전용 사례의 `read_finished=False`는 미완료 read가 있다는 뜻이 아니다.

신규 30건의 구성은 다음과 같다.

| 검사 | 건수 | 관찰 |
|---|---:|---|
| 정상 청크 읽기·EOF·반복 aclose·client 소유권 | 1 | 실제 close 1회, 닫힌 뒤 read 거절 |
| 1/2 worker × 취소 0/1/3회, 진행 중 read+동시 aclose | 6 | close/read 비경합, 첫 취소, 모든 caller 회수 |
| 실제 close 진행 중 취소 1/3회 × close 성공/실패 | 4 | gate 전 미완료, 첫 취소, 실패 cause 회수 |
| 늦은 read 오류 × read 취소 유무 | 2 | 원래 오류 또는 취소 우선, 본문 close 실행 |
| close 실패의 동시 호출과 후속 멱등 호출 | 1 | 동일 오류, close 중복 없음 |
| 무관한 worker 포화로 큐에 대기한 close × 성공/실패 | 2 | 반복 취소에도 실제 작업 실행/오류 회수 |
| ASGI 2.3/2.4 × 추가 취소 유무 | 4 | 정상 disconnect 대조·실제 Uvicorn shutdown 취소·반복 취소 |
| HTTP 정상/read 오류/최초 취소/send 오류 × 정리 중 새 취소 유무 | 8 | 최초 오류/취소 정체성·cause 보존, close 실패 회수 |
| S3/local context 본문 오류+close 실패+반복 취소+동시 close | 2 | 원래 본문 오류와 단일 정리 시도 보존 |

합성 본문은 로컬 io.BytesIO이고 S3 HTTP 본문 wrapper는 설치된 실제 botocore
StreamingBody다. read/close 자체는 실제 worker에서 실행한다. Event와 제출 장벽으로
순서를 제어하며 임의 sleep이나 AsyncMock.aclose 호출 여부만으로 종료를 주장하지 않는다.
모든 신규 사례의 finally에서 gate 해제·task 회수·합성 자원 종료·실행기 shutdown/join과
기존 실행기 복원을 수행한다. close 실패 대역도 마지막에 직접 종료한다.

## 정확한 최종 검사 수

최종 한 번의 업무 실행은 175개 수집, **145 passed + 30 skipped**, 실패/오류 0이다.
[기계 판독 집계](evidence-summary.json)의 파일별 수와 일치한다.

| 범위 | passed | failed | skipped |
|---|---:|---:|---:|
| 신규 S3/shared 수명 | 30 | 0 | 0 |
| 기존 local 수명 | 22 | 0 | 0 |
| asset_storage / type 계약 | 20 + 7 | 0 | 0 |
| U08 포함 media cancellation / transport / fingerprint | 15 + 9 + 16 | 0 | 0 |
| character media 계약 / runtime entrypoint | 7 + 11 | 0 | 0 |
| media HTTP | 2 | 0 | 2 |
| character media DB | 0 | 0 | 28 |
| 상품 reader 전달·종료 소비자 | 4 | 0 | 0 |
| 원본 감사 대조군 | 2 | 0 | 0 |
| 업무 합계 | **145** | **0** | **30** |

필수 [check_backend_quality.py](backend-quality-final-code.txt)는 종료 코드 0이다.
패턴 진단 0, Ruff format 388파일·lint 통과, mypy 367소스 통과,
아키텍처/패턴 검사기 **13 passed / failed·skipped·오류 0**이다.
변경 Python 4파일의 [직접 Ruff format/check·mypy](changed-files-quality.txt)도 통과했다.
[대상 git diff --check](diff-check.txt)는 공백 오류가 없으며 LF/CRLF 안내만 있었다.

중간 실행은 합계에 다시 더하지 않는다. 최초 샌드박스 재현 시도는 출력 없이 정지하여
중단했고, 성공/실패 건수로 세지 않았다. 허용된 환경의 재시도에서 원본 재현 결과를 얻었다.
신규 첫 실행은 [18 passed / 4 failed](new-regression-first.txt)였으며, 두 번째 close
코루틴이 진입하기 전에 테스트가 취소한 하네스 오류였다. 진입 장벽을 추가한 뒤
[28 passed](new-regression-second.txt)를 확인했다. 큐 전용 2건을 추가한
[중간 관련 회귀](related-regression-final.txt)는 139 passed / 30 skipped였다.
최종에는 추가 소비자/원본 대조군 6건과 회수 관찰을 포함해 위 145/30을 확인했다.
기존 기대값·skip·설정·타입 기준선을 약화한 변경은 없다.

## 재실행 방법과 환경

모든 Python 실행은 프로젝트 `.venv/Scripts/python.exe`를 사용했다.
Windows Python 3.12.14, boto3/botocore 1.43.93, Starlette 1.6.0,
Uvicorn 0.52.4, pytest 8.4.2, pytest-asyncio 0.26.0이다([버전 로그](runtime.txt)).
각 실행의 basetemp는 기존 경로와 겹치지 않는 짧은 새 경로를 사용했다.
DB 및 외부 공급자 실행 환경을 제거했으며 실제 자격 증명이나 환경 값은 로그에 출력하지 않았다.
Windows 샌드박스 첫 비동기 실행이 정지하여 이후 비동기 검증은 승인된 실행 환경에서 수행했다.
외부 요청은 하지 않았다.

저장소 루트 PowerShell에서 다음처럼 최종 업무 범위를 재실행한다. 신규 30건만 확인하려면
`$targets`를 `@('apps/api/tests/test_s3_reader_lifecycle.py')`로 지정한다.

```powershell
$env:PYTHONPATH = 'apps/api'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Get-ChildItem Env: | Where-Object {
    $_.Name -match '^(TEST_DATABASE_URL|TEST_AUTH_DATABASE_URL|DATABASE_URL|AUTH_DATABASE_URL|PYTEST_ADDOPTS|RUN_.*|AWS_.*|OPENAI_.*|ANTHROPIC_.*|VOYAGE_.*|SMTP_.*|ASSET_S3_.*|LLM_.*|EMBEDDING_.*|MEMORY_SUMMARY_PROVIDER)$'
} | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:AWS_EC2_METADATA_DISABLED = 'true'
$targets = @(
    'apps/api/tests/test_s3_reader_lifecycle.py',
    'apps/api/tests/test_local_storage_lifecycle.py',
    'apps/api/tests/test_asset_storage.py',
    'apps/api/tests/test_asset_storage_type_contracts.py',
    'apps/api/tests/test_media_cancellation_contracts.py',
    'apps/api/tests/test_media_transport_contracts.py',
    'apps/api/tests/test_media_fingerprint_contracts.py',
    'apps/api/tests/test_character_media_contracts.py',
    'apps/api/tests/test_runtime_entrypoint_contracts.py',
    'apps/api/tests/test_media_http.py',
    'apps/api/tests/test_character_media.py',
    'apps/api/tests/test_product_views.py::test_media_reads_only_authorized_snapshot_ids_after_session_exit',
    'docs/audits/2026-11-02-independent-error-reaudit/test_s3_reader_lifetime.py::test_http_repeated_cancel_must_still_close_s3_body[False]',
    'docs/audits/2026-11-02-independent-error-reaudit/test_s3_disconnect_shutdown.py::test_asgi23_disconnect_and_server_shutdown_closes_body[False]'
)
$s3Temp = 'tmp/s3-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe -m pytest -p no:cacheprovider -p pytest_asyncio.plugin @targets -v -s -rs --tb=short --basetemp=$s3Temp
$env:PYTEST_ADDOPTS = '--basetemp=tmp/s3q-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
.venv/Scripts/python.exe tools/check_backend_quality.py
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
```

## 미검사 환경과 남은 한계

- 실제 AWS/S3·TLS·네트워크 socket, 운영 장기 자원 수/부하/지연, 브라우저/컨테이너
  종료 E2E, Linux 런타임은 검증하지 않았다. 실제 SDK 본문+로컬 대역의 오프라인 검증이다.
- PostgreSQL 관련 30건은 환경을 제거해 skip했다. 앱 DB migration/초기화/삭제,
  Docker 볼륨 변경과 외부 LLM/SMTP/S3 요청을 실행하지 않았다. DB 통합 성공을 주장하지 않는다.
- 진행 중 동기 I/O는 취소로 중단되지 않는다. read/close가 반환하지 않거나 실행기가
  진행하지 못하면 정리 대기도 길어질 수 있다. 새로운 전체 deadline/강제 종료를 넣지 않았다.
  프로세스 강제 종료나 이벤트 루프의 전체 task 강제 종료에 대한 완료 보장은 없다.
- close 자체가 실패한 경우 단일 실패 시도를 회수할 뿐 물리적 자원 종료를 보장하지 않는다.
  API의 멱등 close를 무제한 재시도로 바꾸지 않았다. 반환 reader를 닫지 않는 호출자까지
  adapter가 자동 수거하지 않는다.
- U28 업로드 중 DB 잠금 대체 설계·전체 업로드 deadline, 미확정 IEA-01 답변 과금 후보는
  이번 범위에 포함하지 않았다. 최종 검증 결과는 해시가 기록된 현재 작업 트리의 범위이며,
  이후 병렬 작업/통합 변경에 자동으로 확장되지 않는다.
