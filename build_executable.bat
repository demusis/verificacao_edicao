@echo off
echo ========================================================
echo CRIAÇÃO DE EXECUTÁVEIS - FORENSIC ANALYZER
echo ========================================================

:: Limpar pastas antigas se existirem
if exist build rd /s /q build
if exist dist rd /s /q dist

echo.
echo [1/2] Criando Executável da GUI (Interface Gráfica)...
pyinstaller --noconfirm --onedir --windowed ^
    --icon "icon.ico" ^
    --name "ForensicAnalyzer_GUI" ^
    --add-data "core;core" ^
    --add-data "modules;modules" ^
    --add-data "adapters;adapters" ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "cv2" ^
    --hidden-import "numpy" ^
    --hidden-import "scipy" ^
    --hidden-import "skimage" ^
    --hidden-import "pywt" ^
    "app/gui.py"

echo.
echo [2/2] Criando Executável da CLI (Linha de Comando)...
pyinstaller --noconfirm --onedir --console ^
    --icon "icon.ico" ^
    --name "ForensicAnalyzer_CLI" ^
    --add-data "core;core" ^
    --add-data "modules;modules" ^
    --add-data "adapters;adapters" ^
    --hidden-import "typer" ^
    --hidden-import "cv2" ^
    --hidden-import "numpy" ^
    "app/cli.py"

echo.
echo ========================================================
echo PROCESSO CONCLUÍDO!
echo Executáveis disponíveis na pasta 'dist/'
echo ========================================================
pause
