"""Application fixtures with explicit fake engine injection for transport tests."""

import pytest

from sentinel import create_app
from sentinel.scanner.models import Confidence, Finding, ScanResult, ScanState, Severity
from sentinel.scanner.scoring import apply_score


def fake_scan(root, scan_id, filename, config=None):
    return apply_score(
        ScanResult(
            scan_id,
            ScanState.COMPLETED,
            filename,
            [
                Finding(
                    "SS-006",
                    "Origin check",
                    Severity.HIGH,
                    Confidence.MEDIUM,
                    "Use of tx.origin",
                    "Use msg.sender",
                    "A.sol",
                    1,
                    1,
                    '<script>alert("x")</script>',
                )
            ],
            {
                "compilers": {"A.sol": "0.8.30"},
                "slither_version": "test",
                "duration_seconds": 0.1,
                "sloc": 1,
                "contract_count": 1,
                "function_count": 1,
            },
        )
    )


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATA_DIR": tmp_path,
            "SCAN_FUNCTION": fake_scan,
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
        }
    )
    yield application
    application.extensions["sentinel_jobs"].shutdown()


@pytest.fixture
def client(app):
    return app.test_client()
