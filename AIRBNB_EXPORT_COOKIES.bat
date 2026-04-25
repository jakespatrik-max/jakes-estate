@echo off
set PYTHON=C:\Users\jakes\AppData\Local\Programs\Python\Python312\python.exe
echo Otevre se samostatne Chrome okno - prihlaste se na Airbnb
echo.
"%PYTHON%" "%~dp0airbnb_export_cookies.py"
pause
