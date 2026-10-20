@echo off
cd /d "%~dp0"
if exist "deliverables\desktop-input-fix-v0.1.5\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-input-fix-v0.1.5\FormatFactory\FormatFactory.exe"
) else if exist "deliverables\desktop-office-copy-v0.1.4\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-office-copy-v0.1.4\FormatFactory\FormatFactory.exe"
) else if exist "deliverables\desktop-formula-fix-v0.1.3\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-formula-fix-v0.1.3\FormatFactory\FormatFactory.exe"
) else if exist "deliverables\desktop-formula-fix-v0.1.2\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-formula-fix-v0.1.2\FormatFactory\FormatFactory.exe"
) else if exist "deliverables\desktop-formula-fix-v0.1.1\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-formula-fix-v0.1.1\FormatFactory\FormatFactory.exe"
) else if exist "dist\FormatFactory\FormatFactory.exe" (
    start "" "dist\FormatFactory\FormatFactory.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -X utf8 main.py
) else (
    echo Runtime not found. Please run the setup script first.
    pause
)
