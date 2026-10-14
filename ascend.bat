@echo off
chcp 65001 > nul
python "%~dp0ascend_cli.py" %*
