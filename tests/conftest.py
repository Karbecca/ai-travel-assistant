import os


def pytest_configure() -> None:
    """Force test isolation from developer `.env` (PostgreSQL, secrets).

    Runs before test collection so imports see consistent settings.
    """

    os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"
    os.environ.setdefault(
        "JWT_SECRET_KEY",
        "test-secret-key-for-jwt-signing-at-least-32-characters",
    )
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-api-key")
