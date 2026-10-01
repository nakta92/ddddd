"""v7.0 스모크 테스트: 헬스체크, 배포 설정 파일(Dockerfile/compose/ignore) 점검."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_health(make_client):
    r = make_client().get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_dockerfile_settings():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "DATABASE_URL=sqlite:////data/guestbook.db" in text
    assert "UPLOAD_DIR=/data/uploads" in text
    assert 'VOLUME ["/data"]' in text
    assert '"--host", "0.0.0.0", "--port", "8000"' in text
    assert '"--workers", "1"' in text  # in-memory pub/sub
    assert "USER appuser" in text
    assert "HEALTHCHECK" in text and "/health" in text


def test_compose_settings():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"8000:8000"' in text
    assert "env_file:" in text and "- .env" in text
    assert "guestbook-data:/data" in text
    assert "restart: unless-stopped" in text


def test_secrets_are_ignored():
    for name in (".gitignore", ".dockerignore"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        for pattern in (".env", "*.db", "uploads/", "data/"):
            assert pattern in lines, f"{name}에 {pattern} 누락"
        assert "!.env.example" in lines
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("SECRET_KEY", "KAKAO_REST_API_KEY", "KAKAO_REDIRECT_URI", "ADMIN_KAKAO_IDS",
                "ADMIN_USERNAME", "ADMIN_PASSWORD", "UPLOAD_DIR", "MAX_UPLOAD_MB"):
        assert f"{key}=" in env_example
    # 예시 파일에 실제 비밀값이 들어가지 않도록
    assert "KAKAO_REST_API_KEY=\n" in env_example and "ADMIN_PASSWORD=\n" in env_example
