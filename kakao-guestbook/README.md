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
│   ├── routers/         # auth, guestbook
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
