@echo off
setlocal EnableDelayedExpansion

:: ====================================
:: Developer Tools Manager Script
:: ====================================

:: Default versions
set "GIT_VERSION=2.44.0"
set "NODEJS_VERSION=20.11.1"
set "PYTHON_VERSION=3.12.2"
set "DOCKER_VERSION=25.0.3"

:: Setup
set "DOWNLOAD_DIR=%USERPROFILE%\Downloads\DevTools"
if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%" 2>nul

:: Function to refresh environment variables from registry
call :refresh_env_vars

:: Set title and color
title Developer Tools Manager
color 0A

:: Define a temporary file for checking installations
set "TEMP_CHECK=%TEMP%\tool_check.cmd"

:: Find PowerShell path
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL_EXE%" (
  set "POWERSHELL_EXE=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
)
if not exist "%POWERSHELL_EXE%" (
  echo PowerShell not found. Using fallback download method.
  set "USE_PS=0"
) else (
  set "USE_PS=1"
)

:main_menu
cls
echo ====================================
echo      DEVELOPER TOOLS MANAGER
echo ====================================
echo.
echo Current Status:
echo.

:: Check Git
echo Git:      
set git_found=0
for /f "tokens=*" %%i in ('where git 2^>nul') do (
  for /f "tokens=*" %%j in ('git --version 2^>^&1') do (
    echo [INSTALLED] %%j
    set git_found=1
    goto :end_git
  )
)
if %git_found%==0 echo [NOT INSTALLED]
:end_git

:: Check Node.js
echo.
echo Node.js:  
set node_found=0
if exist "%ProgramFiles%\nodejs\node.exe" (
  echo [INSTALLED] Node.js is installed in Program Files
  set node_found=1
  goto :end_node
)
if exist "%ProgramFiles(x86)%\nodejs\node.exe" (
  echo [INSTALLED] Node.js is installed in Program Files (x86)
  set node_found=1
  goto :end_node
)
for /f "tokens=*" %%i in ('where node 2^>nul') do (
  for /f "tokens=*" %%j in ('node --version 2^>^&1') do (
    echo [INSTALLED] v%%j
    set node_found=1
    goto :end_node
  )
)
if %node_found%==0 echo [NOT INSTALLED]
:end_node


:: Check Python
echo.
echo Python:
set python_found=0

if exist "%ProgramFiles%\Python312\python.exe" (
  echo [INSTALLED] Python is installed in Program Files
  set python_found=1
)

if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
  echo [INSTALLED] Python 3 is installed in User's AppData directory
  set python_found=1
)

if exist "%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\python.exe" (
  echo [INSTALLED] Python is installed via Windows Store
  set python_found=1
)

:: Try to execute Python directly
python --version >nul 2>&1
set python_error=%ERRORLEVEL%

if %python_error% EQU 0 (
  for /f "tokens=*" %%i in ('python --version 2^>^&1') do (
    if %python_found%==0 echo [INSTALLED] %%i
    set python_found=1
  )
) else (
  if %python_found%==1 (
    echo [PYTHON IS INSTALLED BUT NOT IN PATH]
  ) else (
    echo [NOT INSTALLED]
  )
)

if %python_found%==0 echo [NOT INSTALLED]

:end_python


:: Check Docker
echo.
echo Docker:   
set docker_found=0
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
  echo [INSTALLED] Docker Desktop is installed in Program Files
  set docker_found=1
  goto :end_docker
) 
if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" (
  echo [INSTALLED] Docker Desktop is installed in Program Files (x86)
  set docker_found=1
  goto :end_docker
) 
for /f "tokens=*" %%i in ('where docker 2^>nul') do (
  for /f "tokens=*" %%j in ('docker --version 2^>^&1') do (
    echo [INSTALLED] %%j
    set docker_found=1
    goto :end_docker
  )
)
if %docker_found%==0 echo [NOT INSTALLED]
:end_docker


echo.
echo ====================================
echo.
echo Select an action:
echo.
echo  1. Install/Update Git
echo  2. Install/Update Node.js
echo  3. Install/Update Python
echo  4. Install/Update Docker
echo  5. Configure Git
echo  6. Start Docker Desktop
echo  7. Uninstall Git
echo  8. Uninstall Node.js
echo  9. Uninstall Python
echo 10. Uninstall Docker
echo 11. Exit
echo.
set /p choice="Enter your choice (1-11): "

