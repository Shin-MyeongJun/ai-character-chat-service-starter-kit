# 모서리 U19 a5 스튜디오 이미지 편집 초안

개발 서버에서 `/dev/studio-images`를 연다. 기존 캐릭터·로어북·시작 장면 편집기와 스튜디오 버튼, 입력 필드, 다이얼로그를 재사용한다. 예시 편집값과 로컬 파일 미리보기는 페이지 메모리에 있다.

## 변경 파일

| 파일 | 변경 |
| --- | --- |
| `apps/web/app/dev/studio-images/page.tsx` | 개발 전용 예시 경로 |
| `apps/web/components/studio/studio-image-example.tsx` | 예시 이미지, 파일 선택 처리, 첫 장면과 발행 미리보기 |
| `apps/web/components/studio/studio-image-editor.tsx` | 표정·상황 이미지 편집, 첫 장면 선택, 발행 앨범 목록 |
| `apps/web/components/studio/character-editor.tsx` | 이미지·에셋 탭의 선택적 이미지 영역 |
| `apps/web/components/studio/lore-editor.tsx` | 내용 탭의 선택적 이미지 영역 |
| `apps/web/components/studio/project-editors.tsx` | 장면 내용 탭의 선택적 이미지 영역 및 예시용 장면 미리보기 동작 |
| `apps/web/components/studio/studio.module.css` | 예시 화면 레이아웃 |

## a1·a4 연결 지점

- **이미지 목록과 편집** — 상위 편집기에서 소유 항목과 분류를 확정한 뒤 `StudioImageGroup`에 표시용 ID, 이름, 미리보기 URL을 전달한다. 캐릭터는 표정과 상황 그룹을, 로어북은 상황 그룹을 렌더링한다. `onAdd(file)`는 새 항목 추가 의도, `onReplace(imageId, file)`는 해당 항목의 이미지 교체 의도, `onLabelChange(imageId, label)`는 표시 이름 변경 의도다. 요청 중 상태와 오류는 `busy`와 `error`로 돌려준다. 교체 예시에서는 ID와 이름을 유지하므로 첫 장면 참조가 새 이미지를 표시한다.
- **첫 장면** — `StudioOpeningImage`에 해당 장면에서 선택할 수 있는 기존 이미지와 삽입 위치 선택지를 전달한다. `onChange`는 이미지·위치 선택 또는 삽입 해제(`null`)를 전달한다. 이미지 선택 직후 위치는 미선택일 수 있다. 예시 위치는 도입 대사 앞·뒤이며 실제 위치 ID와 저장 방식은 연결 단계에서 결정한다.
- **발행 미리보기** — 일반 편집 경로를 연결할 때 발행 검토 다이얼로그에서 `StudioAlbumPreview`에 포함 판정이 끝난 목록을 전달한다. 각 항목은 이미지와 출처 표시 이름을 담는다. 예시에서는 야간 근무 이미지를 제외하고 새로 추가한 이미지를 포함해 목록 차이를 확인할 수 있다.

표시용 타입과 콜백은 화면 경계다. 다음 작업에서 a1·a4 계약으로 초안 저장·복원, 실제 업로드·발행, 일반 작품 편집 진입점을 연결한다. 저장 후 재접속 검증까지 마친 뒤 a5 최종 커밋을 만든다.

## 검증

- `pnpm web:typecheck` 통과. 워크트리에서 기존 로컬 의존성을 연결하고 이 명령에 한해 pnpm의 자동 재설치 검사를 껐다.
- 기존 스튜디오 프로젝트·미리보기·워크스페이스 테스트 12개 통과.
- 브라우저에서 예시 PNG 교체와 추가, 로어북 상황 전용 화면, 선택 이미지의 도입 대사 뒤 배치, 발행 앨범 포함 목록 확인.
