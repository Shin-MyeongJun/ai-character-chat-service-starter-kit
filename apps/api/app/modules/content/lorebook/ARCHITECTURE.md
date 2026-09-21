# Lorebook 모듈

- 소유 테이블: `lorebooks`, `lorebook_entries`, `lorebook_snapshots`.
- `service/query.py`: 소유자 조회, 시작 항목 조회, 활성 항목 선택, 발행용 소스 잠금·스냅샷 조회. 원본 키워드 업무 판단은 EntryInfo로 변환한 뒤 실행한다. `activate_snapshot_entries(ActivateSnapshotEntriesCommand)`는 전달된 LorebookSnapshotInfo와 text만 사용하는 동기 공개 서비스이며 ActivatedSnapshotEntriesInfo를 반환한다.
- `service/command.py`: 원본·항목 생성/수정/삭제, 상태 변경, `freeze_lorebook`. 입력은 Command, 생성·수정 결과는 Info, 삭제 결과는 None이다. 미존재 삭제는 기존 오류를 유지한다.
- `service/util/matching.py`: 정규식 검증·매칭 보조 함수. 독립된 조회/쓰기 유스케이스를 담지 않는다.
- `repository.py`: 원본과 스냅샷 저장, `LorebookPageRow` 및 `LorebookEntryPageRow` 구성. Entity 생성·필드 변경은 이곳에서 수행한다.
- `mapper/persistence.py`: 원본/페이지/스냅샷의 순수 변환. 활성화 판단과 정규식 실행을 포함하지 않는다.
- `router.py`: 소유자 관리용 HTTP 경로. 관리자 조회와 모더레이션 경로는 각각 governance/admin과 governance/moderation에 있다.

## 경계와 특이 계약

외부 모듈은 공개 service/types만 가져온다. product는 공개 소스 잠금, 시작 항목, freeze 서비스를 통해 발행하며 타 모듈 ORM을 읽지 않는다. 인가 JOIN 예외는 없다.

이미 인가된 lorebook ID 목록을 받는 활성화 함수는 별도 소유자 필터를 추가하지 않는다. 시작 항목은 채팅 프롬프트의 일반 활성 항목에 포함하지 않는다. 원본 변경 이후에도 발행된 스냅샷의 내용은 유지된다.

스냅샷 활성화는 호출자가 인가·가용성을 확인한 스냅샷을 받으며 DB와 원본을 조회하지 않는다. enabled이며 start_set이 아닌 항목 중 always와 text에 매칭된 keyword만 선택한다. exact는 전체 텍스트 일치, contains는 부분 문자열, regex는 기존 안전한 정규식 매칭을 재사용한다. 키워드는 하나라도 매칭되면 활성화하고 빈 텍스트에서는 활성화하지 않는다. semantic/manual은 자동 선택하지 않으며 잘못된 활성화 유형이나 평가 중 잘못된 정규식은 오류로 전달한다. 반환 항목은 스냅샷 순서와 전체 필드를 보존한 깊은 복사본이다. 우선순위 정렬·토큰 예산·프롬프트 배치는 이 함수의 책임이 아니다.

원본과 스냅샷의 활성화는 같은 query에서 키워드 매칭 판단을 공유한다. 결과 복사는 persistence mapper에 두어 업무 선택과 구조 변환을 분리한다.

스냅샷과 원본의 수명 주기가 연결되므로 하나의 repository를 유지하고, 정규식 보조 함수만 util로 옮겼다. `schemas.py`·`dependencies.py`는 `app/http`의 공유 계약/훅을 재노출한다. DTO 클래스 이름, cursor 검증, HTTP 의존성 override와 미연결 훅의 503 응답을 보존한다. `app.main`은 DB 세션과 일반 소유자의 실제 쿠키 인증을 연결한다. character/lorebook 전용 관리자·검수 dependency는 기본 503 훅으로 남아 있다.

## 현재 구현 점검과 읽는 순서 (2026-09-17)

읽는 순서: http/contracts/lorebook → router → command/query → util/matching → repository → mapper. 발행본 활성화는 conversation의 command/context에서 호출하고 최종 prompt는 chatting/prompt가 만든다.

항목 본문 수정 시 기존 embedding을 지우거나 재생성하는 동작은 현재 command에 없다. semantic 자동 선택은 구현 범위 밖이다. title=None은 원본 스키마에서 허용되지만 상품 시작 옵션의 응답 계약과 충돌할 수 있어 F02에 기록했다. metadata 크기 제한은 문자 수가 아닌 직렬화한 UTF-8 바이트 수다.

관련 테스트: `test_lorebook_command`, `test_lorebook_query`, `test_lorebook_schema`, `test_lorebook_snapshot_activation`. 빈 함수가 아닌 미구현 기능과 단순 재노출 파일은 전체 목록에서 구분한다.

전체 파일 상태·발견 사항·검증은 [백엔드 점검 안내](../../../../../../references_document/backend_review/README.md)에 모았다.
