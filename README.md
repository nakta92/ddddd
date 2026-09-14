# ddddd

두 개의 예제 프로젝트를 담은 저장소입니다.

| 폴더 | 내용 | 실행 방식 |
|---|---|---|
| [`admin-platform/`](admin-platform/) | app-server(Node.js) + backoffice-backend(FastAPI) + backoffice-frontend(React) | `docker compose up --build` |
| [`spring-cloud-test/`](spring-cloud-test/) | Spring Boot 3.2 + Spring Cloud 2023.0 멀티 모듈 (Eureka / Gateway / Auth / Board) | `./run.sh` |

자세한 내용은 각 폴더의 README를 참고하세요.

## 포트 요약

| 서비스 | 포트 |
|---|---|
| admin-platform / app-server | 50066 (WebSocket), 50067 (REST) |
| admin-platform / backoffice-backend | 8000 |
| admin-platform / backoffice-frontend | 3000 |
| spring-cloud-test / eureka-server | 8761 |
| spring-cloud-test / api-gateway | 8080 |
| spring-cloud-test / auth-service | 8081 |
| spring-cloud-test / board-service | 8082 |
