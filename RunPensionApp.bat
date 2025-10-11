@echo off
cd "%USERPROFILE%\Dev\GitHub\PensionTaxModel"
call .venv\Scripts\activate.bat
streamlit run app\app.py
pause