if "%choice%"=="1" goto install_git
if "%choice%"=="2" goto install_nodejs
if "%choice%"=="3" goto install_python
if "%choice%"=="4" goto install_docker
if "%choice%"=="5" goto configure_git
if "%choice%"=="6" goto start_docker
if "%choice%"=="7" goto uninstall_git
if "%choice%"=="8" goto uninstall_nodejs
if "%choice%"=="9" goto uninstall_python
if "%choice%"=="10" goto uninstall_docker
if "%choice%"=="11" goto exit_script
echo Invalid choice. Please try again.
timeout /t 2 >nul
goto main_menu

:: ====================================
:: GIT FUNCTIONS
:: ====================================

:install_git
cls
echo ====================================
echo       GIT INSTALLATION
echo ====================================
echo.

:: Check if Git is already installed
where git >nul 2>&1
if %errorlevel% EQU 0 (
  echo Git is already installed:
  for /f "tokens=*" %%i in ('git --version') do echo %%i
  echo.
  set /p confirm="Do you want to reinstall Git? (Y/N): "
  if /i not "%confirm%"=="Y" goto main_menu
)

:: Get Git version
set /p GIT_VERSION="Enter Git version to install (default: %GIT_VERSION%): "

echo.
echo Downloading Git version %GIT_VERSION%...
set "GIT_INSTALLER=%DOWNLOAD_DIR%\Git-%GIT_VERSION%-64-bit.exe"

:: Remove existing installer if present
if exist "%GIT_INSTALLER%" del "%GIT_INSTALLER%"

:: Try to download with PowerShell or bitsadmin as fallback
if %USE_PS%==1 (
  echo Using PowerShell to download...
  "%POWERSHELL_EXE%" -Command "& {$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v%GIT_VERSION%.windows.1/Git-%GIT_VERSION%-64-bit.exe' -OutFile '%GIT_INSTALLER%' -UseBasicParsing } catch { exit 1 }}"
) else (
  echo Using BITS transfer to download...
  bitsadmin /transfer GitDownload /download /priority normal "https://github.com/git-for-windows/git/releases/download/v%GIT_VERSION%.windows.1/Git-%GIT_VERSION%-64-bit.exe" "%GIT_INSTALLER%"
)

if not exist "%GIT_INSTALLER%" (
  echo Failed to download Git installer.
  echo Please check your internet connection and try again.
  echo.
  echo You can also download the installer manually from:
  echo https://github.com/git-for-windows/git/releases/download/v%GIT_VERSION%.windows.1/Git-%GIT_VERSION%-64-bit.exe
  echo.
  pause
  goto main_menu
)

echo Download successful! Installing Git...
echo.
echo Running Git installer...
echo Please complete the installation wizard.
start /wait "" "%GIT_INSTALLER%" /SILENT /COMPONENTS="icons,ext\reg\shells\bash"

echo.
echo Verifying Git installation...
where git >nul 2>&1
if %errorlevel% EQU 0 (
  echo Git installed successfully!
  
  :: Configure Git if needed
  echo.
  set /p config="Would you like to configure Git now? (Y/N): "
  if /i "%config%"=="Y" goto configure_git
) else (
  echo Git installation may have failed.
  echo Try running the installer manually from: %GIT_INSTALLER%
)

echo.
echo Press any key to return to the main menu...
pause >nul
call :refresh_and_goto_main

:configure_git
cls
echo ====================================
echo        GIT CONFIGURATION
echo ====================================
echo.

where git >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Git is not installed. Please install Git first.
  pause
  goto main_menu
)

echo Current Git configuration:
echo.

:: Get current Git username
git config --global user.name >nul 2>&1
if %errorlevel% EQU 0 (
  for /f "tokens=*" %%n in ('git config --global user.name') do echo Username: %%n
) else (
  echo Username: Not set
)

:: Get current Git email
git config --global user.email >nul 2>&1
if %errorlevel% EQU 0 (
  for /f "tokens=*" %%e in ('git config --global user.email') do echo Email: %%e
) else (
  echo Email: Not set
)

echo.
echo Enter new Git configuration:
echo (Leave blank to keep current setting)
echo.

set /p new_username="Username: "
if not "%new_username%"=="" (
  git config --global user.name "%new_username%"
  echo Username updated to: %new_username%
)

set /p new_email="Email: "
if not "%new_email%"=="" (
  git config --global user.email "%new_email%"
  echo Email updated to: %new_email%
)

