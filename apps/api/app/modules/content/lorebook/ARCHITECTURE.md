# Lorebook 모듈

- 태그 연결 소유 테이블: `lorebook_tags`, `lorebook_internal_tags`. 사전 `tags`는 content/tag 영역 소유이며 ORM은 `app/db/models/tag.py`에 분리한다. 공개 연결은 sort_order·assigned_by, 내부 연결은 source(admin/system)·assigned_by·갱신 시각을 기록한다. 같은 태그 ID를 양쪽에서 사용할 수 있다. 대상 삭제는 연결만 CASCADE, 연결된 사전 삭제는 RESTRICT, 부여 사용자 삭제는 SET NULL이다. 개수 제한·태그 snapshot은 없고 기존 API 응답/발행 snapshot 구조를 유지하며 태그 전용 서비스가 인가·활성 상태·관리자 지정 보호 정책을 검사한다.
- 소유 테이블: `lorebooks`, `lorebook_entries`, `lorebook_snapshots`.
- `service/query.py`: 소유자 조회, 시작 항목 조회, 활성 항목 선택, 발행용 소스 잠금·스냅샷 조회. 원본 키워드 업무 판단은 EntryInfo로 변환한 뒤 실행한다. `activate_snapshot_entries(ActivateSnapshotEntriesCommand)`는 전달된 LorebookSnapshotInfo와 text만 사용하는 동기 공개 서비스이며 ActivatedSnapshotEntriesInfo를 반환한다.
- `service/command.py`: 원본·항목 생성/수정/삭제, 상태 변경, `freeze_lorebook`. 입력은 Command, 생성·수정 결과는 Info, 삭제 결과는 None이다. 미존재 삭제는 기존 오류를 유지한다.
- `service/util/matching.py`: 정규식 검증·매칭 보조 함수. 독립된 조회/쓰기 유스케이스를 담지 않는다.
- `repository.py`: 원본과 스냅샷 저장, `LorebookPageRow` 및 `LorebookEntryPageRow` 구성. Entity 생성·필드 변경은 이곳에서 수행한다.
- `mapper/persistence.py`: 원본/페이지/스냅샷의 순수 변환. 활성화 판단과 정규식 실행을 포함하지 않는다.
- `router.py`: 소유자 관리용 HTTP 경로. 관리자 조회와 모더레이션 경로는 각각 governance/admin과 governance/moderation에 있다.

## 경계와 특이 계약

### CRUD 타입·명명 정리 (2026-10-26)

`repository.py`, `service/command.py`, `service/query.py`, `mapper/` 전체를 엄격 품질
검사 범위에 포함한다. 저장소의 생성·수정은 Lorebook/LorebookEntry, 삭제는 None,
발행은 LorebookSnapshot을 반환한다. 세션·UUID 목록·잠금 플래그·태그 연결의 입력과
mapper의 Entity/Info 목록 타입을 명시해 서비스 반환에 미주석 Any가 전파되지 않게 한다.

Info를 순회하는 변수는 entry_info, 사전은 tags_by_id, 연결 순서는 sort_order로 표현한다.
기존 공개 함수 인자와 LorebookSchemaMapper 클래스는 호출 호환을 위해 유지한다.
태그 대상 조회는 같은 SQL과 populate_existing/잠금 옵션으로 첫 행 또는 None을 반환한다.
기존 페이지·정렬·검증·트랜잭션·embedding 보존 및 metadata 얕은 복사/스냅샷 깊은 복사는 유지한다.

당시 진단 결과와 활성 스냅샷 mapper의 dict는 이 경계에서 키를 해석하지 않고 전달·복사하므로
`dict[str, object]`로 표현한다. 이는 JSON 필드별 타입 검증 완료를 뜻하지 않는다.
`types.py`의 스냅샷 구조, `service/activation.py`, `service/tags.py`와 HTTP 라우터 등은
엄격 검사 확대가 남은 별도 범위다. 로어북 전체나 활성화 정책 수정 완료로 간주하지 않는다.

