@echo off
REM ReviewAgent 全局命令包装器
chcp 65001 > nul
python "%~dp0..\review.py" %*