echo.
echo Git configuration updated.
pause
goto main_menu

:uninstall_git
cls
echo ====================================
echo        GIT UNINSTALLATION
echo ====================================
echo.

where git >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Git is not installed.
  pause
  goto main_menu
)

echo Warning: This will uninstall Git from your system.
set /p confirm="Are you sure you want to continue? (Y/N): "
if /i not "%confirm%"=="Y" goto main_menu

echo.
echo Locating Git uninstaller...
for /f "tokens=*" %%i in ('where git') do set GIT_PATH=%%i
set GIT_ROOT=%GIT_PATH:\cmd\git.exe=%
set GIT_UNINSTALLER=%GIT_ROOT%\unins000.exe

if exist "%GIT_UNINSTALLER%" (
  echo Running Git uninstaller...
  start /wait "" "%GIT_UNINSTALLER%" /SILENT
  
  echo.
  echo Verifying Git uninstallation...
  where git >nul 2>&1
  if %errorlevel% NEQ 0 (
    echo Git has been successfully uninstalled.
  ) else (
    echo Git uninstallation may have failed.
    echo Try uninstalling Git manually through Control Panel.
  )
) else (
  echo Git uninstaller not found.
  echo Please uninstall Git manually through Control Panel.
)

echo.
pause
goto main_menu

:: ====================================
:: NODE.JS FUNCTIONS
:: ====================================

:install_nodejs
cls
echo ====================================
echo       NODE.JS INSTALLATION
echo ====================================
echo.

:: Check if Node.js is already installed
where node >nul 2>&1
if %errorlevel% EQU 0 (
  echo Node.js is already installed:
  for /f "tokens=*" %%i in ('node --version') do echo v%%i
  echo.
  set /p confirm="Do you want to reinstall Node.js? (Y/N): "
  if /i not "%confirm%"=="Y" goto main_menu
)

:: Get Node.js version
set /p NODEJS_VERSION="Enter Node.js version to install (default: %NODEJS_VERSION%): "

echo.
echo Downloading Node.js version %NODEJS_VERSION%...
set "NODEJS_INSTALLER=%DOWNLOAD_DIR%\node-v%NODEJS_VERSION%-x64.msi"

:: Remove existing installer if present
if exist "%NODEJS_INSTALLER%" del "%NODEJS_INSTALLER%"

:: Try to download with PowerShell or bitsadmin as fallback
if %USE_PS%==1 (
  echo Using PowerShell to download...
  "%POWERSHELL_EXE%" -Command "& {$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://nodejs.org/dist/v%NODEJS_VERSION%/node-v%NODEJS_VERSION%-x64.msi' -OutFile '%NODEJS_INSTALLER%' -UseBasicParsing } catch { exit 1 }}"
) else (
  echo Using BITS transfer to download...
  bitsadmin /transfer NodeJSDownload /download /priority normal "https://nodejs.org/dist/v%NODEJS_VERSION%/node-v%NODEJS_VERSION%-x64.msi" "%NODEJS_INSTALLER%"
)

if not exist "%NODEJS_INSTALLER%" (
  echo Failed to download Node.js installer.
  echo Please check your internet connection and try again.
  echo.
  echo You can also download the installer manually from:
  echo https://nodejs.org/dist/v%NODEJS_VERSION%/node-v%NODEJS_VERSION%-x64.msi
  echo.
  pause
  goto main_menu
)

echo Download successful! Installing Node.js...
echo.
echo Running Node.js installer...
start /wait msiexec /i "%NODEJS_INSTALLER%" /qn

echo.
echo Verifying Node.js installation...
where node >nul 2>&1
if %errorlevel% EQU 0 (
  echo Node.js installed successfully!
  for /f "tokens=*" %%i in ('node --version') do echo Version: v%%i
) else (
  echo Node.js installation may have failed.
  echo Try running the installer manually from: %NODEJS_INSTALLER%
)

echo.
echo Press any key to return to the main menu...
pause >nul
call :refresh_and_goto_main

:uninstall_nodejs
cls
echo ====================================
echo       NODE.JS UNINSTALLATION
echo ====================================
echo.

where node >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Node.js is not installed.
  pause
  goto main_menu
)

echo Warning: This will uninstall Node.js from your system.
set /p confirm="Are you sure you want to continue? (Y/N): "
if /i not "%confirm%"=="Y" goto main_menu

echo.
echo Uninstalling Node.js...
for /f "tokens=*" %%v in ('node --version') do set NODE_VER=%%v
set NODE_VER=%NODE_VER:~1%

