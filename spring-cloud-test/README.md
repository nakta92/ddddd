# spring-cloud-test

Spring Boot 3.2 + Spring Cloud 2023.0 기반 멀티 모듈(Gradle) 마이크로서비스 테스트 프로젝트입니다.
외부 DB 없이 메모리 저장소를 사용하므로 JDK 만 있으면 바로 실행할 수 있습니다.

```
                      ┌────────────────────┐
                      │ eureka-server 8761 │  서비스 레지스트리
                      └─────────▲──────────┘
                    등록/조회   │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
 Client ─▶ api-gateway 8080 ──lb://AUTH-SERVICE──▶ auth-service 8081
                          └──lb://BOARD-SERVICE─▶ board-service 8082
```

## 기술 스택

| 항목 | 버전 |
|---|---|
| Java | 17 |
| Spring Boot | 3.2.5 |
| Spring Cloud | 2023.0.1 |
| Gradle | 8.7 (Wrapper) |
| 공통 의존성 | Lombok, Spring Web, Spring Boot Actuator |

> `api-gateway` 는 Spring Cloud Gateway(WebFlux/Netty) 기반이라 Spring Web(MVC)을 넣으면 기동에 실패합니다.
> 그래서 루트 `build.gradle` 에서 `api-gateway` 만 Spring Web 을 제외했습니다.

## 모듈 구조

```
spring-cloud-test/
├── settings.gradle
├── build.gradle            # subprojects 공통 설정 (Boot, Cloud BOM, Lombok, Web, Actuator)
├── run.sh / stop.sh        # macOS / Linux 실행·종료
├── run.bat                 # Windows 실행
├── eureka-server/          # 8761  @EnableEurekaServer
├── api-gateway/            # 8080  Spring Cloud Gateway + Eureka Client
├── auth-service/           # 8081  로그인 / 토큰 발급 (메모리)
└── board-service/          # 8082  게시판 CRUD (메모리)
```

## Gradle Wrapper 생성 (최초 1회)

이 저장소에는 `gradlew` 와 `gradle/wrapper/gradle-wrapper.jar` 가 포함되어 있지 않습니다.
Gradle 이 설치된 환경에서 한 번만 실행하면 생성됩니다.

```bash
gradle wrapper --gradle-version 8.7
```

- IntelliJ IDEA 로 폴더를 열면 자동으로 Gradle 프로젝트로 인식되며, 여기서 실행해도 됩니다.
- `run.sh` / `run.bat` 는 `gradlew` 가 없고 `gradle` 이 설치되어 있으면 자동으로 생성합니다.
- 생성된 `gradlew`, `gradlew.bat`, `gradle/wrapper/*` 는 커밋해 두는 것을 권장합니다.

## 실행

### 스크립트로 전체 실행

```bash
# macOS / Linux
./run.sh      # 빌드 후 eureka → auth/board → gateway 순서로 실행
./stop.sh     # 종료
```

```bat
REM Windows
run.bat
```

### 모듈별 실행

```bash
./gradlew :eureka-server:bootRun
./gradlew :auth-service:bootRun
./gradlew :board-service:bootRun
./gradlew :api-gateway:bootRun
```

실행 후 http://localhost:8761 에서 `AUTH-SERVICE`, `BOARD-SERVICE`, `API-GATEWAY` 가 등록되었는지 확인하세요.

## API (Gateway 8080 경유)

### auth-service

테스트 계정: `admin / admin1234`, `user / user1234`

| Method | Path | 설명 |
|---|---|---|
| POST | `/auth/login` | 로그인, 토큰 발급 |
| GET | `/auth/validate` | 토큰 검증 (`Authorization: Bearer {token}`) |
| POST | `/auth/logout` | 토큰 폐기 (`Authorization: Bearer {token}`) |

```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin1234"}'
```

```json
{ "accessToken": "3f1c...", "tokenType": "Bearer", "expiresIn": 3600, "username": "admin" }
```

### board-service

| Method | Path | 설명 |
|---|---|---|
| GET | `/boards` | 게시글 목록 |
| GET | `/boards/{id}` | 게시글 상세 |
| POST | `/boards` | 게시글 작성 |
| PUT | `/boards/{id}` | 게시글 수정 |
| DELETE | `/boards/{id}` | 게시글 삭제 |

```bash
curl http://localhost:8080/boards

curl -X POST http://localhost:8080/boards \
  -H "Content-Type: application/json" \
  -d '{"title":"hello","content":"spring cloud","author":"admin"}'
```

### 기타

| URL | 설명 |
|---|---|
| http://localhost:8761 | Eureka 대시보드 |
| http://localhost:8080/actuator/gateway/routes | Gateway 라우팅 목록 |
| http://localhost:{port}/actuator/health | 각 서비스 헬스 체크 |

## 참고

- 데이터는 메모리에 저장되므로 서비스를 재시작하면 초기화됩니다.
- Gateway 는 Eureka 레지스트리를 주기적으로 받아오므로, 서비스 기동 직후 몇십 초 동안은 `503` 이 날 수 있습니다.
