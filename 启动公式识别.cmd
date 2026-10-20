@echo off
cd /d "%~dp0"
if exist "deliverables\desktop-input-fix-v0.1.5\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-input-fix-v0.1.5\FormatFactory\FormatFactory.exe" --formula-workspace
) else if exist "deliverables\desktop-office-copy-v0.1.4\FormatFactory\FormatFactory.exe" (
    start "" "deliverables\desktop-office-copy-v0.1.4\FormatFactory\FormatFactory.exe" --formula-workspace
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -X utf8 main.py --formula-workspace
) else (
    echo Formula workspace runtime not found.
    pause
    exit /b 1
)
