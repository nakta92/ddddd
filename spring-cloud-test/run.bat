@echo off
REM 전체 서비스 빌드 후 각각 새 창에서 실행 (eureka -> auth/board -> gateway)
REM 종료: 각 창을 닫거나 Ctrl+C
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist gradlew.bat goto build

where gradle >nul 2>nul
if errorlevel 1 (
  echo [run] gradlew.bat 와 gradle 이 모두 없습니다. README 의 'Gradle Wrapper 생성'을 참고하세요.
  exit /b 1
)
echo [run] gradlew.bat 가 없어 Gradle Wrapper 를 생성합니다.
call gradle wrapper --gradle-version 8.7
if errorlevel 1 exit /b 1

:build
echo [run] 빌드 중...
call gradlew.bat clean bootJar -x test
if errorlevel 1 exit /b 1

set VERSION=0.0.1-SNAPSHOT

start "eureka-server (8761)" cmd /k java -jar eureka-server\build\libs\eureka-server-%VERSION%.jar
echo [run] eureka-server 기동 대기 (25초)...
timeout /t 25 /nobreak >nul

start "auth-service (8081)" cmd /k java -jar auth-service\build\libs\auth-service-%VERSION%.jar
start "board-service (8082)" cmd /k java -jar board-service\build\libs\board-service-%VERSION%.jar
echo [run] auth/board 서비스 기동 대기 (20초)...
timeout /t 20 /nobreak >nul

start "api-gateway (8080)" cmd /k java -jar api-gateway\build\libs\api-gateway-%VERSION%.jar

echo.
echo [run] 전체 서비스 실행 요청 완료
echo   Eureka Dashboard : http://localhost:8761
echo   API Gateway      : http://localhost:8080
endlocal
