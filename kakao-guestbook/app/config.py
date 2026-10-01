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

    # 최초 관리자: 카카오 회원번호(쉼표 구분). 해당 사용자가 로그인하면 관리자 권한이 부여됩니다.
    admin_kakao_ids: str = ""
    # 카카오 없이 로그인하는 기본 관리자 계정(/auth/admin/login). 비워두면 비활성화됩니다.
    admin_username: str = ""
    admin_password: str = ""

    # HTTPS로 서비스할 때 true로 설정하면 세션 쿠키에 Secure 속성이 붙습니다.
    session_https_only: bool = False
    posts_per_page: int = 5

    @property
    def kakao_enabled(self) -> bool:
        return bool(self.kakao_rest_api_key)

    @property
    def admin_login_enabled(self) -> bool:
        return bool(self.admin_username and self.admin_password)

    @property
    def admin_kakao_id_set(self) -> set[int]:
        return {int(x) for x in self.admin_kakao_ids.replace(" ", "").split(",") if x.isdigit()}


settings = Settings()
