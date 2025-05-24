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


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up the test environment"""
    print("Setting up test environment...")
    
    os.environ("PYTHONDONTWRITEBYTECODE") = 1

    

    # Delete directory
    dir_to_delete = "path/to/directory"
    if os.path.exists(dir_to_delete):
        run_command(f"rmdir /s /q {dir_to_delete}")  # For Windows
        # or for cross-platform: shutil.rmtree(dir_to_delete)
    
    # Launch Docker containers
    run_command("docker-compose up -d")
    
    # Wait for services to be ready
    import time
    time.sleep(5)  # Simple wait, you could implement a more robust check
    
    yield
    
    # Cleanup
    run_command("docker-compose down")