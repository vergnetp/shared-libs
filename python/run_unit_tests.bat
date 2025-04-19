set PYTHONDONTWRITEBYTECODE=1
pytest -v
rmdir /s /q .pytest_cache
pause
exit /b 0