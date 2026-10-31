@echo off
rem Installs FigAssemble on Windows. Double-click this file (if Windows says it protected your
rem PC, click "More info" and then "Run anyway").
rem
rem It installs conda (Miniforge, in your user folder) if you don't have conda yet, makes a conda
rem environment called "figassemble" with everything FigAssemble needs, and adds FigAssemble to
rem the Start menu and the desktop. Running it again updates an earlier installation. It needs
rem an internet connection and about 2 GB of disk space; the first run takes 5-15 minutes.
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

rem 1. Conda: use the one you have, or install Miniforge
set "CONDA="
for %%D in ("%USERPROFILE%\miniforge3" "%USERPROFILE%\mambaforge" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%LOCALAPPDATA%\miniforge3" "%PROGRAMDATA%\miniforge3" "%PROGRAMDATA%\miniconda3" "%PROGRAMDATA%\anaconda3") do (
  if not defined CONDA if exist "%%~D\Scripts\conda.exe" set "CONDA=%%~D\Scripts\conda.exe"
)
if not defined CONDA (
  for /f "delims=" %%C in ('where conda 2^>nul') do (
    if not defined CONDA if exist "%%~dpC..\Scripts\conda.exe" set "CONDA=%%~dpC..\Scripts\conda.exe"
  )
)
if not defined CONDA (
  echo.
  echo ==^> Installing conda ^(Miniforge^) into %USERPROFILE%\miniforge3
  if exist "%USERPROFILE%\miniforge3" (
    set "WHY=%USERPROFILE%\miniforge3 exists but has no conda in it; move it aside and try again"
    goto failed
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe' -OutFile (Join-Path $env:TEMP 'Miniforge3-Windows-x86_64.exe')"
  if errorlevel 1 (
    set "WHY=Miniforge couldn't be downloaded; check the internet connection"
    goto failed
  )
  start "" /wait "%TEMP%\Miniforge3-Windows-x86_64.exe" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=%USERPROFILE%\miniforge3
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
set "PREFIX="
rem (the extra quotes survive cmd stripping the outer pair from a quoted command)
for /f "delims=" %%P in ('""%CONDA%" run -n "%ENV_NAME%" python -c "import sys; print(sys.prefix)""') do set "PREFIX=%%P"
if not defined PREFIX (
  set "WHY=the new environment's Python couldn't be found"
  goto failed
)

rem 3. FigAssemble itself, copied into the environment (this folder can be deleted afterwards)
echo.
echo ==^> Installing FigAssemble
"%PREFIX%\python.exe" -m pip install --upgrade --no-warn-script-location .
if errorlevel 1 (
  set "WHY=FigAssemble couldn't be installed (the messages above say why)"
  goto failed
)

rem 4. Shortcuts in the Start menu and on the desktop
echo.
echo ==^> Adding FigAssemble to the Start menu and the desktop
"%PREFIX%\python.exe" packaging\windows\make_shortcuts.py
if errorlevel 1 (
  set "WHY=the shortcuts couldn't be made; FigAssemble itself is installed"
  goto failed
)

echo.
echo FigAssemble is installed. Start it from the Start menu or the desktop.
echo To update it later, download the newest version and run this installer again.
if not "%FIGASSEMBLE_NO_OPEN%"=="" exit /b 0
start "" "%PREFIX%\pythonw.exe" -m figassemble
echo.
pause
exit /b 0

:failed
echo.
echo The installation stopped: %WHY%
echo You can run this installer again after fixing the problem.
if "%FIGASSEMBLE_NO_OPEN%"=="" pause
exit /b 1
