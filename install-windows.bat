@echo off
rem Installs mosaic on Windows. Double-click this file (if Windows says it protected your
rem PC, click "More info" and then "Run anyway").
rem
rem It installs conda (Miniforge, in your user folder; see MF_DIR below) if you don't have conda yet, makes a conda
rem environment called "mosaic" with everything mosaic needs, and adds mosaic to
rem the Start menu and the desktop. Running it again updates an earlier installation. It needs
rem an internet connection and about 2 GB of disk space; the first run takes 5-15 minutes.
rem
rem mosaic's own updates run this file from the new version (mosaic\updates.py), with
rem MOSAIC_UPDATE=1 (no questions), MOSAIC_PREFIX (the environment to update; conda is
rem needed only if environment.yml changed), MOSAIC_WAIT_PID (wait for mosaic to
rem close), MOSAIC_RESULT (a file to write "ok" or "failed: why" to) and MOSAIC_LOCK (a
rem file to delete at the end).
rem
rem For testing: MOSAIC_ENV (environment name), MOSAIC_NO_OPEN=1 (don't start
rem mosaic or wait for a key at the end).
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ENV_NAME=%MOSAIC_ENV%"
if "%ENV_NAME%"=="" set "ENV_NAME=mosaic"
if not exist environment.yml (
  set "WHY=run this file from inside the mosaic folder you downloaded"
  goto failed
)

rem Where conda goes if it has to be installed: your user folder, unless that folder's name has a
rem space or a letter outside plain English in it (Miniforge refuses those): then a folder of its
rem own on the system drive, named after the account in plain letters.
set "MF_DIR=%USERPROFILE%\miniforge3"
powershell -NoProfile -Command "if ($env:USERPROFILE -match '\s|\P{IsBasicLatin}') { exit 1 }"
if errorlevel 1 (
  set "MF_USER="
  powershell -NoProfile -Command "$env:USERNAME -replace '\P{IsBasicLatin}','' -replace '\W',''" > "%TEMP%\mosaic-user.txt"
  if exist "%TEMP%\mosaic-user.txt" set /p MF_USER=<"%TEMP%\mosaic-user.txt"
  del "%TEMP%\mosaic-user.txt" >nul 2>nul
  if not defined MF_USER set "MF_USER=user"
  set "MF_DIR=%SystemDrive%\miniforge3-!MF_USER!"
)

rem 0. An update from mosaic itself: it closes first
if defined MOSAIC_WAIT_PID (
  echo.
  echo ==^> Waiting for mosaic to close
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Wait-Process -Id %MOSAIC_WAIT_PID% -Timeout 300 -ErrorAction SilentlyContinue; if (Get-Process -Id %MOSAIC_WAIT_PID% -ErrorAction SilentlyContinue) { exit 1 }"
  if errorlevel 1 (
    set "WHY=mosaic didn't close"
    goto failed
  )
)

set "ENV_HASH="
if defined MOSAIC_PREFIX goto update_env

