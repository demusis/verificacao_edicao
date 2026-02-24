@echo off
echo ========================================================
echo CRIAÇÃO DE EXECUTÁVEIS - FORENSIC ANALYZER
echo ========================================================

:: Limpar pastas antigas se existirem
if exist build rd /s /q build 2>nul
if exist dist rd /s /q dist 2>nul

:: Limpar arquivos SPEC antigos
del *.spec 2>nul

:: Limpar caches (agressivo)
for /d /r "app" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
for /d /r "modules" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
for /d /r "core" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"


:: Se dist ainda existir (travado), avisar e tentar prosseguir
if exist dist (
    echo AVISO: A pasta 'dist' esta em uso ou travada. O PyInstaller tentara sobrescrever.
)

echo.
:: Ativar ambiente virtual
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo AVISO: Ambiente virtual .venv nao encontrado. Usando Python do sistema.
)

echo.
:: Atualizar Versão e Data
echo Atualizando versao...
python tools/update_version.py > temp_version.txt
set /p APP_VERSION=<temp_version.txt
del temp_version.txt
echo Versao detectada: %APP_VERSION%

echo.
:: Obter caminho dos haarcascades do OpenCV (os arquivos XML estão diretamente em cv2/data/)
for /f "delims=" %%i in ('python -c "import cv2; print(cv2.data.haarcascades)"') do set OPENCV_HAARCASCADES_PATH=%%i
echo Caminho dos haarcascades do OpenCV: %OPENCV_HAARCASCADES_PATH%

echo [1/2] Criando Executável da GUI (Interface Gráfica)...
python -m PyInstaller --noconfirm --onedir --windowed --distpath "dist" ^
    --icon "icon.ico" ^
    --name "VerificacaoEdicao" ^
    --add-data "core;core" ^
    --add-data "modules;modules" ^
    --add-data "adapters;adapters" ^
    --add-data "%OPENCV_HAARCASCADES_PATH%;cv2\data" ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "cv2" ^
    --hidden-import "numpy" ^
    --hidden-import "scipy" ^
    --hidden-import "scipy.signal" ^
    --hidden-import "scipy.fft" ^
    --hidden-import "skimage" ^
    --hidden-import "skimage.feature" ^
    --hidden-import "skimage.feature._local_binary_pattern" ^
    --hidden-import "pywt" ^
    --hidden-import "librosa" ^
    --hidden-import "librosa.feature" ^
    --hidden-import "librosa.core" ^
    --hidden-import "soundfile" ^
    --hidden-import "audioread" ^
    --hidden-import "dataclasses" ^
    "app/gui.py"

echo.
echo [2/2] Criando Executável da CLI (Linha de Comando)...
python -m PyInstaller --noconfirm --onedir --console --distpath "dist" ^
    --icon "icon.ico" ^
    --name "VerificacaoEdicao_CLI" ^
    --add-data "core;core" ^
    --add-data "modules;modules" ^
    --add-data "adapters;adapters" ^
    --add-data "%OPENCV_HAARCASCADES_PATH%;cv2\data" ^
    --hidden-import "typer" ^
    --hidden-import "cv2" ^
    --hidden-import "numpy" ^
    --hidden-import "scipy" ^
    --hidden-import "scipy.signal" ^
    --hidden-import "scipy.fft" ^
    --hidden-import "skimage" ^
    --hidden-import "skimage.feature" ^
    --hidden-import "skimage.feature._local_binary_pattern" ^
    --hidden-import "pywt" ^
    --hidden-import "librosa" ^
    --hidden-import "librosa.feature" ^
    --hidden-import "librosa.core" ^
    --hidden-import "soundfile" ^
    --hidden-import "audioread" ^
    --hidden-import "dataclasses" ^
    "app/cli.py"

echo.
echo [3/3] Tentando criar Instalador (Inno Setup)...
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "%ISCC_PATH%" (
    echo Encontrado Inno Setup. Compilando...
    "%ISCC_PATH%" /DMyAppVersion="%APP_VERSION%" "setup_script.iss"
    echo.
    echo Instalador criado em dist-setup/
) else (
    echo Inno Setup nao encontrado no caminho padrao.
    echo Pule a etapa de criacao do instalador ou instale o Inno Setup.
    echo Baixe em: https://jrsoftware.org/isdl.php
)

echo.
echo ========================================================
if exist "dist\VerificacaoEdicao\VerificacaoEdicao.exe" (
    echo PROCESSO CONCLUIDO COM SUCESSO!
    echo Executaveis na pasta 'dist/'
    if exist "dist-setup\VerificacaoEdicao_Setup.exe" (
        echo Instalador criado em dist-setup/
    )
) else (
    echo ERRO: O executavel nao foi gerado. Verifique as mensagens acima.
)
echo ========================================================
pause
