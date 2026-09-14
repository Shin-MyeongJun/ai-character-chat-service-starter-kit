# asset_storage 모듈

## 책임과 경계

`asset_storage`는 객체 키로 파일을 저장·스트리밍 읽기·삭제·메타데이터 조회하는 독립 모듈이다. 소유 DB 테이블은 없으며 repository, mapper, router도 필요하지 않아 만들지 않았다. 호출자의 상품·캐릭터 권한 판단, 파일 참조의 도메인 영속화, HTTP 파일 제공, URL 발급은 이 모듈의 책임이 아니다.

다른 업무 모듈은 `app.modules.asset_storage.service`와 `app.modules.asset_storage.types`의 공개 API만 사용한다. `app.main`이 설정 → 팩토리 → 서비스 수명을 조립하고 character의 `CharacterMediaService`에 주입한다. 상품은 자신의 접근 정책을 확인한 뒤 character 공개 미디어 서비스를 호출한다. 저장소 모듈은 여전히 DB·HTTP·도메인 인가를 소유하지 않는다.

파일별 책임은 다음과 같다.

- `types.py`: Command/Info, `AssetStorageAdapter` Protocol, 설정과 공급자 중립 오류.
- `service/storage.py`: 어댑터를 주입받는 공개 `AssetStorageService`.
- `service/settings.py`: 기존 프로젝트 방식대로 환경 변수를 읽어 타입 설정을 구성하는 `load_asset_storage_settings`.
- `service/factory.py`: 선택한 어댑터를 한 번 생성해 서비스에 주입하는 `create_asset_storage_service`.
- `adapters/test_local_storage/adapter.py`: 테스트·수동 개발 전용 파일시스템 구현.
- `adapters/s3_storage/adapter.py`: boto3를 사용하는 실제 Amazon S3 구현.
- `example.py`: 앱 시작 코드와 독립된 설정 → 팩토리 → 서비스 실행 예제.

## 공개 인터페이스

`AssetStorageAdapter`와 `AssetStorageService`는 아래 비동기 계약을 공유한다.

- `store_asset(StoreAssetCommand) -> StoredAssetInfo`
- `read_asset(ReadAssetCommand) -> AssetReadInfo`
- `get_asset_metadata(GetAssetMetadataCommand) -> AssetMetadataInfo`
- `delete_asset(DeleteAssetCommand) -> None`
- `aclose() -> None`

`StoredAssetInfo`와 `AssetMetadataInfo`는 `storage_kind`, `storage_id`, 논리 `object_key`, `size_bytes`, `content_type`를 제공하고 가능한 경우 `etag`, `last_modified`도 제공한다. `storage_kind`는 구현 종류(`test_local`, `s3`)이고 `storage_id`는 같은 종류 안에서 위치/버킷을 구분하는 배포자가 정한 논리 식별자다. 영구 참조는 이 세 값으로 구성할 수 있으며 접근 URL과는 별개다. 어떤 어댑터도 경로나 공개/서명 URL을 반환하지 않는다.

저장 입력은 현재 위치부터 읽는 binary stream과 호출자가 아는 `size_bytes`를 받는다. 따라서 큰 파일을 공통 계약에서 `bytes` 하나로 복제하지 않는다. 호출자가 입력 stream의 수명과 닫기를 책임진다. seek 가능한 S3 입력과 모든 로컬 입력은 선언 크기를 검증한다. S3의 non-seekable 입력은 복사 없이 전송하기 위해 선언 크기를 호출자의 계약으로 신뢰한다.

`read_asset`은 전체 내용을 즉시 적재하지 않고 `AssetReadInfo.read(size)`로 읽는다. 호출자는 `async with await service.read_asset(...)`를 사용해 공급자 중립 reader가 반드시 닫히게 한다.

## 공통 객체 키와 동작 계약