rem 1. Conda: use the one you have, or install Miniforge
call :find_conda
if not defined CONDA (
  echo.
  echo ==^> Installing conda ^(Miniforge^) into !MF_DIR!
  if exist "!MF_DIR!" (
    set "WHY=!MF_DIR! exists but has no conda in it; move it aside and try again"
    goto failed
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe' -OutFile (Join-Path $env:TEMP 'Miniforge3-Windows-x86_64.exe')"
  if errorlevel 1 (
    set "WHY=Miniforge couldn't be downloaded; check the internet connection"
    goto failed
  )
  start "" /wait "%TEMP%\Miniforge3-Windows-x86_64.exe" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=!MF_DIR!
  del "%TEMP%\Miniforge3-Windows-x86_64.exe" >nul 2>nul
  set "CONDA=!MF_DIR!\Scripts\conda.exe"
  if not exist "!CONDA!" (
    set "WHY=Miniforge didn't install"
    goto failed
  )
)
echo.
echo ==^> Using conda at %CONDA%

rem 2. The environment: made the first time, brought up to date after that
"%CONDA%" env list | findstr /b /c:"%ENV_NAME% " >nul
if errorlevel 1 (
  echo.
  echo ==^> Making the "%ENV_NAME%" environment ^(this downloads the tools mosaic uses^)
  "%CONDA%" env create -n "%ENV_NAME%" -f environment.yml
) else (
  echo.
  echo ==^> Updating the "%ENV_NAME%" environment
  "%CONDA%" env update -n "%ENV_NAME%" -f environment.yml --prune
)
if errorlevel 1 (
  set "WHY=the conda environment couldn't be made (the messages above say why)"
  goto failed
)
rem The environment's folder, from its own Python (it isn't always inside conda's folder); read
rem back from a file, since a for /f around this command would need its quotes and brackets escaped
set "PREFIX="
set "PREFIX_FILE=%TEMP%\mosaic-prefix.txt"
"%CONDA%" run -n "%ENV_NAME%" python -c "import sys; print(sys.prefix)" > "%PREFIX_FILE%"
if exist "%PREFIX_FILE%" set /p PREFIX=<"%PREFIX_FILE%"
del "%PREFIX_FILE%" >nul 2>nul
if not defined PREFIX (
  set "WHY=the new environment's Python couldn't be found"
  goto failed
)
goto env_done

rem 2. An update: the environment mosaic runs in, brought up to date only if what it needs changed
:update_env
set "PREFIX=%MOSAIC_PREFIX%"
if not exist "%PREFIX%\python.exe" (
  set "WHY=mosaic's environment isn't in %PREFIX% any more"
  goto failed
)
call :env_hash
set "OLD_HASH="
if exist "%PREFIX%\etc\mosaic\environment.sha256" set /p OLD_HASH=<"%PREFIX%\etc\mosaic\environment.sha256"
if defined ENV_HASH if /i "%OLD_HASH%"=="%ENV_HASH%" (
  echo.
  echo ==^> The tools mosaic uses are up to date
  goto env_done
)
call :find_conda
if not defined CONDA (
  set "WHY=this update needs conda, and conda wasn't found"
  goto failed
)
echo.
echo ==^> Updating the tools mosaic uses ^(this can take a few minutes^)
"%CONDA%" env update -p "%PREFIX%" -f environment.yml --prune
if errorlevel 1 (
  set "WHY=the tools mosaic uses couldn't be updated (the log says why)"
  goto failed
)

:env_done
if not exist "%PREFIX%\python.exe" (
  set "WHY=mosaic's environment isn't in %PREFIX%"
  goto failed
)
if not exist "%PREFIX%\etc\mosaic" mkdir "%PREFIX%\etc\mosaic"
if not defined ENV_HASH call :env_hash
if defined ENV_HASH (echo !ENV_HASH!)>"%PREFIX%\etc\mosaic\environment.sha256"

rem 3. mosaic itself, copied into the environment (this folder can be deleted afterwards)
echo.
echo ==^> Installing mosaic
"%PREFIX%\python.exe" -m pip install --upgrade --no-warn-script-location .
if errorlevel 1 (
  set "WHY=mosaic couldn't be installed (the messages above say why)"
  goto failed
)

rem 4. Shortcuts in the Start menu and on the desktop (an update keeps a desktop shortcut only if there is one)
echo.
echo ==^> Adding mosaic to the Start menu and the desktop
set "SHORTCUT_ARGS="
if defined MOSAIC_UPDATE set "SHORTCUT_ARGS=--update"
"%PREFIX%\python.exe" packaging\windows\make_shortcuts.py %SHORTCUT_ARGS%
if errorlevel 1 (
  set "WHY=the shortcuts couldn't be made; mosaic itself is installed"
  goto failed
)
rem A note for mosaic's updates: installed by this installer
(echo windows)>"%PREFIX%\etc\mosaic\installer"

if defined MOSAIC_RESULT (echo ok)>"%MOSAIC_RESULT%"
if defined MOSAIC_LOCK del "%MOSAIC_LOCK%" >nul 2>nul
echo.
echo mosaic is installed. Start it from the Start menu or the desktop.
if not defined MOSAIC_UPDATE echo From now on it updates itself (Settings, Updates).
if not "%MOSAIC_NO_OPEN%"=="" exit /b 0
rem From the user's folder: started from this folder, Python would run the copy of mosaic in it
cd /d "%USERPROFILE%"
start "" "%PREFIX%\pythonw.exe" -m mosaic
if defined MOSAIC_UPDATE exit /b 0
echo.
pause
exit /b 0

rem What the environment is made from (environment.yml's SHA-256, from the environment's own
rem Python), to tell whether an update needs conda; read back from a file, as above
:env_hash
set "ENV_HASH="
set "HASH_FILE=%TEMP%\mosaic-env-hash.txt"
"%PREFIX%\python.exe" -I -c "import hashlib; print(hashlib.sha256(open('environment.yml', 'rb').read()).hexdigest())" > "%HASH_FILE%"
if exist "%HASH_FILE%" set /p ENV_HASH=<"%HASH_FILE%"
del "%HASH_FILE%" >nul 2>nul
goto :eof

rem Conda: the one on the PATH or in a usual place, or the base installation the environment is in
:find_conda
set "CONDA="
for %%D in ("%MF_DIR%" "%USERPROFILE%\miniforge3" "%USERPROFILE%\mambaforge" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%LOCALAPPDATA%\miniforge3" "%PROGRAMDATA%\miniforge3" "%PROGRAMDATA%\miniconda3" "%PROGRAMDATA%\anaconda3") do (
  if not defined CONDA if exist "%%~D\Scripts\conda.exe" set "CONDA=%%~D\Scripts\conda.exe"
)
if not defined CONDA (
  for /f "delims=" %%C in ('where conda 2^>nul') do (
    if not defined CONDA if exist "%%~dpC..\Scripts\conda.exe" set "CONDA=%%~dpC..\Scripts\conda.exe"
  )
)
if not defined CONDA if defined MOSAIC_PREFIX (
  if exist "%MOSAIC_PREFIX%\..\..\Scripts\conda.exe" set "CONDA=%MOSAIC_PREFIX%\..\..\Scripts\conda.exe"
)
goto :eof

:failed
echo.
echo The installation stopped: %WHY%
echo You can run this installer again after fixing the problem.
if defined MOSAIC_RESULT (echo failed: !WHY!)>"%MOSAIC_RESULT%"
if defined MOSAIC_LOCK del "%MOSAIC_LOCK%" >nul 2>nul
rem An update that didn't go in: open the version there is, which says what happened
if defined MOSAIC_UPDATE if "%MOSAIC_NO_OPEN%"=="" if defined PREFIX if exist "%PREFIX%\pythonw.exe" (
  cd /d "%USERPROFILE%"
  start "" "!PREFIX!\pythonw.exe" -m mosaic
  exit /b 1
)
if "%MOSAIC_NO_OPEN%"=="" pause
exit /b 1
