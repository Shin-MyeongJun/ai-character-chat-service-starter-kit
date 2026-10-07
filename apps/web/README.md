# 모서리 프런트 프로토타입

홈 → 작품 상세 → 시작 설정 → 채팅을 볼 수 있는 Next.js 프런트다. 샘플 작품은 화면 시연용이며 서버·AI·크레딧을 사용하지 않는다. 실제 작품 UUID가 설정되면 같은 상세·채팅 화면에서 API를 호출한다.

## 화면 시연

저장소 루트에서 Node.js 22와 pnpm 11을 준비한 뒤:

```powershell
pnpm install
pnpm web:dev
```

브라우저에서 <http://localhost:3000>을 연다. 표지·작품명·시연 대화는 자체 제작 샘플이다. 시연 메시지는 현재 브라우저의 로컬 저장소에 남는다.

데스크톱은 좁은 왼쪽 레일의 버튼으로 최근 대화 사이드바를 펼친다. 펼치면 전체 높이에서 최근 대화 표지와 최신 메시지를 보고, 발견·둘러보기·검색은 상단 바에서 이용한다. 모바일은 하단 메뉴의 **내 대화**에서 같은 목록을 본다. 현재 API에 대화 상대·작품 이미지와 서버 대화 목록 계약이 없어 샘플 표지 또는 기본 표지 이미지를 사용하며, 목록은 이 브라우저에만 저장된다.

## 제작 스튜디오 시연

`/studio`에서 제작 스튜디오를 연다. 서비스 상단 메뉴와 모바일 메뉴에도 진입 링크가 있다. 사용자 제공 Figma PNG와 저장된 생성 코드를 기준으로 구성한 화면이며, 작품 개요·캐릭터·시작 장면·기본/고급 로어 편집과 폴더·태그 검색을 제공한다. 화이트·다크 테마를 지원하고 모바일에서는 자료/편집/미리보기를 하단 메뉴로 전환한다.

전체 초안은 `chat-kit-studio-draft-v2` 키로 현재 브라우저에 자동 저장된다. 기존 v1 로어 초안은 보존하며 이전한다. 이미지 파일은 IndexedDB에 별도로 저장하므로 JSON과 함께 원본 파일도 보관해야 한다. 태그와 활성화 키워드는 별도 입력이다. **테스트**는 선택한 시작 장면 미리보기와 로컬 키워드 확인이며 AI를 호출하지 않는다. 비공개 설정·토큰 예산·삽입 위치는 저장만 한다. **발행**은 초안 검토 화면이고 서버 발행은 아직 연결하지 않았다.

로어 미리보기와 초안 복원의 검증:

```powershell
node --test apps/web/tests/studio-preview.test.cjs apps/web/tests/studio-project.test.cjs
```

구현 범위와 검증 결과는 [제작 스튜디오 구현 기록](../../docs/creator-studio-implementation.md)에 정리했다.

## 실제 API 연결 방법

API가 `http://127.0.0.1:8000`에서 실행 중인 경우 Next.js는 `/backend/*`를 API에 전달한다. 다른 주소라면 `apps/web/.env.example`을 `apps/web/.env.local`로 복사해 `CHAT_KIT_API_URL`을 바꾼다. 다음 항목도 준비한다.

1. API의 `DATABASE_URL`, 인증 키·메일 설정, 최신 Alembic 마이그레이션을 준비한다.
2. API 환경에 `CORS_ORIGINS=http://localhost:3000`을 포함한다. 브라우저의 Origin을 인증 CSRF 검사가 확인한다. 로컬 HTTP에서는 `AUTH_SECURE_COOKIES=false`가 필요하다.
3. 발행된 작품, 사용 가능한 모델, 가격표(`BILLING_PRICING_CONFIG_PATH`), 사용자 크레딧을 준비한다. 그렇지 않으면 답변 요청이 설정/잔액 오류로 종료될 수 있다.
4. 발행 작품 UUID를 `NEXT_PUBLIC_FEATURED_PRODUCT_IDS`에 쉼표로 구분해 넣고 Next 개발 서버를 다시 실행한다. 홈의 **연결된 작품** 영역에서 진입한다.
5. `/login`에서 기존 인증 계정으로 로그인한다. 새 계정 가입 화면은 아직 구현되지 않았으므로 서버에서 기존 계정을 준비해야 한다.

로그인 쿠키는 브라우저의 HttpOnly 쿠키를 사용하며 프런트는 Access/Refresh 토큰을 저장하지 않는다. CSRF 토큰은 `/auth/csrf` 응답으로 받아 상태 변경 요청 헤더에 넣는다.

현재 공개 작품 카탈로그와 내 대화 목록 HTTP API는 없다. 샘플 작품과 연결된 작품은 화면에서 구분되며, 내 대화 목록은 **이 브라우저에서 시작한 대화만** 표시한다. 실제 채팅은 `GET /conversations/{id}/start`, 메시지 저장/조회, 비스트리밍 답변 API를 사용한다. 결과가 불확실한 답변은 같은 요청 키로 확인하도록 세션 저장소에 요청 정보를 보관한다.

## 확인

```powershell
pnpm web:typecheck
pnpm web:build
```

프런트 구현 범위와 이후 API 보강은 [프런트 프로토타입 계획](../../docs/frontend-prototype-plan.md)에 정리했다.
