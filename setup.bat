@echo off
setlocal enabledelayedexpansion

:: OpenSpace WebRTC Rendering Server Setup Script
:: This script automates the setup process described in README.md
:: Usage: setup_openspace.bat [IP_ADDRESS]
:: If no IP address is provided, defaults to 127.0.0.1

echo ==========================================
echo OpenSpace WebRTC Rendering Server Setup
echo ==========================================
echo.

:: Get server IP from command line argument or use default
if "%~1"=="" (
    set "SERVER_IP=127.0.0.1"
    echo [INFO] No IP address provided as argument, using default: 127.0.0.1
) else (
    set "SERVER_IP=%~1"
    echo [INFO] Using provided IP address: %~1
)

:: Step 1: Check for Node.js and npm
echo [INFO] Checking for Node.js and npm...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo Please download and install Node.js from: https://nodejs.org/en/
    echo After installation, restart this script.
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
    echo [SUCCESS] Node.js found: !NODE_VERSION!
)

:: Step 2: Check for Python
echo [INFO] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from: https://www.python.org/downloads/
    echo Make sure to check 'Add Python to PATH' during installation.
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
    echo [SUCCESS] Python found: !PYTHON_VERSION!
)

:: Check for pip
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip is not installed or not in PATH.
    echo pip should come with Python installation.
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('pip --version') do set PIP_VERSION=%%i
    echo [SUCCESS] pip found: !PIP_VERSION!
)

:: Step 3: Install required Python libraries
echo [INFO] Installing required Python libraries...
echo Installing openspace-api...
pip install openspace-api
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install openspace-api
    pause
    exit /b 1
)

echo Installing websockets...
pip install websockets
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install websockets
    pause
    exit /b 1
)

echo Installing psutil...
pip install psutil
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install psutil
    pause
    exit /b 1
)

echo [SUCCESS] All Python libraries installed successfully!

:: Step 5: Server IP is already set from command line argument or default
echo [SUCCESS] Server IP configured: !SERVER_IP!

:: Step 6: Check for OpenSpace submodule
echo [INFO] Checking OpenSpace submodule...
if not exist "OpenSpace" (
    echo [ERROR] OpenSpace submodule directory not found.
    echo Make sure you cloned with --recursive flag.
    echo You can run: git submodule update --init --recursive
    pause
    exit /b 1
)

if not exist "OpenSpace\feature" (
    echo [WARNING] OpenSpace submodule may not be properly initialized.
    echo You may need to run: git submodule update --init --recursive
)

:: Step 7: CMake and Visual Studio build instructions
echo [INFO] Checking for OpenSpace/bin/RelWithDebInfo/OpenSpace.exe...
if not exist "OpenSpace/bin/RelWithDebInfo/OpenSpace.exe" (
    cd OpenSpace
    cmake -B build
    cmake --build build --config RelWithDebInfo
)

:: Step 8: Configure OpenSpace-WebGuiFrontend
echo [INFO] Configuring OpenSpace-WebGuiFrontend...
if not exist "OpenSpace-WebGuiFrontend" (
    echo [ERROR] OpenSpace-WebGuiFrontend directory not found.
    pause
    exit /b 1
)

:: Create backup of original Environment.js
if exist "OpenSpace-WebGuiFrontend\src\api\Environment.js" (
    if not exist "OpenSpace-WebGuiFrontend\src\api\Environment.js.backup" (
        copy "OpenSpace-WebGuiFrontend\src\api\Environment.js" "OpenSpace-WebGuiFrontend\src\api\Environment.js.backup"
        echo [INFO] Created backup of Environment.js
    )
    
    :: Update Environment.js with server IP
    echo [INFO] Updating Environment.js with server IP: !SERVER_IP!
    powershell -Command "(Get-Content 'OpenSpace-WebGuiFrontend\src\api\Environment.js') -replace 'wsAddress.*:.*[,]', 'wsAddress: \"!SERVER_IP!\",    ' | Set-Content 'OpenSpace-WebGuiFrontend\src\api\Environment.js'"
    powershell -Command "(Get-Content 'OpenSpace-WebGuiFrontend\src\api\Environment.js') -replace 'signalingAddress.*:.*[,]', 'signalingAddress: \"!SERVER_IP!\",    ' | Set-Content 'OpenSpace-WebGuiFrontend\src\api\Environment.js'"
)

:: Step 9: Install npm dependencies for WebGuiFrontend
echo [INFO] Installing npm dependencies for WebGuiFrontend...
cd OpenSpace-WebGuiFrontend
cmd /c "npm install --legacy-peer-deps"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install WebGuiFrontend dependencies
    cd ..
    pause
    exit /b 1
)

echo [SUCCESS] WebGuiFrontend dependencies installed!

:: Step 10: Setup signaling server
echo [INFO] Setting up signaling server...
cd src\signalingserver
cmd /c "npm install --legacy-peer-deps"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install signaling server dependencies
    cd ..\..\..\
    pause
    exit /b 1
)

echo [SUCCESS] Signaling server dependencies installed!
cd ..\..\..\

:: Step 11: Check firewall and networking
echo [INFO] Networking setup information...
echo.
echo [WARNING] MANUAL NETWORKING STEPS REQUIRED:
echo 1. Ensure ports 4680-4700 and 8443 are open in Windows Firewall
echo 2. Configure router/network firewall if applicable
echo 3. Consider SSL certificate for HTTPS (recommended)
echo.
echo If you need to allow insecure origins in Chrome:
echo   - Go to chrome://flags
echo   - Add "http://!SERVER_IP!:4690" to "Insecure origins treated as secure"
echo.

:: Step 12: Check OPENSPACE_SYNC environment variable
echo [INFO] Checking OPENSPACE_SYNC environment variable...
if not defined OPENSPACE_SYNC (
    echo [WARNING] OPENSPACE_SYNC environment variable is not set.
    echo This is required if you plan to add multiple rendering instances.
    echo You can set it to a shared sync folder path.
    echo.
    set /p SET_SYNC="Do you want to set OPENSPACE_SYNC now? (y/n): "
    if /i "!SET_SYNC!"=="y" (
        set /p SYNC_PATH="Enter the sync folder path: "
        setx OPENSPACE_SYNC "!SYNC_PATH!"
        echo [SUCCESS] OPENSPACE_SYNC set to !SYNC_PATH!
        echo [WARNING] You may need to restart the command prompt for this to take effect.
    )
) else (
    echo [SUCCESS] OPENSPACE_SYNC is set to: %OPENSPACE_SYNC%
)

:: Step 13: Final summary
echo.
echo ==========================================
echo [SUCCESS] Setup completed successfully!
echo ==========================================
echo.
echo Server IP configured: !SERVER_IP!
echo.
echo To run the system:
echo 1. Run: python supervisor.py
echo 2. Access via browser: http://!SERVER_IP!:4690/frontend/#/streaming?id=0
echo.
echo Additional steps you may need to complete manually:
echo - Configure SSL certificate for HTTPS
echo - Set up firewall rules for ports 4680-4700, 8443
echo - Adjust video quality settings in OpenSpace configuration
echo.
echo [INFO] Setup script completed. Check the README.md for additional configuration details.

pause
endlocal