start /wait msiexec /x "{E4D567B9-F7C9-4889-9B27-67D2D031A347}" /qn
REM Alternative method if the above doesn't work
REM start /wait msiexec /x "%ProgramFiles%\nodejs\node-v%NODE_VER%-x64.msi" /qn

echo.
echo Verifying Node.js uninstallation...
where node >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Node.js has been successfully uninstalled.
) else (
  echo Node.js uninstallation may have failed.
  echo Try uninstalling Node.js manually through Control Panel.
)

echo.
pause
goto main_menu

:: ====================================
:: PYTHON FUNCTIONS
:: ====================================

:install_python
cls
echo ====================================
echo       PYTHON INSTALLATION
echo ====================================
echo.

:: Check if Python is already installed (using more reliable method)
python --version >nul 2>&1
if not errorlevel 1 (
  echo Python is already installed:
  for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo %%i
  echo.
  set /p confirm="Do you want to reinstall Python? (Y/N): "
  if /i not "%confirm%"=="Y" goto main_menu
) else (
  echo Checking for Python in alternate locations...
  
  :: Check Program Files location
  if exist "%ProgramFiles%\Python*\python.exe" (
    echo Python is installed but not in PATH.
    echo Will reinstall with PATH option enabled.
  ) else if exist "%ProgramFiles(x86)%\Python*\python.exe" (
    echo Python is installed but not in PATH.
    echo Will reinstall with PATH option enabled.
  ) else (
    echo Python does not appear to be installed.
  )
)

:: Get Python version
set /p PYTHON_VERSION="Enter Python version to install (default: %PYTHON_VERSION%): "

echo.
echo Downloading Python version %PYTHON_VERSION%...
set "PYTHON_INSTALLER=%DOWNLOAD_DIR%\python-%PYTHON_VERSION%-amd64.exe"

:: Remove existing installer if present
if exist "%PYTHON_INSTALLER%" del "%PYTHON_INSTALLER%"

:: Try to download with PowerShell or bitsadmin as fallback
if %USE_PS%==1 (
  echo Using PowerShell to download...
  "%POWERSHELL_EXE%" -Command "& {$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing } catch { exit 1 }}"
) else (
  echo Using BITS transfer to download...
  bitsadmin /transfer PythonDownload /download /priority normal "https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe" "%PYTHON_INSTALLER%"
)

if not exist "%PYTHON_INSTALLER%" (
  echo Failed to download Python installer.
  echo Please check your internet connection and try again.
  echo.
  echo You can also download the installer manually from:
  echo https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
  echo.
  pause
  goto main_menu
)

:: Before installing, try to disable Python app execution alias
echo Checking for Python app execution aliases...
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe" >nul 2>&1
if not errorlevel 1 (
  echo Disabling Python app execution aliases to prevent conflicts...
  reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe" /f >nul 2>&1
)

echo Download successful! Installing Python...
echo.
echo Running Python installer with PATH option enabled...
echo Note: This will override any Microsoft Store Python aliases.
start /wait "" "%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1 AssociateFiles=1

echo.
echo Installation complete. Opening a new command prompt to refresh environment...
echo.
echo You may need to close and reopen any command prompts after installation.
echo.

:: Create a batch file to test Python
set "PYTHON_TEST=%TEMP%\test_python.cmd"
echo @echo off > "%PYTHON_TEST%"
echo echo Testing Python installation... >> "%PYTHON_TEST%"
echo python --version >> "%PYTHON_TEST%"
echo if errorlevel 1 ( >> "%PYTHON_TEST%"
echo   echo Python is still not in PATH. >> "%PYTHON_TEST%"
echo   echo You may need to restart your computer. >> "%PYTHON_TEST%"
echo ) else ( >> "%PYTHON_TEST%"
echo   echo Python was successfully installed and is in PATH. >> "%PYTHON_TEST%"
echo ) >> "%PYTHON_TEST%"
echo echo. >> "%PYTHON_TEST%"
echo pause >> "%PYTHON_TEST%"
echo goto :eof >> "%PYTHON_TEST%"

start cmd /c "%PYTHON_TEST%"

echo.
echo Press any key to return to the main menu...
pause >nul
call :refresh_and_goto_main

:uninstall_python
cls
echo ====================================
echo       PYTHON UNINSTALLATION
echo ====================================
echo.

