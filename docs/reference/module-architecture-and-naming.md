# 모듈 아키텍처 & 명명 규칙

> 신규 모듈 작성 및 기존 모듈 리팩터링의 기준 문서다.
> 기존 문서의 구조 원칙과 명명 규칙에 모듈 경계, Row 전달, 업무 판단, 트랜잭션 및 파일 분리 기준을 반영했다.
> 신규 코드에는 즉시 적용한다. 기존 위반 코드는 관련 파일을 수정할 때 점진적으로 교정하며, 무관한 코드까지 일괄 변경하지 않는다.

---

## Part 1. 구조 원칙

### 0. 전체 구조

모듈은 router · service · repository · mapper · types를 중심으로 구성한다. schemas는 HTTP 입출력 타입을, dependencies는 실행 의존성 연결을 담당한다.

```text
module/
  __init__.py
  ARCHITECTURE.md
  types.py                 # 또는 types/
  schemas.py               # 또는 schemas/
  dependencies.py
  repository.py            # 또는 repository/
  mapper/
    __init__.py
    persistence.py         # 또는 persistence/
    schema.py              # 또는 schema/
  service/
    __init__.py
    command.py             # 또는 command/
    query.py               # 또는 query/
    views.py               # 또는 views/, 필요할 때만 생성
    util/                  # 내부 보조 함수가 필요할 때만 생성
  router.py                # 또는 router/, HTTP 노출 시에만 생성
```

사용하지 않는 계층이나 빈 파일을 형식적으로 만들지 않는다. router가 없는 모듈에는 HTTP 전용 schemas/dependencies를 요구하지 않는다.

#### 0.1 호출 방향

```text
router → service → repository
router → mapper/schema
service → mapper/persistence
```

- service가 router를 호출하거나 router가 repository를 직접 호출하는 것은 금지한다.
- mapper는 조회나 업무 실행을 수행하지 않는 순수 변환 계층이다. 입력 타입을 참조할 수 있지만 router·service·repository의 실행 함수를 호출하지 않는다.
- types는 router·service·repository·mapper·schemas에 의존하지 않는다. 공개 types에 ORM Entity나 Row를 포함하지 않는다.
- dependencies는 session/auth 등의 의존성을 연결한다. 비즈니스 로직이나 우회적인 repository 호출을 넣지 않는다.

#### 0.2 모듈 간 공개 경계

- 다른 모듈에서는 **공개 service와 공개 types만** 참조한다.
- 다른 모듈의 repository·mapper·ORM 모델·schemas·내부 보조 함수는 직접 참조하지 않는다.
- 공개 service의 입력과 반환 타입에도 이 경계를 적용한다. Row/Entity를 타 모듈에 전달하지 않는다.
- `service/views`는 다른 모듈의 공개 service에서 받은 Info/View를 자기 모듈 mapper에 전달하여 조합한다.
- HTTP 라우터를 등록하는 애플리케이션 조립 코드는 router를 가져올 수 있다. 이는 업무 모듈 간 호출과 구분한다.
- repository의 인가 스코핑 JOIN은 §C의 제한된 예외를 따른다.

### A. Router

1. REST API 요청을 받고 응답한다.
2. 입력은 schemas의 RequestDto, 출력은 ResponseDto를 기본으로 한다. 응답 본문이 없는 엔드포인트는 DTO 없이 반환할 수 있다.
3. schema mapper로 RequestDto를 Command로 변환하고 service를 호출한다. 반환된 Info/View는 schema mapper로 ResponseDto로 변환한다.
4. 비즈니스 로직과 DB 접근을 수행하지 않는다. Row/Entity는 router에 도달해서는 안 된다.
5. 엔드포인트가 많아지면 동일 접근 주체 안에서 기능별로 router/를 나눌 수 있다.
6. 접근 주체가 다른 라우팅(일반 사용자와 관리자/모더레이터 등)은 별도 모듈로 분리한다. 관리 기능도 다른 도메인의 공개 service를 통해 접근한다.

### B. Service

