set PYTHONDONTWRITEBYTECODE=1
pytest -v %~dp0log\tests\
rmdir /s /q .pytest_cache
pause
exit /b 0