객체 키는 `/`로 구분한 상대 논리 키다. 빈 키/구간, `.`/`..`, 절대 경로, 역슬래시, 제어 문자, Windows 비호환 문자·예약 이름, 끝의 공백/점, 내부 예약 첫 구간 `.asset_storage`를 거부한다. 최대 길이는 UTF-8 1024바이트이며 S3 prefix를 합친 실제 키도 같은 제한을 받는다. 이 이식 가능한 부분집합을 두 어댑터에 똑같이 적용한다.

- 같은 키 저장: 마지막으로 **성공한** 저장이 이전 객체와 콘텐츠 타입을 대체한다.
- 없는 키 읽기/메타데이터: `AssetNotFoundError`.
- 없는 키 삭제: 성공하는 멱등 연산이며 `None`을 반환한다.
- 실패: 빈 내용이나 성공값으로 바꾸지 않고 예외를 전달한다.

test_local은 루트를 먼저 resolve하고 모든 데이터 경로가 그 안인지 다시 확인한다. 콘텐츠는 같은 디렉터리의 임시 파일에 쓰고 길이와 flush/fsync를 확인한 뒤 `os.replace`한다. 작은 내부 sidecar에 콘텐츠 타입과 해시를 보관하며 실패 시 임시 파일을 제거하고 기존 정상 객체/메타데이터를 복원한다. 로컬 절대 경로는 공개 결과에 포함하지 않는다.

S3는 `key_prefix/object_key`에 저장하며 ACL이나 공개 버킷을 설정·가정하지 않는다. `upload_fileobj`의 관리형 multipart 전송을 사용하므로 큰 파일을 메모리에 통째로 적재하지 않는다. S3가 제공하지 않는 업로드 직후 ETag/수정 시각을 얻기 위한 추가 HEAD 요청은 하지 않으며, 이 두 필드는 저장 결과에서 `None`일 수 있다. 이후 메타데이터 조회/읽기 결과에는 S3 응답 값을 포함한다. 공급자별 이 차이를 가짜 공통 동작으로 숨기지 않는다.

## 설정과 조립

`AssetStorageSettings`는 실행 환경과 저장소 선택을 분리하고, 선택별로 `TestLocalStorageSettings` 또는 `S3StorageSettings`를 가진다. `load_asset_storage_settings()`가 읽는 값은 다음과 같다.

| 환경 변수 | 의미 |
|---|---|
| `ENVIRONMENT` | `test`, `local`, `development`, `staging`, `production` (`prod` 별칭 허용) |
| `ASSET_STORAGE_KIND` | 필수. `test_local` 또는 `s3` |
| `ASSET_STORAGE_ID` | 논리 저장소 식별자. S3는 필수, test_local 기본 `test-local-default` |
| `ASSET_TEST_LOCAL_ROOT` | test_local 루트. 기본 Windows 절대 경로 `C:\testChatData` |
| `ASSET_S3_BUCKET`, `ASSET_S3_REGION` | S3 선택 시 필수 |
| `ASSET_S3_KEY_PREFIX` | 선택적 공통 키 prefix |
| `ASSET_S3_CONNECT_TIMEOUT_SECONDS` | 기본 5초 |
| `ASSET_S3_READ_TIMEOUT_SECONDS` | 기본 60초 |
| `ASSET_S3_MAX_ATTEMPTS` | 최초 요청을 포함한 SDK 최대 시도 횟수, 기본 3 |

`production`에서 `test_local` 선택은 설정 생성 시 즉시 거부한다. 테스트 환경에서는 두 종류 모두 선택할 수 있다. 선택한 종류의 필수 설정과 숫자 범위도 초기화 전에 검증한다.

조립 단계는 설정을 한 번 읽고 `create_asset_storage_service(settings)`를 한 번 호출한 뒤 서비스를 재사용한다. 요청마다 클라이언트를 만들지 않는다. 팩토리가 boto3 client를 만들면 `AssetStorageService.aclose()`가 닫고, 테스트나 상위 조립 코드가 `s3_client=`로 주입한 client는 호출자가 닫는다. `example.py`가 독립 실행 흐름을 보여준다.

