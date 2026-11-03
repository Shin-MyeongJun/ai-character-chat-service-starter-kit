# 두 수정 통합 후 커밋 전 마무리 검증

실행일: 2026-11-03 (Asia/Seoul).
기준 HEAD: `31de1428aba2ea67fc887b004221f7bc3884cf0a`.
대상은 스튜디오·S3 수정과 기존 미커밋 변경이 합쳐진 현재 작업 트리다.

**판정: 지정한 두 수정의 업무 회귀·실제 PG 검증·필수 품질 검사를 통과했다.**
스튜디오 수정 보고서의 DB 연결 불가로 남았던 검증을 이번에 완료했다.
운영 배포나 전체 시스템/외부 공급자 검증 완료 판정은 아니다. commit/push는 하지 않았다.

## 실제 결과

| 검사 | passed | failed | skipped | setup/collection errors | 로그 |
| --- | ---: | ---: | ---: | ---: | --- |
| 스튜디오 신규 PG 11건 + 첫 DB 환경 확인 1건 | 12 | 0 | 0 | 0 | [final-docker-studio-01](logs/final-docker-studio-01.txt) |
| 관련 태그·발행·저장소·미디어 및 원래 영수증 재현 | 261 | 0 | 0 | 0 | [final-combined-regressions-01](logs/final-combined-regressions-01.txt) |
| 필수 품질 검사 내 아키텍처/검사기 | 13 | 0 | 0 | 0 | [final-quality-01](logs/final-quality-01.txt) |
| 전체 종료 후 DB 환경 재확인 | 1 | 0 | 0 | 0 | [final-environment-01](logs/final-environment-01.txt) |

업무 테스트는 **272 passed**, 품질 내부 테스트는 **13 passed**다.
DB 환경 확인은 같은 테스트를 전후 두 번 실행했으므로 고유 테스트 합계는
**286건**이며 실행 횟수 합계는 287건이다. 과거 실행 수와 합산하지 않는다.

필수 품질: 패턴 기준선 신규 위반 0, Ruff format 388파일, lint 통과,
mypy 367소스 통과, 전체 도구 종료 코드 0.

## 결함별 수락 근거

### IEA-02: 스튜디오 태그 교착

`test_studio_publication_db.py`는 독립 PG 연결과 실행 장벽을 사용한다.
구 순서 대조군은 전체 이름 선획득만 비활성화하고 실제 최초 resolve SQL 뒤에서
동기화한다. 결과는 **HTTP [200, 500], SQLSTATE 40P01**이다.
수정 경로는 전체 이름 획득 전 장벽과 `pg_blocking_pids` 관찰을 사용하며
**HTTP [200, 200], 교착 오류 없음**으로 끝났다.
이미 존재하는 태그 대조군도 [200, 200]이다. 재전송 후 snapshot은 모두 2개다.

관리자 변경 fencing, 부모별 비활성 태그 유지/신규 연결 거절,
영수증 저장 실패 rollback과 재시도, legacy 매핑 보존 검사도 통과했다.
U25 실제 PG 경합, 기존 studio 잠금 및 tag 관리 회귀도 함께 통과했다.
임의의 모든 writer 조합·격리 수준에서 교착이 없다는 주장은 하지 않는다.

### IEA-03: 무변경 발행 영수증

새 PG 회귀 외에 원래 감사의 HTTP/서비스 재현 두 건도 그대로 실행했다.
D 발행 → E 저장 → D 복귀 → 무변경 발행 → 다음 초안 저장 → 같은 발행 요청 재생이
**HTTP 200**이다. revision 1과 3의 영수증이 모두 남고,
snapshot 수 1 및 과거 snapshot JSON 동일성을 확인했다.
즉시 재시도와 원래 revision 1의 재시도도 200이다.

### IEA-04: S3 reader 취소 정리

신규 `test_s3_reader_lifecycle.py` 30건과 기존 local/S3/media 회귀를 실행했다.
실제 worker thread, 설치 botocore body, 제어된 read/close gate를 사용한다.
정상 close 경로는 실제 close 1회, pending read 0, close task 종료,
회수 후 worker 생존 0, 미회수 예외 0을 확인했다.
close 자체 실패를 주입한 사례의 raw_closed=False는 의도한 실패 계약이며
물리적 close 성공으로 집계하지 않는다.
Uvicorn 종료 취소 로그와 memory 오류 주입 경고는 해당 테스트의 예상 경로다.

기존 감사의 수정 전 스케줄 가정을 가진 전체 재현을 무작정 재실행하지 않았다.
스튜디오 전체 선획득 이전/이후 장벽 위치와 S3 정리 완료 대기 계약에 맞는
정식 회귀를 사용했다. 원래 영수증 두 재현은 수정 없이도 유효하므로 그대로 실행했다.