외부 모듈은 공개 service/types만 가져온다. product는 공개 소스 잠금, 시작 항목, freeze 서비스를 통해 발행하며 타 모듈 ORM을 읽지 않는다. 인가 JOIN 예외는 없다.

이미 인가된 lorebook ID 목록을 받는 활성화 함수는 별도 소유자 필터를 추가하지 않는다. 시작 항목은 채팅 프롬프트의 일반 활성 항목에 포함하지 않는다. 원본 변경 이후에도 발행된 스냅샷의 내용은 유지된다.

스냅샷 활성화는 호출자가 인가·가용성을 확인한 스냅샷을 받으며 DB와 원본을 조회하지 않는다.
enabled이며 start_set이 아닌 항목을 검사한다. 기존 옵션 없는 항목은 저장 순서와
always/keyword 규칙을 유지한다. exact는 전체 텍스트 일치, contains는 부분 문자열,
regex는 기존 안전한 정규식 매칭이다. semantic은 자동 선택하지 않고 manual은 허가된
스냅샷 안의 명시된 ID만 선택한다. v1 activation_options가 있으면 우선순위·order·ID 정렬,
메시지 깊이/화자 필터, any/all 키워드·대소문자·단어 경계, UTF-8 바이트 추정 항목 예산과
배타 그룹을 적용한다. 반환 항목은 전체 필드를 보존한 깊은 복사본이다. 이 설명은 기존
activation 구현을 반영한 문서 보완이며 이번 타입 정리에서 활성화 정책을 추가한 것이 아니다.

원본과 스냅샷의 활성화는 같은 query에서 키워드 매칭 판단을 공유한다. 결과 복사는 persistence mapper에 두어 업무 선택과 구조 변환을 분리한다.

스냅샷과 원본의 수명 주기가 연결되므로 하나의 repository를 유지하고, 정규식 보조 함수만 util로 옮겼다. `schemas.py`·`dependencies.py`는 `app/http`의 공유 계약/훅을 재노출한다. DTO 클래스 이름, cursor 검증, HTTP 의존성 override와 미연결 훅의 503 응답을 보존한다. `app.main`은 DB 세션과 일반 소유자의 실제 쿠키 인증을 연결한다. character/lorebook 전용 관리자·검수 dependency는 기본 503 훅으로 남아 있다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: http/contracts/lorebook → router → command/query → util/matching → repository → mapper. 발행본 활성화는 conversation의 command/context에서 호출하고 최종 prompt는 chatting/prompt가 만든다.

항목 본문 수정 시 기존 embedding을 지우거나 재생성하는 동작은 현재 command에 없다. semantic 자동 선택은 구현 범위 밖이다. title=None은 원본 스키마에서 허용되지만 상품 시작 옵션의 응답 계약과 충돌할 수 있어 F02에 기록했다. metadata 크기 제한은 문자 수가 아닌 직렬화한 UTF-8 바이트 수다.

관련 테스트: `test_lorebook_command`, `test_lorebook_query`, `test_lorebook_schema`, `test_lorebook_snapshot_activation`. 빈 함수가 아닌 미구현 기능과 단순 재노출 파일은 전체 목록에서 구분한다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.


## 현재 태그 관리

생성 Command/DTO의 선택 tags로 공개 태그를 생성 트랜잭션에 함께 연결한다. 미지정/빈 목록은 기존 생성 동작이다. 공개 태그 전용 API는 조회·추가·전체 교체/정렬·해제를 제공한다. 연결을 제거해도 사전 항목은 남는다. 태그 수정은 현재 연결에 즉시 반영하고 발행 snapshot에는 넣지 않는다.

