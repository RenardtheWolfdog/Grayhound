@echo off
rem Grayhound 실행을 위한 배치 파일 (WebSocket 방식)

title Grayhound Launcher

:: 배치 파일이 있는 디렉토리(grayhound_server)로 이동하여 경로 문제를 방지
cd /d "%~dp0"

echo [1/4] Starting Local System Agent (Optimizer.py)...
rem /c 옵션: Python 스크립트 실행 후 창이 자동으로 닫힙니다. (디버깅 시에는 /k 사용)
START "Grayhound Local Agent" cmd /c python secure_agent\Optimizer.py

echo [2/4] Starting Main WebSocket Server (Grayhound_Websocket.py)...
rem 메인 서버를 실행합니다. 클라이언트는 이 서버에 접속합니다.
START "Grayhound Main Server" cmd /c python Grayhound_Websocket.py

echo [3/4] Waiting for servers to initialize...
timeout /t 5 > nul

echo [4/4] Starting Grayhound Tauri Client...
rem 클라이언트 디렉토리로 이동하여 Tauri 앱을 실행
cd ../grayhound-client
npm run tauri dev

echo.
echo All processes are launched. You can close this window.
pause