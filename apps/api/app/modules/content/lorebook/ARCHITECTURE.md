# Lorebook 모듈

- 소유 테이블: `lorebooks`, `lorebook_entries`, `lorebook_snapshots`.
- `service/query.py`: 소유자 조회, 시작 항목 조회, 활성 항목 선택, 발행용 소스 잠금·스냅샷 조회. 키워드 업무 판단은 EntryInfo로 변환한 뒤 실행한다.
- `service/command.py`: 원본·항목 생성/수정/삭제, 상태 변경, `freeze_lorebook`. 입력은 Command, 생성·수정 결과는 Info, 삭제 결과는 None이다. 미존재 삭제는 기존 오류를 유지한다.
- `service/util/matching.py`: 정규식 검증·매칭 보조 함수. 독립된 조회/쓰기 유스케이스를 담지 않는다.
- `repository.py`: 원본과 스냅샷 저장, `LorebookPageRow` 및 `LorebookEntryPageRow` 구성. Entity 생성·필드 변경은 이곳에서 수행한다.
- `mapper/persistence.py`: 원본/페이지/스냅샷의 순수 변환. 활성화 판단과 정규식 실행을 포함하지 않는다.
- `router.py`: 소유자 관리용 HTTP 경로. 관리자 조회와 모더레이션 경로는 각각 governance/admin과 governance/moderation에 있다.

## 경계와 특이 계약

외부 모듈은 공개 service/types만 가져온다. product는 공개 소스 잠금, 시작 항목, freeze 서비스를 통해 발행하며 타 모듈 ORM을 읽지 않는다. 인가 JOIN 예외는 없다.

이미 인가된 lorebook ID 목록을 받는 활성화 함수는 별도 소유자 필터를 추가하지 않는다. 시작 항목은 채팅 프롬프트의 일반 활성 항목에 포함하지 않는다. 원본 변경 이후에도 발행된 스냅샷의 내용은 유지된다.

스냅샷과 원본의 수명 주기가 연결되므로 하나의 repository를 유지하고, 정규식 보조 함수만 util로 옮겼다. `schemas.py`·`dependencies.py`는 `app/http`의 공유 계약/훅을 재노출한다. DTO 클래스 이름, cursor 검증, HTTP 의존성 override와 기존 503 응답을 보존한다. 실제 DB/auth 연결은 아직 미구현이다.