## 실행 범위

261건 실행의 대상은 다음 20개 지정 경로다.

- `apps/api/tests/test_u25_postgres_concurrency.py`
- `apps/api/tests/test_studio_locking_db.py`
- `apps/api/tests/test_tag_management_db.py`
- `apps/api/tests/test_studio_publication.py`
- `apps/api/tests/test_studio_republication_contracts.py`
- `apps/api/tests/test_tag_resolve_batch_contracts.py`
- `apps/api/tests/test_s3_reader_lifecycle.py`
- `apps/api/tests/test_local_storage_lifecycle.py`
- `apps/api/tests/test_asset_storage.py`
- `apps/api/tests/test_asset_storage_type_contracts.py`
- `apps/api/tests/test_media_cancellation_contracts.py`
- `apps/api/tests/test_media_transport_contracts.py`
- `apps/api/tests/test_media_fingerprint_contracts.py`
- `apps/api/tests/test_character_media_contracts.py`
- `apps/api/tests/test_runtime_entrypoint_contracts.py`
- `apps/api/tests/test_media_http.py`
- `apps/api/tests/test_character_media.py`
- `apps/api/tests/test_product_views.py::test_media_reads_only_authorized_snapshot_ids_after_session_exit`
- `docs/audits/2026-11-02-independent-error-reaudit/test_http_publication.py::test_http_noop_publication_replay_after_new_save`
- `docs/audits/2026-11-02-independent-error-reaudit/test_reproductions.py::test_noop_publication_retry_must_survive_later_draft_save`

PG 설정이 있는 실행이지만 이 중 오프라인 테스트도 포함된다.
261건 모두가 PG 잠금 시험이라는 뜻은 아니다.

## 환경·변경 보존과 커밋 점검

- 프로젝트 `.venv/Scripts/python.exe`와 기존 범위 검사 도우미
  `tools/run_postgres_audit_tests.py`만으로 전용 DB에 접속했다.
- PostgreSQL 17.11 / READ COMMITTED. 모든 업무 검사 종료 후 두 전용 DB에서
  테스트 스키마 잔량 각각 0을 확인했다. 운영/앱 DB에는 접속하지 않았다.
- 외부 공급자 실행 환경을 제거하고 고유한 짧은 basetemp와 UUID 스키마를 사용했다.
  Docker 볼륨/앱 DB migration·초기화·삭제와 외부 LLM/SMTP/S3 요청은 하지 않았다.
- 검사 시작과 종료 사이 앱·프로젝트 테스트 코드의 해시 변경은 0이다.
  새로운 결함 수정이나 기대값/skip/타입 기준선 변경은 없었다.
- `git diff --check HEAD`에서 감사 스크립트 7개의 EOF 빈 줄을 발견했다.
  원본 바이트를 로컬 tmp에 보관한 뒤 마지막 불필요 빈 줄만 제거했다.
  함수·검증 동작은 변경하지 않았다. 이 기계적 정리와 이번 문서만 추가 반영한다.
- 원시 로그·해시 목록은 기존 ignore 규칙으로 Git에서 제외한다.
  이번 최종 검증 보고서는 버전 관리 대상으로 남긴다.

로컬 기준·종료 해시와 로그 해시는 [final-validation-state.json](final-validation-state.json)에
기록한다. 이 파일과 로그 링크는 새 clone에는 없을 수 있으며 정책은
[감사 기록 안내](../README.md)를 따른다.

## 재실행

저장소 루트 PowerShell에서 실행하고 로그 이름은 매번 새 이름을 사용한다.

```powershell
$runner = 'docs/audits/2026-11-03-iea-studio-fix/run_checks.py'
.venv/Scripts/python.exe $runner pg recheck-studio-01 apps/api/tests/test_studio_publication_db.py
.venv/Scripts/python.exe $runner pg recheck-s3-media-01 apps/api/tests/test_s3_reader_lifecycle.py apps/api/tests/test_media_http.py apps/api/tests/test_character_media.py
.venv/Scripts/python.exe $runner command recheck-quality-01 tools/check_backend_quality.py
```

전체 API·웹 빌드·브라우저·실제 AWS/S3·운영 네트워크·Linux·부하 시험은 이번에
다시 실행하지 않았다. 이번 수정과 무관한 동일 소스의 과거 전체 통합 결과를
반복하지 않고, 미완료 PG와 변경된 경계의 관련 회귀를 우선 확인했다.
U19/U28 설계 보류와 미확정 IEA-01은 이 검증으로 완료 처리하지 않는다.
