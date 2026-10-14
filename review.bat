@echo off
REM ReviewAgent CLI Wrapper for Windows
chcp 65001 > nul
python "%~dp0review_cli.py" %*
