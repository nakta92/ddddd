# 카카오 방명록

Python **FastAPI + SQLite**로 만든 카카오 로그인(OAuth 2.0) 기반 **방명록 + 소셜 웹 서비스**입니다.
방명록(글·댓글·반응)에 더해 내 정보, 관리자, 인앱 알림, 친구(사이 맺기), 실시간 그룹 채팅을 제공합니다.

## 목차
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [설치 및 실행](#설치-및-실행)
- [카카오 앱 설정](#카카오-앱-설정)
- [Docker로 실행](#docker로-실행)
- [EC2에 Docker로 배포](#ec2에-docker로-배포)
- [환경변수](#환경변수)
- [운영 시 참고](#운영-시-참고)
- [테스트](#테스트)
- [폴더 구조](#폴더-구조)
- [버전 관리](#버전-관리)

## 주요 기능

### 방명록 (v1.0)
- 카카오 로그인/로그아웃. 콜백에서 사용자 upsert(닉네임, 프로필 이미지, 가입일 저장), `state`로 CSRF 방지
- 방명록 조회는 누구나, 작성은 로그인 사용자만
- 게시글 / 댓글 / 대댓글(1단계). 모두 **본인만 수정·삭제**
- 반응(👍 좋아요 / 👎 싫어요 / 🙏 감사해요): 글·댓글·대댓글 공용, 사용자당 1개 토글, 마우스를 올리면 참여자 명단 표시
- 작성/수정/삭제/반응은 AJAX로 처리해 **스크롤 위치 유지**(새로고침·점프 없음). JS를 끄면 일반 폼 제출 + 리다이렉트로 동작
- 게시글 페이지네이션(5개/페이지), 댓글 전체 접기·펴기 + 대댓글 토글, 글쓰기 플로팅 버튼(맨 위로 + 입력창 포커스)
- 모든 시간은 UTC로 저장하고 KST로 표시
- 앱 시작 시 **누락 컬럼/인덱스 자동 추가 마이그레이션**(기존 DB 호환)

### 내 정보 / 관리자 (v2.0)
- 내 정보 등록·변경(`/me`): 표시 이름, 자기소개. 표시 이름이 있으면 카카오 닉네임 대신 우선 노출
- 사용자 프로필 페이지(`/users/{id}`): 작성자 이름을 누르면 이동
- 관리자 페이지(`/admin`): 회원 목록·검색, 회원 삭제, 관리자 권한 부여/해제(본인 해제·삭제 차단)
- 최초 관리자는 `.env`의 `ADMIN_KAKAO_IDS`(카카오 회원번호)로 지정
- 카카오 없이 로그인하는 기본 관리자 계정(`ADMIN_USERNAME`/`ADMIN_PASSWORD`, `/auth/admin/login`), 5회 실패 시 5분 잠금

### 알림 (v3.0)
- 내 글에 댓글, 내 댓글에 대댓글, 글/댓글 반응, 친구 요청/수락/거절, 채팅 초대, 멘션 시 인앱 알림(본인 행동 제외, 반응 알림 중복 방지)
- `/notifications` 목록 + 🔔 안 읽은 수 배지(30초마다 갱신)
- 알림 클릭 시 읽음 처리 후 대상(글/댓글/채팅 메시지)이 있는 위치로 이동해 펼치고 강조. 삭제된 대상은 안내
- 안 읽은 알림은 하늘색 배경, 읽은 알림은 옅은 회색. "모두 읽음" 지원

### 친구 / 사이 맺기 (v4.0)
- 사용자 검색 → 친구 요청(관계 라벨: 친구 / 동료 / 직접 입력), 수락·거절·요청 취소·끊기, 관계 라벨 수정(각자 자기 라벨)
- 상대가 먼저 보낸 요청이 있으면 내 요청은 바로 수락 처리
- 방명록 글 작성자가 친구가 아니면 이름 옆 **+친구 추가** 버튼(새로고침 없이 요청), 친구면 관계 칩 표시

### 그룹 채팅 (v5.0)
- 채팅방 개설, **사이 맺은 친구만 초대**, 초대는 수락해야 입장(수락/거절 + 알림, 초대한 사람에게 결과 알림)
- 텍스트 / 파일(최대 10MB) 공유. 파일은 **방 멤버만 다운로드**, 안전한 이미지(png/jpeg/gif/webp)는 미리보기
- **실시간(SSE)**: 새 메시지, 읽음, 멤버 변경이 즉시 반영. 연결이 끊겼다 다시 붙으면 놓친 메시지 자동 보충
- 메시지별 **"N명 읽음"**(방 입장/보고 있을 때 읽음 처리), 채팅 목록 방별 안 읽은 메시지 배지(실시간)
- 멤버 이름 옆 관계 표시, **`@멘션` 자동완성**(↑↓ 선택, Enter/Tab 입력) + 멘션 알림(클릭 시 해당 메시지로 이동·강조)
- Enter 전송 / Shift+Enter 줄바꿈(한글 조합 중 Enter는 무시)

### UI (v6.0)
- 모든 페이지가 공통 레이아웃(`layout.html`)을 상속
- 반응형 사이드바: 데스크톱(960px 초과)은 왼쪽 고정, 모바일은 햄버거 버튼으로 여는 드로어(JS 없이도 동작, ESC/바깥 클릭/메뉴 이동 시 닫힘)
- 상단바는 로고 + 🔔 알림 배지, 사이드바 메뉴에 채팅·친구 요청·알림 배지와 현재 메뉴 강조

### 배포 (v7.0)
- `Dockerfile`(uvicorn `0.0.0.0:8000`, 비root 실행, DB/업로드는 `/data` 볼륨, 헬스체크), `docker-compose.yml`, `.dockerignore`
- `/health` 헬스체크 엔드포인트(DB 연결 확인), 기본 `SECRET_KEY` 사용 시 시작 로그 경고

## 기술 스택

| 구분 | 사용 기술 |
|---|---|
| 웹 프레임워크 | FastAPI, Starlette SessionMiddleware(세션 로그인) |
| DB | SQLite, SQLAlchemy 2.0 |
| 템플릿 | Jinja2 (서버 렌더링 + 바닐라 JS) |
| 외부 연동 | 카카오 REST API OAuth 2.0, httpx |
| 실시간 | SSE(Server-Sent Events) + in-memory pub/sub |
| 기타 | python-multipart(폼/파일 업로드), pydantic-settings(`.env`) |
| 배포 | Docker, Docker Compose, uvicorn |

## 설치 및 실행

Python 3.11 이상이 필요합니다.

```bash
cd kakao-guestbook
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # 값 채우기 (아래 '카카오 앱 설정' 참고)
uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3
```

브라우저에서 http://localhost:8000 접속.

> `--timeout-graceful-shutdown`: 채팅 SSE 연결이 열려 있어도 재시작/종료가 막히지 않게 대기 시간을 제한합니다.
>
> 카카오 키 없이 먼저 둘러보려면 `.env`에 `ADMIN_USERNAME`/`ADMIN_PASSWORD`를 넣고 `/auth/admin/login`으로 로그인하세요.

## 카카오 앱 설정

1. [Kakao Developers](https://developers.kakao.com) > 내 애플리케이션 > **애플리케이션 추가하기**
2. **앱 키**의 `REST API 키` → `.env`의 `KAKAO_REST_API_KEY`
3. **플랫폼 > Web**에 사이트 도메인 등록 (예: `http://localhost:8000`, 운영 도메인 `https://guestbook.example.com`)
4. **카카오 로그인** 활성화 ON, **Redirect URI** 등록: `http://localhost:8000/auth/kakao/callback`
   (`.env`의 `KAKAO_REDIRECT_URI`와 정확히 같아야 합니다. 운영 도메인용 URI도 함께 등록하세요)
5. **동의항목**에서 `닉네임`, `프로필 사진` 설정
6. (선택) **보안 > Client Secret**을 사용하면 코드를 `.env`의 `KAKAO_CLIENT_SECRET`에 입력
7. 최초 관리자로 지정할 사람의 **카카오 회원번호**를 `ADMIN_KAKAO_IDS`에 입력
   (한 번 로그인한 뒤 기본 관리자 계정으로 `/admin`에 들어가면 '로그인' 열에서 회원번호를 확인할 수 있습니다)

## Docker로 실행

```bash
cd kakao-guestbook
cp .env.example .env               # 값 채우기
docker compose up -d --build
docker compose logs -f             # 로그 확인
```

- DB(`/data/guestbook.db`)와 첨부파일(`/data/uploads`)은 named volume `guestbook-data`에 저장되어 컨테이너를 지워도 유지됩니다.
- compose가 `DATABASE_URL`/`UPLOAD_DIR`을 `/data` 경로로 고정하므로 `.env`의 해당 값은 무시됩니다.
- 상태 확인: `curl http://localhost:8000/health` → `{"status":"ok"}`
- 중지: `docker compose down` (볼륨까지 지우려면 `-v`, **데이터가 삭제됩니다**)

## EC2에 Docker로 배포

### 1. EC2 인스턴스 준비
- AMI: Amazon Linux 2023 또는 Ubuntu 22.04/24.04, 타입: t3.micro 이상
- 보안 그룹 인바운드: `22`(SSH, 내 IP만), `80`, `443`. Nginx 없이 바로 확인할 때만 `8000` 임시 개방
- (권장) 탄력적 IP를 할당하고 도메인 A 레코드를 연결

### 2. Docker 설치

```bash
# Amazon Linux 2023
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Ubuntu
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
```

그룹 변경이 반영되도록 SSH에 다시 접속한 뒤 `docker compose version`으로 확인합니다.

### 3. 코드 받기 + 환경변수

```bash
git clone https://github.com/nakta92/ddddd.git
cd ddddd/kakao-guestbook
cp .env.example .env
vi .env
```

운영에서 꼭 바꿀 값:

```dotenv
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))" 결과>
KAKAO_REST_API_KEY=<REST API 키>
KAKAO_REDIRECT_URI=https://guestbook.example.com/auth/kakao/callback
SESSION_HTTPS_ONLY=true            # HTTPS로 서비스할 때
ADMIN_KAKAO_IDS=<내 카카오 회원번호>
ADMIN_PASSWORD=<길고 복잡한 비밀번호 또는 비워서 비활성화>
FORWARDED_ALLOW_IPS=*              # Nginx 등 프록시 뒤에서만. 8000 포트를 외부에 직접 열면 넣지 마세요
```

### 4. 실행

```bash
docker compose up -d --build
docker compose ps                  # STATUS가 healthy인지 확인
curl http://localhost:8000/health
```

### 5. Nginx + HTTPS (권장)

카카오 로그인 운영 환경과 Secure 쿠키를 위해 HTTPS를 권장합니다. 앱은 `8000`에서만 듣고 Nginx가 `80/443`을 받습니다.

```bash
sudo dnf install -y nginx          # Ubuntu: sudo apt-get install -y nginx
sudo vi /etc/nginx/conf.d/guestbook.conf
```

```nginx
server {
    listen 80;
    server_name guestbook.example.com;
    client_max_body_size 12m;            # 채팅 첨부파일 10MB + 여유

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 채팅 실시간(SSE): 버퍼링 끄고 연결을 길게 유지
    location ~ ^/chat/(events|\d+/events)$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1h;
    }
}
```

```bash
sudo nginx -t && sudo systemctl enable --now nginx
# HTTPS 인증서 (Let's Encrypt)
sudo dnf install -y certbot python3-certbot-nginx   # Ubuntu: sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d guestbook.example.com
```

Nginx 뒤에서 운영할 때는 `docker-compose.yml`의 포트를 `"127.0.0.1:8000:8000"`으로 바꿔 외부에서 8000에 직접 접근하지 못하게 하세요.
마지막으로 카카오 개발자 콘솔에 운영 도메인(Web 플랫폼)과 Redirect URI를 등록합니다.

### 6. 업데이트 / 백업 / 로그

```bash
# 업데이트 (앱 시작 시 누락 컬럼은 자동 마이그레이션)
git pull
docker compose up -d --build

# 백업: 볼륨의 DB와 첨부파일을 tar로 저장
docker run --rm -v kakao-guestbook_guestbook-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/guestbook-backup-$(date +%F).tar.gz -C /data .

# 로그
docker compose logs -f --tail 200
```

## 환경변수

`.env.example`을 복사해 `.env`로 사용합니다. **`.env`, `*.db`, `uploads/`, `data/`는 `.gitignore`/`.dockerignore`로 제외**되어 커밋·이미지에 포함되지 않습니다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `APP_NAME` | 카카오 방명록 | 화면에 표시되는 서비스 이름 |
| `SECRET_KEY` | (임시값) | 세션 쿠키 서명 키. **운영에서 반드시 변경** |
| `DATABASE_URL` | `sqlite:///./guestbook.db` | SQLAlchemy DB URL (Docker에서는 `sqlite:////data/guestbook.db`) |
| `SESSION_HTTPS_ONLY` | `false` | HTTPS 서비스 시 `true` (세션 쿠키 Secure) |
| `POSTS_PER_PAGE` | `5` | 방명록 페이지당 글 수 |
| `KAKAO_REST_API_KEY` | - | 카카오 REST API 키 |
| `KAKAO_CLIENT_SECRET` | - | (선택) 카카오 Client Secret |
| `KAKAO_REDIRECT_URI` | `http://localhost:8000/auth/kakao/callback` | 카카오에 등록한 Redirect URI |
| `ADMIN_KAKAO_IDS` | - | 최초 관리자 카카오 회원번호(쉼표 구분) |
| `ADMIN_USERNAME` | - | 기본 관리자 계정 아이디 (비우면 비활성) |
| `ADMIN_PASSWORD` | - | 기본 관리자 계정 비밀번호 (비우면 비활성, 길고 복잡하게) |
| `UPLOAD_DIR` | `./uploads` | 채팅 첨부파일 저장 폴더 (Docker에서는 `/data/uploads`) |
| `MAX_UPLOAD_MB` | `10` | 첨부파일 최대 크기(MB) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | (uvicorn) `X-Forwarded-*`를 신뢰할 프록시 IP. Nginx/ALB 뒤에서만 설정 |

## 운영 시 참고

- **워커 1개**: 실시간 이벤트를 프로세스 메모리(pub/sub)로 전달하므로 uvicorn 워커를 1개로 실행합니다(Dockerfile 기본값).
  여러 워커/서버로 늘리려면 Redis pub/sub 같은 외부 브로커와 PostgreSQL 같은 서버형 DB로 바꾸세요.
- **SQLite**: WAL 모드와 외래키(ON DELETE CASCADE)를 켜서 사용합니다. 정기적으로 볼륨을 백업하세요.
- **보안**: 세션 쿠키는 서명(itsdangerous)되고 `SameSite=Lax`입니다. 카카오 로그인은 `state`를 검증하고, 로그인 후 이동 경로는 내부 경로만 허용합니다.
  첨부파일은 멤버만 받을 수 있고, 이미지 외 파일은 항상 다운로드(`attachment`)로 내려가며 `nosniff` 헤더를 붙입니다.
- **업로드 한도**: `Content-Length`가 한도를 넘는 요청은 본문을 받기 전에 413으로 거절합니다.

## 테스트

카카오 API는 가짜 함수로 바꿔 실제 네트워크 없이 OAuth 콜백 흐름까지 검증합니다.
SSE 실시간 테스트(`test_v5_sse_live.py`)는 가짜 카카오 로그인을 붙인 실제 uvicorn 서버(`tests/live_server.py`)를 띄워 검증합니다.

```bash
pip install -r requirements-dev.txt
pytest
```

| 파일 | 내용 |
|---|---|
| `test_v1_guestbook.py` | 카카오 로그인 흐름, 글/댓글/대댓글, 반응 토글, AJAX/리다이렉트, 페이지네이션, KST |
| `test_migration.py` | 예전 스키마 DB에 누락 컬럼·인덱스 자동 추가 |
| `test_v2_profile_admin.py` | 표시 이름/자기소개, 관리자 권한·삭제, 최초 관리자, 기본 관리자 로그인·잠금 |
| `test_v3_notifications.py` | 댓글/대댓글/반응 알림, 배지, 클릭 이동, 모두 읽음 |
| `test_v4_friends.py` | 친구 요청·수락·거절·취소·끊기, 라벨, 방명록 +친구 추가/관계 칩 |
| `test_v5_chat.py` | 방 개설·친구만 초대·수락, 메시지, N명 읽음, 안 읽은 배지, 파일 권한·크기 제한, 멘션 |
| `test_v5_sse_live.py` | 실서버 SSE: 실시간 메시지·읽음·안 읽은 수 이벤트, 비멤버 구독 차단 |
| `test_v6_layout.py` | 레이아웃 상속, 권한별 사이드바 메뉴, 현재 메뉴, 배지 |
| `test_v7_deploy.py` | 헬스체크, Dockerfile/compose/ignore/.env.example 점검 |

## 폴더 구조

```
kakao-guestbook/
├── app/
│   ├── main.py          # 앱 생성, 미들웨어(세션·업로드 한도), 예외 처리, 헬스체크, 시작 시 마이그레이션
│   ├── config.py        # .env 설정 (pydantic-settings)
│   ├── database.py      # 엔진/세션, SQLite 외래키·WAL
│   ├── models.py        # SQLAlchemy 모델
│   ├── migrations.py    # 누락 컬럼/인덱스 자동 추가
│   ├── kakao.py         # 카카오 OAuth 클라이언트
│   ├── deps.py          # 현재 사용자, 템플릿, 플래시, AJAX 판별, 공통 배지
│   ├── views.py         # 방명록 뷰 모델(댓글 트리·반응 요약)
│   ├── notify.py        # 알림 생성/조회 헬퍼
│   ├── friends.py       # 친구 관계 조회/라벨 헬퍼
│   ├── chat.py          # 채팅 읽음/안 읽은 수/멘션/첨부파일/실시간 이벤트
│   ├── pubsub.py        # SSE용 in-memory pub/sub
│   ├── timeutil.py      # UTC → KST
│   ├── routers/         # auth, guestbook, profile, admin, notifications, friends, chat
│   ├── templates/       # Jinja2 템플릿 (모든 페이지가 layout.html 상속, _로 시작하는 파일은 부분 템플릿)
│   └── static/          # style.css, app.js(공통), chat.js(채팅)
├── tests/               # pytest 스모크 테스트 + live_server.py(가짜 카카오 실서버)
├── Dockerfile
├── docker-compose.yml
├── .dockerignore / .gitignore
├── requirements.txt / requirements-dev.txt
└── .env.example
```

## 버전 관리

기능 묶음마다 커밋과 `vX.Y` 태그를 남겼습니다. 특정 버전을 보려면 `git checkout v3.0`처럼 태그로 이동하세요.

| 버전 | 태그 | 내용 |
|---|---|---|
| v1.0 | `v1.0` | 카카오 로그인, 방명록(글/댓글/대댓글), 반응, AJAX(스크롤 유지), 페이지네이션, KST 표시, 자동 마이그레이션 |
| v2.0 | `v2.0` | 내 정보(표시 이름·자기소개), 프로필 페이지, 관리자 페이지(회원 삭제·권한 부여/해제), 최초 관리자 지정, 기본 관리자 계정 |
| v3.0 | `v3.0` | 인앱 알림(댓글·대댓글·반응), 알림 목록·안 읽은 수 배지, 클릭 시 대상 이동+강조 |
| v4.0 | `v4.0` | 친구(사이 맺기): 검색·요청·수락/거절/취소/끊기, 관계 라벨, 방명록 +친구 추가/관계 칩, 친구 알림 |
| v5.0 | `v5.0` | 그룹 채팅: 친구 초대·수락, 텍스트/파일(10MB), 실시간 SSE, N명 읽음, 안 읽은 배지, @멘션 자동완성·알림 |
| v6.0 | `v6.0` | 공통 레이아웃 + 반응형 사이드바(데스크톱 고정 / 모바일 햄버거 드로어), 상단바 로고+알림 배지 |
| v7.0 | `v7.0` | Docker 배포(Dockerfile·compose·볼륨·헬스체크), EC2 배포 가이드, README 정리 |
