@echo off
REM Lanzador de la app Tipo de Cambio SUNAT (Windows)
REM Sin argumentos: abre la GUI
REM Con argumentos: ejecuta en modo CLI
REM   Ejemplos:
REM     run.bat
REM     run.bat --today
REM     run.bat --range 2024-01-01:2024-12-31 --xlsx tc_2024.xlsx
REM     run.bat --cache-info
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo No se encontro Python instalado. Instala Python 3.9+ desde https://www.python.org/
        pause
        exit /b 1
    )
)

if not exist "venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    %PY% -m venv venv
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

REM Reinstala dependencias si requirements.txt cambio desde la ultima
REM instalacion. Tras instalar se guarda una copia de requirements.txt
REM dentro del venv como sello; fc /b compara contenido (falla tambien
REM si el sello no existe, p. ej. venv recien creado).
fc /b requirements.txt "venv\.installed-requirements.txt" >nul 2>nul
if errorlevel 1 (
    echo Instalando dependencias...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Error al instalar dependencias.
        pause
        exit /b 1
    )
    copy /y requirements.txt "venv\.installed-requirements.txt" >nul
)

%PY% app.py %*
if errorlevel 1 pause
