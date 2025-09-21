@echo off
chcp 65001 >nul
echo.
echo ====================================
echo    C盘自动清理工具 v1.0.0
echo ====================================
echo.
echo 正在启动程序...
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误：未找到Python环境！
    echo 请先安装Python 3.6或更高版本。
    echo.
    pause
    exit /b 1
)

REM 检查是否有管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 提示：建议以管理员权限运行此程序以获得最佳清理效果。
    echo.
)

REM 运行主程序
python main.py

if %errorlevel% neq 0 (
    echo.
    echo 程序执行过程中出现错误！
    pause
)

echo.
echo 程序已结束。
pause
