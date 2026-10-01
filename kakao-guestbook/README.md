# 카카오 방명록

Python **FastAPI + SQLite**로 만든 카카오 로그인(OAuth 2.0) 기반 방명록 웹 서비스입니다.

## 주요 기능

### 방명록 (v1.0)
- 카카오 로그인/로그아웃. 콜백에서 사용자 upsert(닉네임, 프로필 이미지, 가입일 저장)
- 방명록 조회는 누구나, 작성은 로그인 사용자만
- 게시글 / 댓글 / 대댓글(1단계). 모두 **본인만 수정·삭제**
- 반응(👍 좋아요 / 👎 싫어요 / 🙏 감사해요): 글·댓글·대댓글 공용, 사용자당 1개 토글, 마우스를 올리면 참여자 명단 표시
- 작성/수정/삭제/반응은 AJAX로 처리해 **스크롤 위치 유지**(새로고침·점프 없음). JS를 끄면 일반 폼 제출 + 리다이렉트로 동작
- 게시글 페이지네이션(5개/페이지), 댓글 전체 접기·펴기 + 대댓글 토글, 글쓰기 플로팅 버튼(맨 위로 + 입력창 포커스)
- 모든 시간은 UTC로 저장하고 KST로 표시
- 앱 시작 시 **누락 컬럼 자동 추가 마이그레이션**(기존 DB 호환)

### 내 정보 / 관리자 (v2.0)
- 내 정보 등록·변경(`/me`): 표시 이름, 자기소개. 표시 이름이 있으면 카카오 닉네임 대신 우선 노출
- 사용자 프로필 페이지(`/users/{id}`): 작성자 이름을 누르면 이동
- 관리자 페이지(`/admin`): 회원 목록·검색, 회원 삭제, 관리자 권한 부여/해제(본인 해제·삭제 차단)
- 최초 관리자는 `.env`의 `ADMIN_KAKAO_IDS`(카카오 회원번호)로 지정
- 카카오 없이 로그인하는 기본 관리자 계정(`ADMIN_USERNAME`/`ADMIN_PASSWORD`, `/auth/admin/login`), 5회 실패 시 5분 잠금

### 알림 (v3.0)
- 내 글에 댓글, 내 댓글에 대댓글, 글/댓글 반응 시 인앱 알림 생성(본인 행동은 제외, 반응 알림은 중복 방지)
- `/notifications` 목록 + 상단바 🔔 안 읽은 수 배지(30초마다 갱신)
- 알림 클릭 시 읽음 처리 후 대상 글/댓글이 있는 페이지로 이동해 펼치고 강조. 삭제된 대상은 안내
- 안 읽은 알림은 하늘색 배경, 읽은 알림은 옅은 회색. "모두 읽음" 지원

## 기술 스택

| 구분 | 사용 기술 |
|---|---|
| 웹 프레임워크 | FastAPI, Starlette SessionMiddleware(세션 로그인) |
| DB | SQLite, SQLAlchemy 2.0 |
| 템플릿 | Jinja2 (서버 렌더링 + 바닐라 JS) |
| 외부 연동 | 카카오 REST API OAuth 2.0, httpx |
| 기타 | python-multipart, pydantic-settings(`.env`) |

## 설치 및 실행

```bash
cd kakao-guestbook
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # 값 채우기 (아래 '카카오 앱 설정' 참고)
uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 접속.

## 카카오 앱 설정

1. [Kakao Developers](https://developers.kakao.com) > 내 애플리케이션 > **애플리케이션 추가하기**
2. **앱 키**의 `REST API 키` → `.env`의 `KAKAO_REST_API_KEY`
3. **플랫폼 > Web**에 사이트 도메인 등록 (예: `http://localhost:8000`)
4. **카카오 로그인** 활성화 ON, **Redirect URI** 등록: `http://localhost:8000/auth/kakao/callback`
   (`.env`의 `KAKAO_REDIRECT_URI`와 정확히 같아야 합니다)
5. **동의항목**에서 `닉네임`, `프로필 사진` 설정
6. (선택) **보안 > Client Secret**을 사용하면 코드를 `.env`의 `KAKAO_CLIENT_SECRET`에 입력

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `APP_NAME` | 카카오 방명록 | 화면에 표시되는 서비스 이름 |
| `SECRET_KEY` | (임시값) | 세션 쿠키 서명 키. **운영에서 반드시 변경** |
| `DATABASE_URL` | `sqlite:///./guestbook.db` | SQLAlchemy DB URL |
| `SESSION_HTTPS_ONLY` | `false` | HTTPS 서비스 시 `true` |
| `KAKAO_REST_API_KEY` | - | 카카오 REST API 키 |
| `KAKAO_CLIENT_SECRET` | - | (선택) 카카오 Client Secret |
| `KAKAO_REDIRECT_URI` | `http://localhost:8000/auth/kakao/callback` | 카카오에 등록한 Redirect URI |
| `ADMIN_KAKAO_IDS` | - | 최초 관리자 카카오 회원번호(쉼표 구분) |
| `ADMIN_USERNAME` | - | 기본 관리자 계정 아이디 (비우면 비활성) |
| `ADMIN_PASSWORD` | - | 기본 관리자 계정 비밀번호 (비우면 비활성, 길고 복잡하게) |

## 테스트

카카오 API는 가짜 함수로 바꿔 실제 네트워크 없이 OAuth 콜백 흐름까지 검증합니다.

```bash
pip install -r requirements-dev.txt
pytest
```

## 폴더 구조

```
kakao-guestbook/
├── app/
│   ├── main.py          # 앱 생성, 미들웨어, 예외 처리, 시작 시 마이그레이션
│   ├── config.py        # .env 설정 (pydantic-settings)
│   ├── database.py      # 엔진/세션, SQLite 외래키 활성화
│   ├── models.py        # SQLAlchemy 모델
│   ├── migrations.py    # 누락 컬럼 자동 추가
│   ├── kakao.py         # 카카오 OAuth 클라이언트
│   ├── deps.py          # 현재 사용자, 템플릿, 플래시, AJAX 판별
│   ├── views.py         # 방명록 뷰 모델(댓글 트리·반응 요약)
│   ├── timeutil.py      # UTC → KST
│   ├── notify.py        # 알림 생성/조회 헬퍼
│   ├── routers/         # auth, guestbook, profile, admin, notifications
│   ├── templates/       # Jinja2 템플릿 (layout.html 상속)
│   └── static/          # style.css, app.js
├── tests/               # pytest 스모크 테스트
├── requirements.txt
└── .env.example
```

## 버전 관리

| 버전 | 태그 | 내용 |
|---|---|---|
| v1.0 | `v1.0` | 카카오 로그인, 방명록(글/댓글/대댓글), 반응, AJAX(스크롤 유지), 페이지네이션, KST 표시, 자동 마이그레이션 |
| v2.0 | `v2.0` | 내 정보(표시 이름·자기소개), 프로필 페이지, 관리자 페이지(회원 삭제·권한 부여/해제), 최초 관리자 지정, 기본 관리자 계정 |
| v3.0 | `v3.0` | 인앱 알림(댓글·대댓글·반응), 알림 목록·안 읽은 수 배지, 클릭 시 대상 이동+강조 |
