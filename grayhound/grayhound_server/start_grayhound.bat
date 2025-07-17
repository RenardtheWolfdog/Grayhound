@echo off
rem Grayhound 실행을 위한 배치 파일

title Grayhound Launcher

echo [1/4] Start Grayhound Agent (Optimizer)...
REM "Grayhound Agent" 라는 제목의 새 창에서 현장 요원을 실행하고, 창을 닫지 않음
START "Grayhound Agent" cmd /k python secure_agent/Optimizer.py

echo [2/4] Wait for 5 seconds...
REM 에이전트가 완전히 실행될 시간을 벌어주기 위한 대기 시간
timeout /t 5 > nul

echo [3/4] Start Grayhound Main CLI...
REM "Grayhound CLI" 라는 제목의 새 창에서 지휘 본부를 실행
START "Grayhound CLI" python Grayhound_CLI.py

@REM cd ..
echo  -> Start the CLI. (python Grayhound_CLI.py)
echo.

:: ======================================================
:: 2. Grayhound 클라이언트 실행 (Tauri)
:: ======================================================

@REM cd grayhound-client

@REM echo [4/4] Start Grayhound Client...
@REM cd grayhound-client

@REM echo  -> Start the client. (npm run tauri dev)
@REM npm run tauri dev

@REM rem Close this window after 5 seconds.
@REM timeout /t 5 > nul
@REM exit