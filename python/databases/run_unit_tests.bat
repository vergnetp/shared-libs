@echo off
set PYTHONDONTWRITEBYTECODE=1

docker compose -f "%~dp0tests\docker-compose.yml" down -v

:: Start DB containers using docker-compose in tests/
docker compose -f "%~dp0tests\docker-compose.yml" up -d

:: Run pytest on the tests folder relative to script
pytest -v "%~dp0tests\test_postgres.py"

:: Clean up pytest cache
rmdir /s /q "%~dp0tests\.pytest_cache"

pause
exit /b 0
