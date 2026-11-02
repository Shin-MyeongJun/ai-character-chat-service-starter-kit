# U04 스튜디오 잠금 순서 통일

작성일: 2026-10-30 (Asia/Seoul)

## 결과와 변경 범위

revision 지정 스튜디오 저장이 product/draft 행을 먼저 잠그고 advisory를 나중에 얻던
순서를 수정했다. product의 공개 잠금 조회가 먼저 같은 `product-studio-draft` advisory를
얻으므로 직접 저장과 모두 advisory → product → draft 순서다. 업로드 준비·발행도 이
공개 조회를 사용한다. 직접 호출 가능한 매핑/영수증 쓰기도 같은 순서로 맞췄다.
새 계층·테이블·migration·내부 commit·savepoint·재시도 루프는 추가하지 않았다.

동일 digest의 재시도는 기존처럼 revision CAS보다 먼저 반환한다. stale/누락 revision도
동일 문서이면 기존 결과이며, 다른 문서의 stale revision은 StudioDraftConflictError다.
legacy 매핑 채택을 저장 전에 수행하는 순서와 실패 시 전체 rollback을 유지한다.
U06 후속 발행·기존 스냅샷/영수증과 U14 발행 저장 단계 계약은 바꾸지 않았다.

실제 PG의 legacy 매핑 채택 검증에서 기존 `MissingGreenlet` 오류도 발견했다. 영수증
갱신 flush가 SQL onupdate의 updated_at을 만료시킨 뒤 mapper가 해당 속성을 읽으며
암묵적 async I/O가 발생했다. repository의 영수증/매핑 쓰기가 flush 후 행을 refresh하도록
수정했다. 조회 책임을 mapper로 옮기지 않았으며 저장 JSON/revision/digest는 유지한다.

## 실제 PostgreSQL 검증

`test_studio_locking_db.py`의 **12개 테스트 전부 통과**. 저장소/트랜잭션/advisory/행 잠금은
대역이 아닌 실제 SQL이다. 두 작업은 각각 독립 AsyncSession과 다른 pg_backend_pid를
사용하며, 별도 관찰 연결이 pg_blocking_pids와 pg_locks로 실제 advisory 대기를 확인한 뒤
실행 장벽을 해제한다. 임의 sleep만으로 교차 실행을 가정하지 않는다. 태스크 정리와
statement/lock/전체 기한을 두어 실패 시 세션/잠금을 남기지 않는다.

- 이전 product → draft → advisory 순서를 대조 경로로 실행하면 PG가 실제 deadlock을
  검출한다(SQLSTATE **40P01**). production 코드를 되돌리거나 DB 잠금을 mock하지 않는다.
- revision 지정 편집과 revision 없는 동일 내용 재시도를 두 시작 순서로 실행한다.
  수정 경로에서는 교착 없이 진행하며 최종 문서/revision/digest를 확인한다.
- 같은 expected_revision의 서로 다른 두 문서는 두 시작 순서 모두 한 건만 revision을
  올리고 다른 한 건은 CAS 충돌한다. 패자의 문서/프로필은 남지 않는다.
- 같은 revision·같은 문서의 동시 수정은 승자의 동일 결과를 반환한다.
- 아직 product/draft가 없는 같은 ID·같은 문서의 동시 생성은 한 행씩만 만들고 revision 1의
  같은 결과를 반환한다. 행 생성 전 advisory 보호를 유지한다.
- expected_revision=None/1/2인 동일 내용 재시도를 직접/상위 저장 양쪽에서 확인한다.
  저장된 revision/digest/문서/영수증/매핑/updated_at이 같다.
- 실제 legacy 구성 조회와 매핑 저장 후 stale CAS가 실패하면 매핑/문서가 함께 rollback된다.
  다음 별도 연결의 정상 저장은 성공하고 같은 legacy 구성 ID를 채택한다.
- 실제 문서 flush 직후 예외를 주입하면 프로필·태그 사전/연결·문서/revision이 모두
  rollback된다. 예외 전에는 태그 연결과 수정 revision이 실제 DB에 존재함도 확인한다.

전용 감사 DB `chatkit_audit_test_12310f`와 실행별 UUID 테스트 스키마를 사용했다.
앱 DB/볼륨/운영 설정은 변경하지 않았고 비밀번호는 출력하지 않았다.
Windows 샌드박스의 asyncio socket 제한 때문에 실제 PG 실행에는 동일 전용 DB 명령의
실행 권한을 조정했다. 스키마 격리와 접속 범위 검사는 기존 실행 도우미를 그대로 사용한다.
최종 읽기 전용 확인에서 감사 DB와 인증 테스트 DB의 잔여 test_/auth_test_ 스키마는
각각 **0개**였다.

## 검증 명령과 결과

```powershell
.venv/Scripts/python.exe tools/run_postgres_audit_tests.py apps/api/tests/test_studio_locking_db.py apps/api/tests/test_product_studio_contracts.py apps/api/tests/test_studio_draft_guard.py apps/api/tests/test_studio_republication_contracts.py apps/api/tests/test_studio_validation_contracts.py apps/api/tests/test_studio_publication.py apps/api/tests/test_publication_batch_contracts.py
```

**115 passed / 0 failed / 0 skipped**. 이 중 신규 12개가 실제 PG 검증이며, 나머지 기존
103개에는 오프라인 SQL 및 공개 서비스 대역을 사용하는 저장·발행·U06/U14 회귀가 포함된다.
모든 115개가 실제 PG 경합 시험이라는 뜻은 아니다.
로그: [u04-studio-regression-final.txt](../../../tmp/u04-studio-regression-final.txt).

```powershell
$env:PYTEST_ADDOPTS = '--basetemp=tmp/u04-quality-' + [guid]::NewGuid().ToString('N').Substring(0,8)
.venv/Scripts/python.exe tools/check_backend_quality.py
```

최초 품질 실행에서 샌드박스 기본 임시 폴더를 만들 수 없어 기존 tmp_path 테스트 2개가
setup 오류를 냈다. workspace 내 새 basetemp로 재실행해 패턴/포맷/Ruff/mypy와 아키텍처/
검사기 **13개 테스트가 통과**했다. 기준선/엄격 검사 범위 예외는 추가하지 않았다.
신규 PG 테스트 파일도 별도 Ruff format/check 및 mypy를 통과했다.
로그: [u04-backend-quality.txt](../../../tmp/u04-backend-quality.txt).

기존 staged/unstaged 변경을 보존했으며 공통 감사 REPORT·검사 설정·commit/push는
수정/실행하지 않았다. 전체 API·외부 공급자·브라우저 E2E·처리량 시험은 이 작업 범위가 아니다.