`service/tags.py`는 부모 잠금·인가·트랜잭션 및 사전 공개 service 호출을 소유한다. `mapper/tags.py`는 연결 Entity → 값, 사전 Info와의 조합만 담당한다. `mapper/tag_schema.py`는 HTTP 요청/응답 변환이다. 연결 SQL은 해당 모듈 repository에 있고 tags 테이블을 직접 읽거나 JOIN하지 않는다. 내부 쓰기는 admin/system 출처를 분리하고 관리자 source를 시스템이 덮어쓰거나 제거하지 못한다. 시스템 Command는 신뢰된 애플리케이션 호출 전용이며 HTTP에 노출하지 않는다. 관리자는 identity.require_admin으로 재검증한다. 공개 응답에는 내부 태그가 포함되지 않는다.

공개 태그 HTTP는 기존 /me 콘텐츠 조회와 같은 소유자 정책이다. 일반 소유자 라우터와 관리자 내부 태그 라우터는 분리한다. 기존 생성·상세 응답의 구조는 바꾸지 않는다.

API 경로·예제·검증은 [태그 관리](../../../../../../references_document/reference/content-tags.md)에 정리했다.

## 태그·활성화·스냅샷 타입 정리 (2026-10-27)

service/tags.py, service/activation.py, types.py를 엄격 검사 범위에 추가했다.
태그는 character와 같은 AsyncSession/Command/Info 및 관리자·시스템 overload 패턴을
적용한다. 기존 부모 잠금·관리자 검증·지정 보호·트랜잭션 정책은 유지한다.

스냅샷 항목, 본문, 활성화 옵션과 진단 결과를 TypedDict로 표현한다. 스냅샷 본문의
entries는 필수이며 title/description과 과거 항목의 선택 필드는 기존 누락 가능성을
유지한다. 기존 확장 필드를 삭제하거나 JSON을 재직렬화하지 않는다. mapper는 계속
깊게 복사하며 활성화 결과는 원본 및 전달된 Info와 중첩 가변 값을 공유하지 않는다.

cast는 세 경계에 근거를 둔다. 공유 JSONB mixin에서 도메인 저장 필드로 읽는 mapper,
기존 검증과 기본값 보완을 마친 옵션, 초안의 id만 제거한 생성 Command 필드다.
첫 번째는 저장소의 스냅샷 계약을 표현하며 버전별 런타임 검증을 추가하지 않는다.
초안의 알 수 없는 키는 기존 **kwargs 경로와 같이 TypeError로 거절한다. 버전 검사의
기존 값 비교는 1.0/True도 허용하므로 임의로 정수 전용 검증으로 바꾸지 않는다.
잘못된 저장 데이터의 기존 오류 경로와 기존 metadata의 동적 값 경계는 남아 있다.

test_lorebook_snapshot_activation의 추가 회귀는 옵션 호환성·입력 비변경, 불리언/정수
혼동 및 알 수 없는 옵션 거절, mapper→활성화의 선택 필드/확장 필드 보존·깊은 복사,
초안의 알 수 없는 생성 필드 거절을 확인한다. HTTP 라우터/조립 의존성 전체는 다음 범위다.

## HTTP 경계 타입 정리 (2026-10-27)

lorebook 디렉터리 전체와 http/lorebook_dependencies.py, http/contracts/lorebook.py를
엄격 검사 범위에 추가했다. schemas/dependencies의 호환 재노출, constraints 및 matching
보조 함수도 직접 검사한다. 다른 HTTP/DB 의존 파일 전체의 검증 완료를 의미하지 않는다.

태그 조회·추가·교체는 list[PublicTagResponseDto], 삭제는 None을 반환한다고 명시한다.
일반 라우터의 요청 지역 변수는 command로 맞췄다. 기존 경로·공개 인자명·DTO·인증 함수,
dependency override 호환과 204 빈 본문을 유지한다. 일반 오류의 고정 문구와 태그 공유
오류의 상세 문구, 미설정 DB/인증 의존성의 503 동작도 유지한다.

test_lorebook_http는 태그 4개 경로의 응답, 신뢰된 owner/session 전달, OpenAPI의 204
본문 부재, 404/422 오류 번역, 미설정 DB/owner 각각의 503 및 서비스 미호출을 확인한다.
서비스 mock을 사용하는 HTTP 계약 검증이며 실제 DB·외부 서비스 연동 검증은 아니다.