1. 유스케이스 실행과 비즈니스 판단을 담당한다.
2. 역할에 따라 다음과 같이 구분한다.
   - `command`: 생성·수정·삭제 등 상태를 변경하는 유스케이스.
   - `query`: 자기 모듈의 데이터로 해결하는 조회.
   - `views`: 다른 모듈의 공개 service 결과를 조합하는 조회.
3. **조회와 쓰기를 포함한 모든 업무 요청 입력은 Command**로 전달한다. DB session 같은 실행 의존성은 별도 인자로 전달할 수 있다.
4. 권한·존재 여부·상태 전이·업무 조건은 service가 판단한다. query도 단순 전달만 하는 계층으로 제한하지 않는다.
5. Row/Entity에 대한 업무 판단은 금지한다. 먼저 mapper를 통해 Info 등 내부 값으로 변환한 다음 판단한다.
6. views는 공개 service 결과를 수집하고 업무 조건을 판단한다. 최종 View의 구조적 조합은 mapper에 맡긴다.
7. 공개 service는 다른 모듈에서 사용할 수 있다. HTTP DTO, HTTP 상태 코드, 프레임워크 HTTP 예외에 의존하지 않는다.

#### B.1 반환 규칙

| 유스케이스 | 기본 반환값 |
|---|---|
| 자기 모듈 조회 | XxxInfo 또는 명시된 Info 목록/페이지 타입 |
| 다른 모듈과 조합하는 조회 | XxxView 또는 명시된 View 목록/페이지 타입 |
| 생성·수정 | 변경 후 리소스의 XxxInfo |
| 삭제 결과가 필요한 경우 | DeleteXxxInfo |
| 반환할 업무 결과가 없는 삭제 | None |

- 삭제 결과의 필드와 멱등성은 해당 유스케이스 계약에 명시한다. `deleted`가 실제 삭제 여부인지 요청 성공 여부인지 모호하게 두지 않는다.
- 공개 service는 Row/Entity를 직접 반환하거나 Info/View 내부에 포함하지 않는다.
- 반환 타입은 함수 시그니처에 명시한다.

### C. Repository

1. 모듈이 소유한 테이블의 조회와 쓰기를 담당한다. 소유 테이블은 모듈의 ARCHITECTURE.md에 기록한다.
2. 동일 모듈 안의 여러 쿼리 결과를 모아 raw 결과 묶음인 XxxRow를 반환할 수 있다. Info/View로의 변환은 수행하지 않는다.
3. 다른 모듈 테이블의 컬럼을 가져와 결과 데이터를 구성하는 JOIN은 금지한다. 모듈 간 데이터 조합은 공개 service와 views를 통해 수행한다.
4. **예외: 소유권·인가 스코핑 JOIN.** 타 모듈 컬럼을 반환 결과에 포함하지 않고 접근 범위를 제한하는 조건으로만 사용할 때 허용한다. 사용 테이블·관계·목적을 ARCHITECTURE.md에 기록한다. 이 예외는 다른 모듈의 repository/mapper를 호출할 권한을 부여하지 않는다.
5. repository는 업무 상태 전이나 HTTP 응답을 결정하지 않는다. service가 결정한 작업을 저장소에 반영한다.
6. commit/rollback을 임의로 수행하지 않는다. 필요한 flush는 허용하되 트랜잭션을 종료하지 않는다.

#### C.1 Row/Entity 전달과 소비 제한

- XxxRow는 repository.py 또는 repository/ 안에 정의하는 raw 캐리어다. 공개 types에 두지 않는다.
- repository는 Row/Entity를 구성하거나 저장소 작업에 사용할 수 있다.
- service는 repository 결과를 **같은 모듈의 persistence mapper에 전달하기 위해 임시 보유**할 수 있다.
- service에서 Row/Entity의 필드 접근·수정·조건 분기는 금지한다. `None` 여부 등 조회 결과에 대한 해석도 mapper가 처리한 후 service가 판단한다.
- mapper에 인자로 전달하는 것은 허용한다. 공개 service의 반환값으로 내보내는 것은 금지한다.
- router 및 다른 모듈에는 변환된 Info/View만 전달한다.
- mapper에서 ORM lazy loading으로 DB 조회가 발생해서는 안 된다. 필요한 데이터는 repository에서 미리 조회한다.

