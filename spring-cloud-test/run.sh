#!/usr/bin/env bash
# 전체 서비스 빌드 후 순서대로 실행 (eureka → auth/board → gateway)
# 로그: logs/<service>.log, 종료: ./stop.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.pids"

cd "$ROOT_DIR"
mkdir -p "$LOG_DIR" "$PID_DIR"

# 1) Gradle 실행 파일 결정
if [ -x "./gradlew" ]; then
  GRADLE="./gradlew"
elif command -v gradle >/dev/null 2>&1; then
  echo "[run] gradlew 가 없어 Gradle Wrapper 를 생성합니다."
  gradle wrapper --gradle-version 8.7
  GRADLE="./gradlew"
else
  echo "[run] gradlew 와 gradle 이 모두 없습니다. README 의 'Gradle Wrapper 생성'을 참고하세요." >&2
  exit 1
fi

# 2) 빌드
echo "[run] 빌드 중..."
"$GRADLE" clean bootJar -x test

start_service() {
  local name="$1" port="$2"
  local jar
  jar="$(ls "$name"/build/libs/*.jar | head -n 1)"

  nohup java -jar "$jar" > "$LOG_DIR/$name.log" 2>&1 &
  echo $! > "$PID_DIR/$name.pid"
  echo "[run] $name 시작 (port $port, pid $!)"
}

wait_for_health() {
  local name="$1" port="$2"
  local url="http://localhost:$port/actuator/health"

  for _ in $(seq 1 60); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "[run] $name 준비 완료"
      return 0
    fi
    sleep 2
  done
  echo "[run] $name 가 120초 안에 뜨지 않았습니다. logs/$name.log 를 확인하세요." >&2
  return 1
}

# 3) 실행
start_service eureka-server 8761
wait_for_health eureka-server 8761

start_service auth-service 8081
start_service board-service 8082
wait_for_health auth-service 8081
wait_for_health board-service 8082

start_service api-gateway 8080
wait_for_health api-gateway 8080

cat <<EOF

[run] 전체 서비스 실행 완료
  Eureka Dashboard : http://localhost:8761
  API Gateway      : http://localhost:8080
    - POST http://localhost:8080/auth/login
    - GET  http://localhost:8080/boards

  * Gateway 가 Eureka 에서 서비스 목록을 받아오기까지 최대 30초 정도 걸릴 수 있습니다.
  * 종료: ./stop.sh
EOF
