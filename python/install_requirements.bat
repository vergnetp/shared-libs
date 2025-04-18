@echo off

>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Please run this as admin
    pause
    exit /b 1
)
pip install -r %~dp0requirements.txt
pause
exit /b 0