@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AIGCTool

echo ============================================
echo   AIGCTool 视频工具合集
echo ============================================
echo.

REM --- 检查 Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+ : https://www.python.org/downloads/
    echo        安装时记得勾选 "Add Python to PATH"。
    pause
    exit /b 1
)

REM --- 首次安装依赖（用标记文件避免每次都装） ---
if not exist ".deps_ok" (
    echo [安装] 首次运行，正在安装 Python 依赖（需要联网，约 1-2 分钟）...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
    echo ok > ".deps_ok"
    echo [完成] 依赖安装完成。
    echo.
)

REM --- 检查 ffmpeg ---
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [提示] 未检测到 ffmpeg：拆分/合并/导出/下载合并 需要它。
    echo        安装命令: winget install ffmpeg   （装完重开本窗口）
    echo.
)

REM --- 启动（pythonw 无黑窗口） ---
start "" pythonw main.py
exit /b 0
