# ddddd

FastAPI + SQLite로 만든 카카오 로그인(OAuth 2.0) 기반 방명록 + 소셜 웹 서비스 저장소입니다.

| 폴더 | 내용 | 실행 방식 |
|---|---|---|
| [`kakao-guestbook/`](kakao-guestbook/) | 방명록(글·댓글·반응), 내 정보/관리자, 인앱 알림, 친구(사이 맺기), 실시간 그룹 채팅(SSE) | `docker compose up --build` |

설치·실행, 카카오 앱 설정, EC2 배포, 환경변수, 버전별 기능 표는 [`kakao-guestbook/README.md`](kakao-guestbook/README.md)를 참고하세요.

## 포트

| 서비스 | 포트 |
|---|---|
| kakao-guestbook | 8000 |
