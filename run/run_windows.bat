@echo off
REM Double-click this file on Windows to run the analysis.
set ROOT=%~dp0..
"%ROOT%\.venv\Scripts\python.exe" "%ROOT%\program\main.py"
echo.
echo Done. Open  data\output\Energy_Analysis_Output.xlsx
pause
