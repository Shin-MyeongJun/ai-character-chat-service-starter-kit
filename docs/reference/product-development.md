# 상품 개발·검증 실행 메모

진행 상태와 미완료 항목은 [작업 계획](product-implementation-plan.md)을 기준으로 한다.

## 테스트

프로젝트 루트 PowerShell에서 실행한다.

```powershell
$env:PYTHONPATH = (Resolve-Path apps/api).Path
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
```

PostgreSQL 통합 테스트는 `TEST_DATABASE_URL`이 없으면 skip한다. pgvector가
설치된 별도 테스트 DB를 준비하고 해당 환경 변수에 asyncpg URL을 설정한다.
DB 이름에는 `test`가 포함되어야 한다. 각 테스트는 고유한 `test_*` 스키마를
만들고 종료 시 해당 스키마만 삭제한다. 운영 DB URL을 사용하지 않는다.

## 마이그레이션

`DATABASE_URL`에 대상의 `postgresql+asyncpg://...` URL을 설정한다.

```powershell
.\.venv\Scripts\python.exe -m alembic -c apps/api/alembic.ini upgrade head
```

빈 DB는 0001 baseline부터 적용한다. 이미 테이블이 있는 DB는 백업·스키마
비교·데이터 조사 후 기준 버전을 명시적으로 정해야 한다. 일부 테이블이
있다는 이유만으로 `stamp`하지 않는다. 새 대화 버전 FK는 nullable로 추가해
검증 불가능한 과거 기록을 그대로 보존하며, 자동 백필은 수행하지 않는다.

신규 Docker DB는 기존 001~003 초기화 SQL 다음 004를 실행한다. 초기화 SQL은
기존 볼륨에는 자동 재적용되지 않는다. 004는 Alembic 0001 이후 SQL에서
alembic_version 갱신만 제외한 파일이며 반복 실행용 스크립트가 아니다.

## 앱 연결

상품 `router`, 대화 `router`, 관리 영역의 `product_router`, `model_router`를
FastAPI 앱에 포함한다. `product.dependencies.get_product_session`은 요청마다
독립 AsyncSession을 제공하고 `get_current_owner_id`는 인증된 사용자 ID를
반환해야 한다. 인증 조회와 쓰기 command가 같은 열린 트랜잭션을 공유하지
않도록 한다. 미설정 상태는 503으로 거부한다. 클라이언트 owner_id를 신뢰하지
않는다. 관리자 기능은 DB의 활성 admin 역할도 검사한다.

대화의 `runtime_context`는 내부 실행 계약이며 HTTP로 반환하지 않는다.
호출자가 트랜잭션을 관리하고, 모델 대체 계획 기록이 포함되므로 성공 시
커밋한다. 반환값의 `execution`을 실제 모델 호출에 사용한다. 생성 전에 얻은
버전을 `append_generated_message`에 전달하여 버전 전환 중 나온 과거 응답을
저장하지 않도록 한다. 해당 메시지 저장은 C13의 사용 기록과 아직 통합되지
않았으며 호출 재시도 멱등성도 C13에서 함께 완성해야 한다.

이미지·에셋의 URL은 불변 저장소 객체를 가리켜야 한다. DB에서 URL 문자열을
복사하는 것만으로 실제 파일의 덮어쓰기/삭제를 방지할 수는 없다. 저장소
연동 시 `media_is_referenced` 검사 및 참조 보존 정책을 적용해야 한다.
