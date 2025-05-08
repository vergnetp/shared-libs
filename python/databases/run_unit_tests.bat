@echo off
set PYTHONDONTWRITEBYTECODE=1

:: Clean up pytest cache
rmdir /s /q "%~dp0tests\.pytest_cache"

::docker compose -f "%~dp0tests\docker-compose.yml" down -v

:: Start DB containers using docker-compose in tests/
docker compose -f "%~dp0tests\docker-compose.yml" up -d

:: Run pytest on the tests folder relative to script
pytest -s -v "%~dp0tests\test.py::test_postgres_save_and_get_entity"

:: Clean up pytest cache
rmdir /s /q "%~dp0tests\.pytest_cache"

pause
exit /b 0
