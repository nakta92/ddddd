import os

# app-server REST 주소 (docker-compose 에서는 http://app-server:50067)
APP_SERVER_URL = os.getenv("APP_SERVER_URL", "http://localhost:50067")

# 쉼표로 구분된 허용 Origin 목록
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
