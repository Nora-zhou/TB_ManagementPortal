@echo off
chcp 65001 >nul
rem ============================================================
rem  启动带远程调试端口的 Edge / Chrome
rem  用途：让 RPA 以 CDP 模式（RPA_BROWSER_MODE=cdp）直接连接
rem        「当前打开的浏览器」，复用你日常浏览器的登录态，
rem        不再打开一个没有登录态的新窗口。
rem  用法：先完全关闭 Edge / Chrome，再双击运行本脚本。
rem ============================================================

setlocal
set DEBUG_PORT=9222

rem ── 检查浏览器是否还在运行 ──────────────────────────────────
tasklist /fi "imagename eq msedge.exe" 2>nul | find /i "msedge.exe" >nul
if %errorlevel%==0 (
    echo [警告] 检测到 Edge 正在运行。
    echo        请先完全退出 Edge（含托盘图标右键-退出），再运行本脚本。
    pause
    exit /b 1
)
tasklist /fi "imagename eq chrome.exe" 2>nul | find /i "chrome.exe" >nul
if %errorlevel%==0 (
    echo [警告] 检测到 Chrome 正在运行。
    echo        请先完全退出 Chrome，再运行本脚本。
    pause
    exit /b 1
)

rem ── 定位浏览器可执行文件 ────────────────────────────────────
set EDGE="%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist %EDGE% set EDGE="%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist %EDGE% set EDGE="%LocalAppData%\Microsoft\Edge\Application\msedge.exe"

set CHROME="%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%LocalAppData%\Google\Chrome\Application\chrome.exe"

if exist %EDGE% (
    echo 正在启动 Edge（远程调试端口 %DEBUG_PORT%）...
    start "" %EDGE% --remote-debugging-port=%DEBUG_PORT%
) else if exist %CHROME% (
    echo 正在启动 Chrome（远程调试端口 %DEBUG_PORT%）...
    start "" %CHROME% --remote-debugging-port=%DEBUG_PORT%
) else (
    echo 未找到 Edge 或 Chrome。请手动用以下参数启动你的浏览器：
    echo     --remote-debugging-port=%DEBUG_PORT%
    pause
    exit /b 1
)

echo.
echo 浏览器已启动。请保持这个浏览器窗口开着：
echo   - RPA 会直接复用它里面的登录态（淘宝/千牛已登录的话无需再登录）
echo   - RPA 只会新开一个标签页干活，不会动你已经打开的标签页
echo   - 验证调试端口：浏览器访问 http://127.0.0.1:%DEBUG_PORT%/json/version
echo.
pause
