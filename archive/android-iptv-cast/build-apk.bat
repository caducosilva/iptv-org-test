@echo off
setlocal
cd /d "%~dp0"

set "JAVA_HOME=%ProgramFiles%\Microsoft\jdk-17.0.20.8-hotspot"
if not exist "%JAVA_HOME%\bin\java.exe" set "JAVA_HOME=%ProgramFiles%\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"

> local.properties echo sdk.dir=%ANDROID_HOME:\=\\%

if not exist "gradle\wrapper\gradle-wrapper.jar" (
  echo ERRO: gradle-wrapper.jar ausente. Rode setup-wrapper.bat antes.
  exit /b 1
)

call gradlew.bat assembleDebug --no-daemon
if errorlevel 1 exit /b 1

set "APK=%~dp0app\build\outputs\apk\debug\app-debug.apk"
set "OUT=%USERPROFILE%\Desktop\IPTV-Cast-android-debug.apk"
copy /Y "%APK%" "%OUT%" >nul
echo.
echo OK APK: %APK%
echo Copia Desktop: %OUT%
endlocal
