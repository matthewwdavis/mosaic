@echo off
rem Installs FigAssemble on Windows. Double-click this file (if Windows says it protected your
rem PC, click "More info" and then "Run anyway").
rem
rem It installs conda (Miniforge, in your user folder) if you don't have conda yet, makes a conda
rem environment called "figassemble" with everything FigAssemble needs, and adds FigAssemble to
rem the Start menu and the desktop. Running it again updates an earlier installation. It needs
rem an internet connection and about 2 GB of disk space; the first run takes 5-15 minutes.
rem
rem FigAssemble's own updates run this file from the new version (figassemble\updates.py), with
rem FIGASSEMBLE_UPDATE=1 (no questions), FIGASSEMBLE_PREFIX (the environment to update; conda is
rem needed only if environment.yml changed), FIGASSEMBLE_WAIT_PID (wait for FigAssemble to
rem close), FIGASSEMBLE_RESULT (a file to write "ok" or "failed: why" to) and FIGASSEMBLE_LOCK (a
rem file to delete at the end).
rem
rem For testing: FIGASSEMBLE_ENV (environment name), FIGASSEMBLE_NO_OPEN=1 (don't start
rem FigAssemble or wait for a key at the end).
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ENV_NAME=%FIGASSEMBLE_ENV%"
if "%ENV_NAME%"=="" set "ENV_NAME=figassemble"
if not exist environment.yml (
  set "WHY=run this file from inside the FigAssemble folder you downloaded"
  goto failed
)

rem 0. An update from FigAssemble itself: it closes first
if defined FIGASSEMBLE_WAIT_PID (
  echo.
  echo ==^> Waiting for FigAssemble to close
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Wait-Process -Id %FIGASSEMBLE_WAIT_PID% -Timeout 300 -ErrorAction SilentlyContinue; if (Get-Process -Id %FIGASSEMBLE_WAIT_PID% -ErrorAction SilentlyContinue) { exit 1 }"
  if errorlevel 1 (
    set "WHY=FigAssemble didn't close"
    goto failed
  )
)

set "ENV_HASH="
if defined FIGASSEMBLE_PREFIX goto update_env

