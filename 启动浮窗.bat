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
if not errorlevel 1 goto run

:try_py
set "PYTHON_EXE=py"
set "PYTHON_ARGS=-3"
%PYTHON_EXE% %PYTHON_ARGS% -c "import numpy, PIL, tkinter" >nul 2>nul
if not errorlevel 1 goto run

set "PYTHON_EXE=python"
set "PYTHON_ARGS="
%PYTHON_EXE% -c "import numpy, PIL, tkinter" >nul 2>nul
if not errorlevel 1 goto run

echo.
echo 未找到带 numpy / Pillow / tkinter 的 Python。
echo 请安装 Python 3.10+ 后执行：
echo    python -m pip install -r requirements.txt
echo.
pause
exit /b 1

:run
echo 正在启动浮窗助手...
echo 控制台会显示实际识别/隐藏/退出快捷键（Alt+C 被占用时会自动换键）。
"%PYTHON_EXE%" %PYTHON_ARGS% agent.py --port 8777
echo.
echo 浮窗已停止。
if not defined XUANJI_NO_PAUSE pause
endlocal
