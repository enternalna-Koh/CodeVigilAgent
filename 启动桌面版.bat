@echo off
chcp 65001>nul
setlocal enabledelayedexpansion
title CodeVigil Agent 桌面版
cd /d "%~dp0"

rem ============================================================
rem  Double-click this file to launch the desktop app.
rem
rem  Why probe several interpreters:
rem     PATH may contain a trimmed Python build without tkinter.
rem     Using it directly fails with
rem     "ModuleNotFoundError: No module named 'tkinter'".
rem
rem  Why read sys.executable instead of calling "py" directly:
rem     py is only a launcher. We need the real interpreter path
rem     to find pythonw.exe next to it.
rem
rem  Comments stay ASCII on purpose: cmd.exe parses this file byte
rem  by byte, and multi-byte UTF-8 can contain bytes such as 0x26
rem  ('&') that get treated as command separators.
rem ============================================================

echo.
echo   正在查找可用的 Python…
echo.

set "PY="
set "TMPPY=%TEMP%\ra_py_path.txt"

for %%C in (python py python3) do (
    if not defined PY (
        %%C -c "import tkinter, sys; print(sys.executable)" > "%TMPPY%" 2>nul && set /p PY=<"%TMPPY%"
    )
)

if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PY (
            "%%P" -c "import tkinter, sys; print(sys.executable)" > "%TMPPY%" 2>nul && set /p PY=<"%TMPPY%"
        )
    )
)
del "%TMPPY%" >nul 2>nul

if not defined PY (
    echo   [失败] 没找到带 tkinter 的 Python。
    echo.
    echo   解决办法（任选一个）：
    echo     1. 重新安装 Python，安装时勾选 "tcl/tk and IDLE"
    echo     2. 如果你有多个 Python，把带 tkinter 的那个放到 PATH 前面
    echo     3. 命令行运行下面这条，把报错发我：
    echo        python desktop_py\app.py
    echo.
    pause
    exit /b 1
)

echo   使用 Python：%PY%
echo   正在启动窗口…
echo.

for %%D in ("%PY%") do set "PYDIR=%%~dpD"
set "PYW=%PYDIR%pythonw.exe"
if not exist "%PYW%" set "PYW=%PY%"

start "" "%PYW%" "%~dp0desktop_py\app.py"

rem give the window a moment, then close this console
ping -n 3 127.0.0.1 >nul 2>&1
exit /b 0
