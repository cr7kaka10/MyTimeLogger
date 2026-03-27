@echo off
echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Starting build process...
python -m PyInstaller --noconfirm my_time_logger.spec

if %errorlevel% neq 0 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo Success! Output is in .\dist\
pause