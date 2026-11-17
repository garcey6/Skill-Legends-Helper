@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
title 选技大乱斗 - 浮窗助手

set "PYTHON_EXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
set "PYTHON_ARGS="
if not exist "%PYTHON_EXE%" goto try_py
"%PYTHON_EXE%" -c "import numpy, PIL, tkinter" >nul 2>nul
if not errorlevel 1 goto menu

:try_py
set "PYTHON_EXE=py"
set "PYTHON_ARGS=-3"
%PYTHON_EXE% %PYTHON_ARGS% -c "import numpy, PIL, tkinter" >nul 2>nul
if not errorlevel 1 goto menu

set "PYTHON_EXE=python"
set "PYTHON_ARGS="
%PYTHON_EXE% %PYTHON_ARGS% -c "import numpy, PIL, tkinter" >nul 2>nul
if not errorlevel 1 goto menu

echo.
echo 未找到带 numpy / Pillow / tkinter 的 Python。
echo 请安装 Python 3.10+ 后执行：
echo    python -m pip install -r requirements.txt
echo.
pause
exit /b 1

:menu
cls
echo.
echo  选技大乱斗 - 浮窗助手
echo.
echo  1. 启动浮窗 + 网页
echo  2. 只启动网页
echo  3. 打开设置
echo  4. 退出
echo.
choice /c 1234 /n /m "请选择 [1-4]: "
if errorlevel 4 goto end
if errorlevel 3 goto settings
if errorlevel 2 goto web
goto overlay

:overlay
echo.
echo 正在启动浮窗助手...
echo 控制台会显示实际识别/隐藏/退出快捷键（Alt+C 被占用时会自动换键）。
"%PYTHON_EXE%" %PYTHON_ARGS% agent.py --port 8777
goto end

:web
echo.
echo 正在启动网页控制台...
"%PYTHON_EXE%" %PYTHON_ARGS% run.py --port 8777
goto end

:settings
set "URL=http://127.0.0.1:8777"
if exist "data\server_url.txt" set /p URL=<"data\server_url.txt"
start "" "%URL%"
goto end

:end
if not defined XUANJI_NO_PAUSE pause
endlocal
