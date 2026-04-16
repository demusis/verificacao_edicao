@echo off
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if exist "%ISCC_PATH%" goto Found
goto NotFound

:Found
echo [INFO] Inno Setup encontrado em: "%ISCC_PATH%"
echo [INFO] Detectando versao...
python tools/get_version.py > temp_version.txt
set /p APP_VERSION=<temp_version.txt
del temp_version.txt
echo [INFO] Versao detectada: %APP_VERSION%

echo [INFO] Criando instalador...
"%ISCC_PATH%" /DMyAppVersion="%APP_VERSION%" "setup_script.iss"
if errorlevel 1 (
     echo [ERRO] Falha ao executar o Inno Setup.
) else (
     echo [SUCESSO] Instalador criado com sucesso na pasta 'dist-setup'!
)
goto End

:NotFound
echo [ERRO] Inno Setup nao encontrado.
echo.
echo Para gerar o instalador (setup.exe), voce precisa instalar o Inno Setup.
echo.
echo Opcao 1 - Recomendada - Instalar via terminal (winget):
echo    winget install --id JRSoftware.InnoSetup -e --source winget
echo.
echo Opcao 2: Baixar manual em: https://jrsoftware.org/isdl.php
echo.
goto End

:End
pause