rem 1. Conda: use the one you have, or install Miniforge
call :find_conda
if not defined CONDA (
  echo.
  echo ==^> Installing conda ^(Miniforge^) into !USERPROFILE!\miniforge3
  if exist "%USERPROFILE%\miniforge3" (
    set "WHY=%USERPROFILE%\miniforge3 exists but has no conda in it; move it aside and try again"
    goto failed
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe' -OutFile (Join-Path $env:TEMP 'Miniforge3-Windows-x86_64.exe')"
  if errorlevel 1 (
    set "WHY=Miniforge couldn't be downloaded; check the internet connection"
    goto failed
  )
  start "" /wait "%TEMP%\Miniforge3-Windows-x86_64.exe" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=!USERPROFILE!\miniforge3
  del "%TEMP%\Miniforge3-Windows-x86_64.exe" >nul 2>nul
  set "CONDA=%USERPROFILE%\miniforge3\Scripts\conda.exe"
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
  echo ==^> Making the "%ENV_NAME%" environment ^(this downloads the tools FigAssemble uses^)
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
set "PREFIX_FILE=%TEMP%\figassemble-prefix.txt"
"%CONDA%" run -n "%ENV_NAME%" python -c "import sys; print(sys.prefix)" > "%PREFIX_FILE%"
if exist "%PREFIX_FILE%" set /p PREFIX=<"%PREFIX_FILE%"
del "%PREFIX_FILE%" >nul 2>nul
if not defined PREFIX (
  set "WHY=the new environment's Python couldn't be found"
  goto failed
)
goto env_done

rem 2. An update: the environment FigAssemble runs in, brought up to date only if what it needs changed
:update_env
set "PREFIX=%FIGASSEMBLE_PREFIX%"
if not exist "%PREFIX%\python.exe" (
  set "WHY=FigAssemble's environment isn't in %PREFIX% any more"
  goto failed
)
call :env_hash
set "OLD_HASH="
if exist "%PREFIX%\etc\figassemble\environment.sha256" set /p OLD_HASH=<"%PREFIX%\etc\figassemble\environment.sha256"
if defined ENV_HASH if /i "%OLD_HASH%"=="%ENV_HASH%" (
  echo.
  echo ==^> The tools FigAssemble uses are up to date
  goto env_done
)
call :find_conda
if not defined CONDA (
  set "WHY=this update needs conda, and conda wasn't found"
  goto failed
)
echo.
echo ==^> Updating the tools FigAssemble uses ^(this can take a few minutes^)
"%CONDA%" env update -p "%PREFIX%" -f environment.yml --prune
if errorlevel 1 (
  set "WHY=the tools FigAssemble uses couldn't be updated (the log says why)"
  goto failed
)

:env_done
if not exist "%PREFIX%\python.exe" (
  set "WHY=FigAssemble's environment isn't in %PREFIX%"
  goto failed
)
if not exist "%PREFIX%\etc\figassemble" mkdir "%PREFIX%\etc\figassemble"
if not defined ENV_HASH call :env_hash
if defined ENV_HASH (echo !ENV_HASH!)>"%PREFIX%\etc\figassemble\environment.sha256"

rem 3. FigAssemble itself, copied into the environment (this folder can be deleted afterwards)
echo.
echo ==^> Installing FigAssemble
"%PREFIX%\python.exe" -m pip install --upgrade --no-warn-script-location .
if errorlevel 1 (
  set "WHY=FigAssemble couldn't be installed (the messages above say why)"
  goto failed
)

rem 4. Shortcuts in the Start menu and on the desktop (an update keeps a desktop shortcut only if there is one)
echo.
echo ==^> Adding FigAssemble to the Start menu and the desktop
set "SHORTCUT_ARGS="
if defined FIGASSEMBLE_UPDATE set "SHORTCUT_ARGS=--update"
"%PREFIX%\python.exe" packaging\windows\make_shortcuts.py %SHORTCUT_ARGS%
if errorlevel 1 (
  set "WHY=the shortcuts couldn't be made; FigAssemble itself is installed"
  goto failed
)
rem A note for FigAssemble's updates: installed by this installer
(echo windows)>"%PREFIX%\etc\figassemble\installer"

if defined FIGASSEMBLE_RESULT (echo ok)>"%FIGASSEMBLE_RESULT%"
if defined FIGASSEMBLE_LOCK del "%FIGASSEMBLE_LOCK%" >nul 2>nul
echo.
echo FigAssemble is installed. Start it from the Start menu or the desktop.
if not defined FIGASSEMBLE_UPDATE echo From now on it updates itself (Settings, Updates).
if not "%FIGASSEMBLE_NO_OPEN%"=="" exit /b 0
rem From the user's folder: started from this folder, Python would run the copy of FigAssemble in it
cd /d "%USERPROFILE%"
start "" "%PREFIX%\pythonw.exe" -m figassemble
if defined FIGASSEMBLE_UPDATE exit /b 0
echo.
pause
exit /b 0

rem What the environment is made from (environment.yml's SHA-256, from the environment's own
rem Python), to tell whether an update needs conda; read back from a file, as above
:env_hash
set "ENV_HASH="
set "HASH_FILE=%TEMP%\figassemble-env-hash.txt"
"%PREFIX%\python.exe" -I -c "import hashlib; print(hashlib.sha256(open('environment.yml', 'rb').read()).hexdigest())" > "%HASH_FILE%"
if exist "%HASH_FILE%" set /p ENV_HASH=<"%HASH_FILE%"
del "%HASH_FILE%" >nul 2>nul
goto :eof

rem Conda: the one on the PATH or in a usual place, or the base installation the environment is in
:find_conda
set "CONDA="
for %%D in ("%USERPROFILE%\miniforge3" "%USERPROFILE%\mambaforge" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%LOCALAPPDATA%\miniforge3" "%PROGRAMDATA%\miniforge3" "%PROGRAMDATA%\miniconda3" "%PROGRAMDATA%\anaconda3") do (
  if not defined CONDA if exist "%%~D\Scripts\conda.exe" set "CONDA=%%~D\Scripts\conda.exe"
)
if not defined CONDA (
  for /f "delims=" %%C in ('where conda 2^>nul') do (
    if not defined CONDA if exist "%%~dpC..\Scripts\conda.exe" set "CONDA=%%~dpC..\Scripts\conda.exe"
  )
)
if not defined CONDA if defined FIGASSEMBLE_PREFIX (
  if exist "%FIGASSEMBLE_PREFIX%\..\..\Scripts\conda.exe" set "CONDA=%FIGASSEMBLE_PREFIX%\..\..\Scripts\conda.exe"
)
goto :eof

:failed
echo.
echo The installation stopped: %WHY%
echo You can run this installer again after fixing the problem.
if defined FIGASSEMBLE_RESULT (echo failed: !WHY!)>"%FIGASSEMBLE_RESULT%"
if defined FIGASSEMBLE_LOCK del "%FIGASSEMBLE_LOCK%" >nul 2>nul
rem An update that didn't go in: open the version there is, which says what happened
if defined FIGASSEMBLE_UPDATE if "%FIGASSEMBLE_NO_OPEN%"=="" if defined PREFIX if exist "%PREFIX%\pythonw.exe" (
  cd /d "%USERPROFILE%"
  start "" "!PREFIX!\pythonw.exe" -m figassemble
  exit /b 1
)
if "%FIGASSEMBLE_NO_OPEN%"=="" pause
exit /b 1
