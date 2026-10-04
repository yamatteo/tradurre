@echo off
setlocal
title Tradurre
rem Double-click launcher for Tradurre.
rem On first run it installs uv and Tradurre, then starts Tradurre. If a
rem different version of Tradurre is installed, it first installs this
rem launcher's version (no network check: a newer launcher means an upgrade).
rem If uv fails to remove the old version (Windows may be scanning its files),
rem it deletes it and tries once more. For PDF support it installs the
rem Microsoft Visual C++ Redistributable when Windows doesn't have it.
rem Keep this window open while you work; closing it stops Tradurre.

rem Filled in by the release workflow with this release's version and wheel URL.
set "VERSION=__VERSION__"
set "WHEEL_URL=__WHEEL_URL__"
rem Extras to install on first run, e.g. "pdf". Leave empty for none.
set "EXTRAS=pdf"

rem uv's default install folder, which is also where uv puts tool commands
rem such as tradurre.exe. Added to PATH for this window only, so a fresh
rem install is found without opening a new terminal.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

rem Always call tradurre.exe with its extension: a bare "tradurre" could
rem resolve to a .bat in the current folder (cmd searches it before PATH).
where tradurre.exe >nul 2>nul
if errorlevel 1 goto not_installed

rem Already installed: switch to this launcher's version if it differs.
rem Versions before --version existed print nothing here, so they upgrade too.
if "%VERSION:~0,2%"=="__" goto run
set "INSTALLED="
for /f "tokens=2" %%v in ('tradurre.exe --version 2^>nul') do set "INSTALLED=%%v"
if "%INSTALLED%"=="%VERSION%" goto run
if not defined INSTALLED set "INSTALLED=an older version"
echo Updating Tradurre from %INSTALLED% to %VERSION%...
echo.
set "UPDATING=1"
goto install

:not_installed
echo Tradurre is not installed yet. Installing it now...
echo.

:install
where uv.exe >nul 2>nul
if not errorlevel 1 goto install_tradurre

echo Installing uv...
powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
where uv.exe >nul 2>nul
if errorlevel 1 goto fail_uv

:install_tradurre
if "%WHEEL_URL:~0,2%"=="__" goto fail_url
set "SPEC=%WHEEL_URL%"
if defined EXTRAS set "SPEC=tradurre[%EXTRAS%] @ %WHEEL_URL%"
set "INSTALL_LOG=%TEMP%\tradurre-install.log"
echo Installing Tradurre (this can take a few minutes)...
call :uv_install
if not errorlevel 1 goto installed
rem uv can fail to remove the old version (os error 32, while Windows scans its
rem files), leaving it half-deleted: nothing left to keep. Delete it and try
rem once more. Only uv's copy of Tradurre goes; the books are in .tradurre.
rem Any other failure (offline, a bad download) deletes nothing.
findstr /c:"failed to remove directory" "%INSTALL_LOG%" >nul 2>nul
if errorlevel 1 goto install_failed
set "TOOLS="
for /f "delims=" %%d in ('uv.exe tool dir 2^>nul') do set "TOOLS=%%d"
if defined TOOLS rmdir /s /q "%TOOLS%\tradurre" >nul 2>nul
echo.
echo Retrying the install of Tradurre...
call :uv_install
if errorlevel 1 goto install_failed

:installed
rem Make tradurre available in future terminals too.
uv.exe tool update-shell >nul 2>nul
echo.
echo Tradurre %VERSION% is installed.
echo.

:run
rem PDF support needs the Visual C++ runtime: see :ensure_vcredist.
if exist "%SystemRoot%\System32\msvcp140.dll" goto start
if defined EXTRAS echo(%EXTRAS%| findstr /i "pdf" >nul && call :ensure_vcredist

:start
tradurre.exe %*
if errorlevel 1 pause
exit /b

:uv_install
rem uv's output goes to a log, so the launcher can read its error, and is
rem then shown as usual.
uv.exe tool install --force --python 3.14 "%SPEC%" >"%INSTALL_LOG%" 2>&1
set "UV_RC=%errorlevel%"
type "%INSTALL_LOG%"
exit /b %UV_RC%

:ensure_vcredist
rem PDF support (pymupdf) needs MSVCP140.dll from the Microsoft Visual C++
rem Redistributable, which not every Windows has: Python brings only
rem vcruntime140.dll. The installer asks for administrator rights itself.
echo PDF support needs the Microsoft Visual C++ Redistributable. Installing it now...
echo Windows will ask for permission.
echo.
set "VCREDIST=%TEMP%\vc_redist.x64.exe"
curl.exe -fsSL -o "%VCREDIST%" "https://aka.ms/vs/17/release/vc_redist.x64.exe"
if errorlevel 1 goto vcredist_failed
"%VCREDIST%" /install /passive /norestart
set "VCREDIST_RC=%errorlevel%"
del "%VCREDIST%" >nul 2>nul
rem 0 installed, 3010 installed (restart suggested), 1638 a newer one is there.
if "%VCREDIST_RC%"=="0" exit /b 0
if "%VCREDIST_RC%"=="3010" exit /b 0
if "%VCREDIST_RC%"=="1638" exit /b 0

:vcredist_failed
del "%VCREDIST%" >nul 2>nul
echo.
echo Could not install the Microsoft Visual C++ Redistributable. Tradurre will
echo start, but importing PDF files won't work until you install it by hand:
echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
exit /b 0

:install_failed
if defined UPDATING goto fail_update
goto fail_tradurre

:fail_uv
echo.
echo Could not install uv. Install it by hand, then run this file again:
echo   https://docs.astral.sh/uv/getting-started/installation/
pause
exit /b 1

:fail_url
echo.
echo This launcher has no download link built in. Download it from the
echo latest release instead: https://github.com/yamatteo/tradurre/releases/latest
pause
exit /b 1

:fail_tradurre
echo.
echo Could not install Tradurre. See the messages above, or install it by hand:
echo   https://github.com/yamatteo/tradurre#install
pause
exit /b 1

:fail_update
rem Keep working offline or if the update fails: start the installed version,
rem if it still runs (a failed update can leave it half-deleted). --help loads
rem the whole app, and works on v0.1.0 too, which has no --version.
echo.
echo Could not update Tradurre (see the messages above). If Tradurre is already
echo open in another window, close it and run this file again.
tradurre.exe --help >nul 2>nul
if errorlevel 1 goto fail_broken
echo Starting the installed version instead...
echo.
goto run

:fail_broken
echo.
echo Tradurre could not be updated, and the version installed before no longer
echo works. Your books are safe in %USERPROFILE%\.tradurre.
echo Close any Tradurre window and run this file again. If it keeps failing,
echo install uv and Tradurre by hand:
echo   https://docs.astral.sh/uv/getting-started/installation/
echo   https://github.com/yamatteo/tradurre#install
pause
exit /b 1
