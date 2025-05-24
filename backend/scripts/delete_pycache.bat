@echo off
echo Please run this as admin to delete all pycache folders in "%~dp0"
pause
for /d /r "%~dp0" %%d in (__pycache__) do (
    echo Deleting "%%d"
    rmdir /s /q "%%d"
)