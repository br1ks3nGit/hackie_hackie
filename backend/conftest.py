import os

# Must be set before any test module imports the app: get_settings() is
# lru_cached, and conftest is imported by pytest before test modules.
os.environ.setdefault("INSURER_API_KEY", "test-insurer-key")
os.environ.setdefault("DRIVER_API_KEY_SALT", "test-salt")