where python >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Python is not installed.
  pause
  goto main_menu
)

echo Warning: This will uninstall Python from your system.
set /p confirm="Are you sure you want to continue? (Y/N): "
if /i not "%confirm%"=="Y" goto main_menu

echo.
echo Locating Python installation...
for /f "tokens=*" %%i in ('where python') do set PYTHON_PATH=%%i

:: Check if it's a Windows Store Python
echo %PYTHON_PATH% | find "WindowsApps" >nul
if %errorlevel% EQU 0 (
  echo Detected Windows Store Python installation.
  echo Please uninstall Python through the Windows Settings app.
  echo Settings -^> Apps -^> Apps ^& features -^> Python
  pause
  goto main_menu
)

:: Get Python directory
for %%i in ("%PYTHON_PATH%") do set PYTHON_DIR=%%~dpi
set PYTHON_DIR=%PYTHON_DIR:~0,-1%

if exist "%PYTHON_DIR%\uninstall.exe" (
  echo Running Python uninstaller...
  start /wait "" "%PYTHON_DIR%\uninstall.exe" /quiet
) else (
  echo Python uninstaller not found.
  echo Please uninstall Python manually through Control Panel.
)

echo.
echo Verifying Python uninstallation...
where python >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Python has been successfully uninstalled.
) else (
  echo Python uninstallation may have failed.
  echo Please uninstall Python manually through Control Panel.
)

echo.
pause
goto main_menu

:: ====================================
:: DOCKER FUNCTIONS
:: ====================================

:install_docker
cls
echo ====================================
echo       DOCKER INSTALLATION
echo ====================================
echo.

:: Check if Docker is already installed
where docker >nul 2>&1
if %errorlevel% EQU 0 (
  echo Docker is already installed:
  for /f "tokens=*" %%i in ('docker --version') do echo %%i
  echo.
  set /p confirm="Do you want to reinstall Docker? (Y/N): "
  if /i not "%confirm%"=="Y" goto main_menu
)

:: Get Docker version (Desktop installer doesn't have version in filename)
set /p DOCKER_VERSION="Enter Docker version to install (default: %DOCKER_VERSION%): "

echo.
echo Downloading Docker Desktop...
set "DOCKER_INSTALLER=%DOWNLOAD_DIR%\Docker-Desktop-Installer.exe"

:: Remove existing installer if present
if exist "%DOCKER_INSTALLER%" del "%DOCKER_INSTALLER%"

:: Try to download with PowerShell or bitsadmin as fallback
if %USE_PS%==1 (
  echo Using PowerShell to download...
  "%POWERSHELL_EXE%" -Command "& {$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker%%20Desktop%%20Installer.exe' -OutFile '%DOCKER_INSTALLER%' -UseBasicParsing } catch { exit 1 }}"
) else (
  echo Using BITS transfer to download...
  bitsadmin /transfer DockerDownload /download /priority normal "https://desktop.docker.com/win/main/amd64/Docker%%20Desktop%%20Installer.exe" "%DOCKER_INSTALLER%"
)

if not exist "%DOCKER_INSTALLER%" (
  echo Failed to download Docker installer.
  echo Please check your internet connection and try again.
  echo.
  echo You can also download the installer manually from:
  echo https://desktop.docker.com/win/main/amd64/Docker%%20Desktop%%20Installer.exe
  echo.
  pause
  goto main_menu
)

echo Download successful! Installing Docker Desktop...
echo.

:: Check if WSL2 is installed
wsl --status >nul 2>&1
if %errorlevel% NEQ 0 (
  echo WARNING: WSL2 may not be installed or enabled.
  echo Docker Desktop requires WSL2 to be enabled.
  echo.
  echo Would you like to:
  echo 1. Continue with Docker installation
  echo 2. Open WSL installation instructions first
  echo 3. Cancel and return to main menu
  echo.
  set /p wsl_choice="Enter your choice (1-3): "
  
  if "%wsl_choice%"=="2" (
    start "" "https://docs.microsoft.com/en-us/windows/wsl/install"
    echo Please return to this script after installing WSL2.
    pause
  )
  if "%wsl_choice%"=="3" goto main_menu
)

echo Running Docker Desktop installer...
echo Please complete the installation wizard.
echo Note: You may need to restart your computer after installation.
start /wait "" "%DOCKER_INSTALLER%" install

echo.
echo Verifying Docker installation...
call :refresh_env_vars
where docker >nul 2>&1
if %errorlevel% EQU 0 (
  echo Docker Desktop installed successfully!
  echo.
  echo Would you like to start Docker Desktop now? (Y/N): 
  set /p start_docker="Enter your choice: "
  if /i "%start_docker%"=="Y" goto start_docker
) else (
  echo Docker installation may have completed but requires system restart.
  echo Try running the installer manually from: %DOCKER_INSTALLER%
  echo or restart your computer to complete the installation.
)

echo.
echo Press any key to return to the main menu...
pause >nul
call :refresh_and_goto_main

:start_docker
cls
echo ====================================
echo      STARTING DOCKER DESKTOP
echo ====================================
echo.

:: Check if Docker is installed
where docker >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Docker is not installed. Please install Docker first.
  pause
  goto main_menu
)

