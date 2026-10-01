from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """`.env` 파일 또는 환경변수에서 읽는 설정. 환경변수가 `.env`보다 우선합니다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "카카오 방명록"
    secret_key: str = "change-me-in-production"
    database_url: str = "sqlite:///./guestbook.db"

    # 카카오 개발자 콘솔 > 내 애플리케이션 > 앱 키 / 카카오 로그인
    kakao_rest_api_key: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = "http://localhost:8000/auth/kakao/callback"

    # HTTPS로 서비스할 때 true로 설정하면 세션 쿠키에 Secure 속성이 붙습니다.
    session_https_only: bool = False
    posts_per_page: int = 5

    @property
    def kakao_enabled(self) -> bool:
        return bool(self.kakao_rest_api_key)


settings = Settings()
