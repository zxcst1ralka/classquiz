@echo off
rem Runs project checks and writes the report to check_log.txt (same folder).
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set LOG=check_log.txt
set PY=

echo START > %LOG%

for %%P in ("venv\Scripts\python.exe" "python" "py") do (
  if not defined PY (
    %%~P -c "import django" >nul 2>&1 && set PY=%%~P
  )
)

if not defined PY (
  echo NO PYTHON WITH DJANGO FOUND >> %LOG%
  goto end
)

echo Python command: %PY% >> %LOG%
%PY% --version >> %LOG% 2>&1
%PY% -c "import django; print('Django', django.get_version())" >> %LOG% 2>&1
%PY% -c "import openpyxl; print('openpyxl', openpyxl.__version__)" >> %LOG% 2>&1

echo. >> %LOG%
echo ===== manage.py check ===== >> %LOG%
%PY% manage.py check >> %LOG% 2>&1

echo. >> %LOG%
echo ===== makemigrations ===== >> %LOG%
%PY% manage.py makemigrations --noinput >> %LOG% 2>&1

echo. >> %LOG%
echo ===== tests ===== >> %LOG%
%PY% manage.py test quiz -v 2 >> %LOG% 2>&1

echo. >> %LOG%
echo ===== backup_db ===== >> %LOG%
%PY% manage.py backup_db >> %LOG% 2>&1

:end
echo. >> %LOG%
echo DONE >> %LOG%