### D. Mapper

1. 이미 받은 데이터의 구조 변환과 조합을 담당하는 순수 함수로 작성한다.
2. `mapper/persistence`: 자기 모듈의 Row/Entity를 Info로 변환하거나, 공개 service에서 받은 Info/View들을 자기 모듈의 View로 조합한다.
3. `mapper/schema`: RequestDto → Command, Info/View → ResponseDto 변환을 담당한다.
4. DB/API 호출, service 호출, 권한 판단, 업무 상태 변경, 현재 시각 조회, 난수 생성은 금지한다. 필요한 값은 입력으로 받는다.
5. 입력 객체를 수정하지 않는다. 업무상 허용 여부나 기본값 정책은 service가 결정하고 mapper는 결정된 결과를 변환한다.
6. 조회 결과가 없는 경우 Row/Entity의 None을 내부 결과의 None으로 변환할 수 있다. 미존재를 오류로 볼지는 service가 판단한다.

### E. Types / Schemas

1. `types`: service의 업무 요청과 결과를 표현한다. DB 및 HTTP 표현과 분리한다.
   - `command`: 조회·쓰기 모두의 요청 값. GetProductCommand, ListProductsCommand, CreateProductCommand 등.
   - `result`: 자기 모듈 결과인 Info. 조회 결과뿐 아니라 생성·수정·삭제 결과도 포함한다.
   - `view`: 다른 모듈의 공개 결과를 조합한 View.
2. `schemas`: router의 RequestDto/ResponseDto를 정의한다.
3. XxxRow는 위 분류에 포함되지 않으며 repository에 둔다.
4. 필요하면 types/command/, types/result/, types/view/, schemas/로 나눈다.

### F. 트랜잭션과 오류 처리

#### F.1 트랜잭션

- 쓰기 트랜잭션은 최상위 유스케이스 단위로 관리한다. 최상위 service가 공통 트랜잭션 관리자 또는 Unit of Work를 통해 경계를 소유한다.
- 한 유스케이스에서 호출되는 내부 service와 repository는 진행 중인 트랜잭션에 참여하며 별도로 commit/rollback하지 않는다.
- 여러 모듈을 변경할 때 조율 service가 각 모듈의 공개 service를 호출하고, 동일 DB에서 원자성이 필요하면 같은 트랜잭션을 공유한다.
- 성공하면 최상위 관리 주체가 commit하고, 실패하면 rollback한다. flush는 commit이 아니다.
- 서로 다른 DB나 외부 API까지 하나의 DB 트랜잭션으로 원자성이 보장된다고 가정하지 않는다. 해당 유스케이스의 실패·재시도 정책을 별도로 명시한다.

#### F.2 오류

- repository의 단건 조회는 기본적으로 미존재 시 None, 목록 조회는 빈 목록을 반환한다. 별도 계약이 있으면 명시한다.
- mapper는 미존재 표현을 변환할 수 있지만 HTTP 오류나 업무상 미존재 예외를 결정하지 않는다.
- service가 변환된 결과를 보고 미존재·권한 부족·상태 충돌 등의 업무 예외를 결정한다. 선택적 조회라면 반환 타입에 None 허용을 명시한다.
- HTTP 상태 코드와 오류 DTO로의 변환은 router 또는 공통 예외 처리기가 담당한다.
- 예외를 숨기고 성공값이나 임의의 빈 결과를 반환하지 않는다. 저장소 오류를 업무 예외로 바꿀 때는 의미가 확인되는 오류만 변환한다.

### G. 폴더/파일 분리와 util

- **줄 수만으로 분리를 강제하지 않는다.** 동일한 책임과 밀접한 기능은 긴 파일에서도 함께 유지할 수 있다.
- 서로 다른 유스케이스·변경 이유·의존성이 한 파일에 섞이면 분리한다. 응집도와 탐색 편의성을 기준으로 판단한다.
- 독립된 업무 기능은 해당 계층의 기능 파일로 둔다. composition.py, publication.py 같은 유스케이스 파일을 util에 넣지 않는다.
- util/은 해당 계층의 내부 보조 함수에 사용한다. 계층별 접근 제한을 그대로 적용하고 다른 모듈에서 직접 참조하지 않는다.
- 재사용되지 않는 짧은 보조 함수는 해당 파일에 유지할 수 있다. util 생성을 강제하지 않는다.
- 분리 예:

