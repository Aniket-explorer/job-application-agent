import pytest
from pymongo.errors import ServerSelectionTimeoutError

from app.core.errors import DependencyUnavailableError, error_body, raise_for_database
from app.core.logging import redact


def test_database_errors_do_not_expose_the_driver_message():
    with pytest.raises(DependencyUnavailableError) as caught:
        raise_for_database(ServerSelectionTimeoutError("mongodb://user:secret-password@db.internal:27017"))
    assert "secret-password" not in caught.value.message
    assert caught.value.code == "dependency_unavailable"
    assert error_body(caught.value.code, caught.value.message, "cid-1") == {
        "code": "dependency_unavailable",
        "message": "Database is unavailable",
        "correlation_id": "cid-1",
        "details": {},
    }


def test_log_redaction_hides_secret_fields_only():
    cleaned = redact({"gmail_client_secret": "real-value", "source": "gmail", "nested": {"authorization": "Bearer abc"}})
    assert cleaned == {"gmail_client_secret": "***", "source": "gmail", "nested": {"authorization": "***"}}