boto3를 선택한 이유는 Amazon의 Python SDK로서 실제 multipart S3 I/O, 표준 AWS 자격 증명 탐색(환경, shared config, workload/instance role 등), botocore timeout/retry 정책을 제공하기 때문이다. 동기 boto3 호출 전체는 `asyncio.to_thread`에서 실행해 비동기 서버 event loop를 막지 않는다. 모듈 자체는 추가 retry loop를 두지 않으며 botocore의 standard retry와 timeout만 전송 계층 정책을 소유한다. 비밀값 설정 필드는 만들지 않았고 예제/로그에도 자격 증명을 기록하지 않는다. S3 실패 시 test_local로 전환하지 않는다.

## 오류 처리

`AssetStorageError`는 `kind`, `operation`, `object_key`, `retryable`, 선택적 `status_code`/`request_id`를 가진다. `AssetStorageErrorKind`는 `not_found`, `access_denied`, `connection`, `timeout`, `invalid_request`, `data_integrity`, `provider`를 구분한다. 미존재는 전용 `AssetNotFoundError`다. 객체 키와 호출 입력 오류는 `ValueError`/`TypeError`, 초기화 설정 오류는 `AssetStorageConfigurationError`다.

S3의 대표 NoSuchKey/404, 자격 증명·AccessDenied, 연결, timeout, 4xx, 5xx를 공급자 중립 오류로 변환한다. 알 수 없는 응답이나 손상된 로컬 sidecar도 성공으로 숨기지 않는다. 호출자는 `retryable`을 상위 작업 재시도 판단에 쓸 수 있지만, 이미 SDK가 수행한 전송 재시도와 중복되지 않도록 유스케이스 수준에서 결정해야 한다.

## 검증

네트워크와 AWS 자격 증명이 필요 없는 테스트:

```powershell
cd apps/api
..\..\.venv\Scripts\python.exe -m pytest tests/test_asset_storage.py -q
```

실제 AWS 테스트는 `RUN_ASSET_STORAGE_S3_INTEGRATION=1`과 S3 설정을 명시한 경우에만 실행된다. 매 실행마다 `ASSET_S3_KEY_PREFIX/cod-integration/<uuid>`를 만들고 그 아래 자신이 생성한 객체 하나만 삭제한다.

```powershell
$env:RUN_ASSET_STORAGE_S3_INTEGRATION='1'
..\..\.venv\Scripts\python.exe -m pytest tests/test_asset_storage_s3_integration.py -q
```

## 확장과 현재 제약

새 공급자를 추가할 때는 `AssetStorageAdapter`를 구현하는 adapter와 필요 설정을 추가하고, `StorageKind`, `AssetStorageSettings`, 환경 loader, `create_asset_storage_service`의 선택 분기 및 공통 계약 테스트 fixture를 갱신한다. 공급자 고유 capability(URL, 보존 정책, 버전 ID 등)가 필요하면 현재 공통 메서드에 억지로 섞지 말고 별도 공개 capability와 명확한 지원 검사를 설계한다.

이 모듈은 DB·마이그레이션을 만들지 않고 기존 파일 참조도 변경하지 않는다. character가 `character_media`와 원본/스냅샷의 참조를 소유한다. 저장소 설정을 test_local에서 S3로 바꾸는 것은 새 업로드의 대상만 바꾸며 기존 파일을 이전하거나 동기화하지 않는다. 기존 저장소는 `create_app(asset_read_settings=...)`의 명시적 설정으로 함께 조립할 수 있으며, 기록된 저장소가 없으면 다른 저장소로 대체하지 않고 실패한다. 같은 storage_id를 다른 root/bucket/prefix에 재사용하면 안 된다.