```text
service/
  command/
    __init__.py
    composition.py
    publication.py
  query.py
  util/
    __init__.py
    validation.py
```

- 에이전트는 구조를 선택하고, 구조 변경 시 분리 또는 유지한 이유를 설명한다. 사용자가 결과를 검토한다.
- 각 모듈의 ARCHITECTURE.md에는 소유 테이블, 공개 service, 현재 파일별 책임, 주요 분리 이유, 인가 JOIN 예외, 유스케이스별 특이 계약을 간결히 기록한다.
- 기존 단일 파일을 폴더로 전환하면 같은 이름의 파일과 폴더를 동시에 유지하지 않는다. import와 문서 인덱스도 갱신한다.

### 전체 흐름 예시

다음은 데이터 전달 흐름이다. 실제 repository와 mapper의 호출 주체는 service다.

```text
[자기 모듈 조회]
router: RequestDto → schema mapper → Command
  → service/query
      → repository 조회 → Row/Entity
      → 자기 persistence mapper → Info
      → Info를 사용한 업무 판단
  → router: Info → schema mapper → ResponseDto

[다른 모듈과 조합하는 조회]
router → service/views
  → 각 모듈의 공개 service 호출 → Info/View
  → 업무 조건 판단
  → 자기 persistence mapper → 최종 View
router: View → schema mapper → ResponseDto

[쓰기]
router: RequestDto → schema mapper → Command
  → 최상위 service/command: 트랜잭션 시작
      → 조회가 필요하면 repository → mapper → Info
      → 권한·상태·업무 조건 판단
      → repository 쓰기/필요한 flush → mapper → Info
      → 성공 시 commit, 실패 시 rollback
  → router: Info → schema mapper → ResponseDto
```

---

## Part 2. 명명 규칙

### 1. 파일 및 import 별칭

- 파일명에는 계층 접미사를 반복하지 않는다. command.py, query.py, persistence.py 등을 사용한다.
- import 별칭은 **기능명(있는 경우) + 분류 + 구조** 순서다. 다른 모듈의 공개 service/types를 가져올 때는 모듈명을 앞에 붙인다.
- 구조: Service, Repository, Mapper, Types, Schemas, Router.
- 분류: Query, Command, Views, Persistence, Schema, Result, View 등.
- 분류가 없으면 구조만 사용한다. 같은 의미가 중복되는 이름은 반복하지 않는다.
- util 파일은 같은 모듈 안에서 `기능명 + 소속 계층 + Util` 별칭을 사용한다.

| 파일 | 같은 모듈 내부 별칭 | 다른 모듈에서의 별칭 |
|---|---|---|
| service/query.py | QueryService | ProductQueryService |
| service/command.py | CommandService | ProductCommandService |
| service/views.py | ViewsService | ProductViewsService |
| service/command/publication.py | PublicationCommandService | ProductPublicationCommandService |
| types.py | Types | ProductTypes |
| types/command/publication.py | PublicationCommandTypes | ProductPublicationCommandTypes |
| repository.py | Repository | 직접 참조 금지 |
| mapper/persistence.py | PersistenceMapper | 직접 참조 금지 |
| mapper/schema.py | SchemaMapper | 직접 참조 금지 |
| schemas.py | Schemas | 직접 참조 금지 |
| service/util/validation.py | ValidationServiceUtil | 직접 참조 금지 |
| router.py | Router | 업무 모듈에서 직접 참조 금지 |

```python
# 다른 모듈의 공개 인터페이스
from app.modules.content.product.service import query as ProductQueryService
from app.modules.content.product import types as ProductTypes

# 같은 모듈 내부
from app.modules.content.product import repository as Repository
from app.modules.content.product.mapper import persistence as PersistenceMapper
```

### 2. 함수명