:: Check if Docker Desktop is already running
docker ps >nul 2>&1
if %errorlevel% EQU 0 (
  echo Docker Desktop is already running.
  
  :: Display running containers
  echo.
  echo Currently running containers:
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
  
  echo.
  pause
  goto main_menu
)

echo Starting Docker Desktop...
echo This may take a few moments...

:: Find Docker Desktop path and start it
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
) else if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe" (
  start "" "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
) else (
  echo Could not find Docker Desktop executable.
  echo Please start Docker Desktop manually.
  pause
  goto main_menu
)

:: Wait for Docker to start
echo Waiting for Docker to start...
:wait_for_docker
timeout /t 2 /nobreak >nul
docker ps >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Docker Desktop is starting. Please wait...
  goto wait_for_docker
)

echo Docker Desktop started successfully!
echo.
echo Docker version:
docker --version
echo.
echo Docker Desktop is now running.
pause
goto main_menu

:refresh_and_goto_main
:: Call the refresh function to update PATH
call :refresh_env_vars
goto main_menu

:uninstall_docker
cls
echo ====================================
echo       DOCKER UNINSTALLATION
echo ====================================
echo.

where docker >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Docker is not installed.
  pause
  goto main_menu
)

echo Warning: This will uninstall Docker Desktop from your system.
set /p confirm="Are you sure you want to continue? (Y/N): "
if /i not "%confirm%"=="Y" goto main_menu

echo.
echo Stopping Docker services...
taskkill /f /im "Docker Desktop.exe" >nul 2>&1
net stop com.docker.service >nul 2>&1

echo Uninstalling Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop Installer.exe" (
  start /wait "" "%ProgramFiles%\Docker\Docker\Docker Desktop Installer.exe" uninstall
) else if exist "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop Installer.exe" (
  start /wait "" "%ProgramFiles(x86)%\Docker\Docker\Docker Desktop Installer.exe" uninstall
) else (
  echo Docker Desktop uninstaller not found.
  echo Please uninstall Docker manually through Control Panel.
)

echo.
echo Verifying Docker uninstallation...
where docker >nul 2>&1
if %errorlevel% NEQ 0 (
  echo Docker has been successfully uninstalled.
) else (
  echo Docker uninstallation may have failed.
  echo Try uninstalling Docker manually through Control Panel.
)

echo.
pause
goto main_menu

:: ====================================
:: HELPER FUNCTIONS
:: ====================================

:refresh_env_vars
:: This function refreshes environment variables from the registry
echo Refreshing environment variables...

:: Get System PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"

:: Get User PATH
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"

:: Combine paths
if defined SYS_PATH (
  if defined USER_PATH (
    set "PATH=%SYS_PATH%;%USER_PATH%"
  ) else (
    set "PATH=%SYS_PATH%"
  )
) else if defined USER_PATH (
  set "PATH=%USER_PATH%"
)

:: Also check standard install locations directly
set "PATH=%PATH%;%ProgramFiles%\Git\cmd;%ProgramFiles(x86)%\Git\cmd"
set "PATH=%PATH%;%ProgramFiles%\nodejs;%ProgramFiles(x86)%\nodejs"
set "PATH=%PATH%;%ProgramFiles%\Python*;%ProgramFiles(x86)%\Python*"
set "PATH=%PATH%;%ProgramFiles%\Docker\Docker\resources\bin"
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python*;%APPDATA%\Python\Python*"

echo PATH updated.
goto :eof

:exit_script
cls
echo ====================================
echo        EXITING SCRIPT
echo ====================================
echo.
echo Thank you for using the Developer Tools Manager.
echo.
echo Press any key to exit...
pause >nul
exit /b