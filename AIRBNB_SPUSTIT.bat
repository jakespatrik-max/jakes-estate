@echo off
set PYTHON=C:\Users\jakes\AppData\Local\Programs\Python\Python312\python.exe
"%PYTHON%" -m pip install requests python-dateutil playwright --quiet
"%PYTHON%" "%~dp0airbnb_local.py"
pause
