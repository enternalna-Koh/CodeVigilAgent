@echo off
echo ========================================
echo ReviewAgent 诊断工具
echo ========================================
echo.

echo [1] 检查 Python 版本
python --version
echo.

echo [2] 检查当前目录
cd
echo.

echo [3] 检查项目目录
dir D:\Agent-ReviewAgent\chat.py
echo.

echo [4] 运行简化测试
python D:\Agent-ReviewAgent\test_chat.py
echo.

echo [5] 尝试运行完整版
python D:\Agent-ReviewAgent\chat.py
echo.

pause
