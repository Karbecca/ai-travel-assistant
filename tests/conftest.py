import os


def pytest_configure() -> None:
    os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"
    os.environ.setdefault(
        "JWT_SECRET_KEY",
        "test-secret-key-for-jwt-signing-at-least-32-characters",
    )
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-api-key")
