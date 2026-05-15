@echo off
:: ============================================================
:: start_server.bat
:: Run this instead of "python manage.py runserver"
:: It will auto-fix migrations before starting the server.
:: ============================================================

echo.
echo [1/2] Running migration fix...
python fix_migrations.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Migration fix reported errors (see above).
    echo Proceeding to runserver anyway...
)

echo.
echo [2/2] Starting Django server...
python manage.py runserver 0.0.0.0:8000
