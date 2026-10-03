@echo off
setlocal
title Tradurre
rem Double-click launcher for Tradurre.
rem On first run it installs uv and Tradurre, then starts Tradurre. If a
rem different version of Tradurre is installed, it first installs this
rem launcher's version (no network check: a newer launcher means an upgrade).
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
echo Installing Tradurre...
uv.exe tool install --force "%SPEC%"
if errorlevel 1 if defined UPDATING goto fail_update
if errorlevel 1 goto fail_tradurre
rem Make tradurre available in future terminals too.
uv.exe tool update-shell >nul 2>nul
echo.
echo Tradurre %VERSION% is installed.
echo.

:run
tradurre.exe %*
if errorlevel 1 pause
exit /b

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
rem Keep working offline or if the update fails: start the installed version.
echo.
echo Could not update Tradurre (see the messages above). If Tradurre is already
echo open in another window, close it and run this file again.
echo Starting the installed version instead...
echo.
goto run
