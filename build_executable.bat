@echo off
echo Check for PyInstaller...
pip install pyinstaller

echo Cleaning up previous builds...
rmdir /s /q build
rmdir /s /q dist
del *.spec

echo Building Executable...
pyinstaller --noconfirm --onefile --windowed --name "ForensicAnalyzer" --clean --add-data "core;core" --add-data "modules;modules" --add-data "adapters;adapters" app/gui.py

echo Done! Executable should be in 'dist' folder.
pause
