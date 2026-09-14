# admin-platform

도커 컨테이너 3개로 구성된 실시간 서비스 + 관리자(백오피스) 예제입니다.

```
                ┌──────────────────────────┐
  Client ──WS──▶│ app-server               │
  (50066)       │  WebSocket 50066         │◀──REST──┐
  Client ─REST─▶│  REST API  50067         │         │
                └──────────────────────────┘         │
                                                     │
  Admin ──HTTP──▶ backoffice-frontend (3000) ──/api──▶ backoffice-backend (8000)
                  React + nginx                        FastAPI
```

| 서비스 | 스택 | 포트 | 역할 |
|---|---|---|---|
| `app-server` | Node.js 20, Express, ws | 50066 (WS), 50067 (REST) | 실시간 통신, 메인 비즈니스 로직 |
| `backoffice-backend` | Python 3.12, FastAPI | 8000 | 관리자 전용 API |
| `backoffice-frontend` | React 18, Vite, nginx | 3000 | 관리자 대시보드 UI |

## 실행

```bash
docker compose up --build
```

- 대시보드: http://localhost:3000
- 백오피스 API 문서(Swagger): http://localhost:8000/docs
- app-server REST: http://localhost:50067/health
- app-server WebSocket: `ws://localhost:50066`

종료: `docker compose down`

## 폴더 구조

```
admin-platform/
├── docker-compose.yml
├── app-server/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── index.js          # 진입점 (WS + REST 서버 기동)
│       ├── config.js         # 포트 설정
│       ├── rest/server.js    # REST 라우팅 (50067)
│       └── ws/wsServer.js    # WebSocket 서버 (50066)
├── backoffice-backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI 앱, CORS, 라우터 등록
│       ├── config.py         # 환경 변수
│       └── routers/
│           ├── health.py     # GET /health
│           └── admin.py      # /api/admin/*
└── backoffice-frontend/
    ├── Dockerfile            # 빌드 후 nginx로 서빙
    ├── nginx.conf            # 3000 포트, /api → backoffice-backend:8000 프록시
    ├── vite.config.js        # 로컬 개발 서버 3000, /api 프록시
    └── src/
        ├── App.jsx
        └── api/client.js
```

## API

### app-server (REST 50067)

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 헬스 체크 |
| GET | `/api/stats` | 현재 WebSocket 접속자 수, 가동 시간 |
| POST | `/api/broadcast` | 모든 WebSocket 클라이언트에게 공지 전송 `{ "message": "..." }` |

### app-server (WebSocket 50066)

JSON 메시지를 주고받습니다.

| 클라이언트 → 서버 | 서버 → 클라이언트 |
|---|---|
| `{ "type": "ping" }` | `{ "type": "pong" }` |
| `{ "type": "chat", "payload": "hi" }` | 모든 클라이언트에게 `{ "type": "chat", ... }` |
| (접속 시) | `{ "type": "welcome", "clientId": "..." }` |
| (관리자 공지) | `{ "type": "notice", "message": "..." }` |

### backoffice-backend (8000)

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 헬스 체크 |
| GET | `/api/admin/dashboard` | app-server 상태 + 사용자 통계 |
| GET | `/api/admin/users` | 사용자 목록 (메모리 가짜 데이터) |
| GET | `/api/admin/users/{id}` | 사용자 상세 |
| PATCH | `/api/admin/users/{id}/status` | 사용자 상태 변경 `{ "status": "active" \| "banned" }` |
| POST | `/api/admin/notices` | app-server를 통해 실시간 공지 전송 `{ "message": "..." }` |

## Docker 없이 로컬 개발

```bash
# app-server
cd app-server && npm install && npm start

# backoffice-backend
cd backoffice-backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

# backoffice-frontend (http://localhost:3000, /api 는 localhost:8000으로 프록시)
cd backoffice-frontend && npm install && npm run dev
```