- 기본 형식: `[_]행위_대상`.
- 선행 언더스코어 1개는 내부 전용 마커다. 업무 모듈 밖에서 호출하지 않는다. 단, 언더스코어가 없다고 repository/mapper가 모듈 간 공개 API가 되는 것은 아니다.
- 나머지 언더스코어는 스네이크케이스 단어 구분자다.
- 대상이 없는 save(), info(), owned(), to_info() 같은 이름은 금지한다.
- **mapper만 예외적으로 `[_]대상_출처_to_결과` 형식을 사용한다.** 여러 입력을 조합하면 출처 이름에 조합되는 입력의 의미를 드러낸다.

| 역할 | 예시 |
|---|---|
| 공개 service | create_lorebook_entry, get_product, list_products |
| 내부 보조 함수 | _validate_lorebook_profile, _get_owned_product |
| repository | save_product, get_product |
| schema mapper | product_request_to_command, product_info_to_response |
| persistence mapper | product_entity_to_info, product_row_to_info |
| 조합 mapper | product_author_infos_to_view |

### 3. Types / Schemas 클래스명

#### 3.1 Schemas

- 리소스 표현: `{Resource}ResponseDto`.
- 요청: `{Resource}RequestDto`, 액션을 구별해야 하면 `{Action}{Resource}RequestDto`.
- 액션 응답: **`{Action}{Resource}ResponseDto`**.
- 생성·수정 응답이 리소스를 포함하면 내부 필드에 해당 ResourceResponseDto를 사용한다.
- 예: CreateLorebookResponseDto의 lorebook: LorebookResponseDto.
- 삭제 결과를 반환하면 DeleteLorebookResponseDto의 deleted: bool 등 계약에 맞는 필드를 사용한다. 본문 없는 삭제 응답은 wrapper를 만들지 않는다.

#### 3.2 Types

| 이름 | 의미 |
|---|---|
| GetProductCommand / ListProductsCommand | 조회 요청 |
| CreateProductCommand / UpdateProductCommand / DeleteProductCommand | 쓰기 요청 |
| ProductInfo | 자기 모듈의 조회·생성·수정 결과 |
| DeleteProductInfo | 명시적인 삭제 결과 |
| ProductAuthorView | 다른 모듈 결과와 조합한 결과 |

Command라는 이름은 쓰기 전용을 뜻하지 않는다. 이 문서에서는 모든 업무 요청 입력을 뜻한다. 요청 데이터가 없는 유스케이스에는 형식적인 빈 Command를 요구하지 않는다.

#### 3.3 Row

- XxxRow는 repository 전용 raw 결과 캐리어다.
- repository.py 또는 repository/에 정의한다.
- service의 mapper 전달용 임시 보유만 허용하며, 공개 반환 및 router 전달을 금지한다.

---

## 부록: 신규 모듈 및 변경 체크리스트

- 필요한 계층만 만들었는가?
- 소유 테이블과 공개 service를 ARCHITECTURE.md에 기록했는가?
- router → service → repository 방향을 지켰는가?
- 타 모듈 접근이 공개 service/types를 통해 이루어지는가?
- Row/Entity를 service에서 해석하지 않고 mapper에 전달했는가?
- router와 공개 service 반환값에서 Row/Entity를 배제했는가?
- 업무 판단은 service에, 순수 변환은 mapper에 있는가?
- 조회·쓰기 요청 데이터를 Command로 표현하고 반환 계약을 명시했는가?
- 최상위 유스케이스가 트랜잭션을 소유하며 내부 호출이 임의 commit하지 않는가?
- 업무 오류와 HTTP 오류 변환을 분리했는가?
- 독립된 업무 기능을 util에 넣지 않았는가?
- 파일 분리를 줄 수가 아닌 책임 기준으로 판단하고 구조 변경 이유를 기록했는가?
- 변경한 동작과 주요 실패 경로에 맞는 검증을 수행했는가?

503 등 미구현 스텁은 명시적으로 요청된 골격 작업에서만 허용한다. 스텁이 남은 기능은 구현 완료로 간주하지 않고 미완료 범위를 표시한다.
