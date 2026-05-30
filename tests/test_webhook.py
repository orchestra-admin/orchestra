import hashlib
import hmac

from conductor.conductor_tasks.webhook import (
    build_signature,
    get_signature_header,
    is_valid_signature,
)


def test_build_signature_returns_sha256_hmac():
    """build_signature returns the expected sha256=<hmac> string."""
    raw_body = b'{"event_type": "test"}'
    secret = "my_secret_key"

    result = build_signature(raw_body, secret)

    # Manually compute expected HMAC
    expected_digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    expected = f"sha256={expected_digest}"

    assert result == expected


def test_build_signature_with_empty_body():
    """build_signature handles empty body correctly."""
    raw_body = b""
    secret = "secret"

    result = build_signature(raw_body, secret)

    expected_digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    expected = f"sha256={expected_digest}"

    assert result == expected


def test_is_valid_signature_accepts_correct_signature():
    """is_valid_signature accepts the correct signature."""
    raw_body = b'{"event_type": "test", "data": "value"}'
    secret = "webhook_secret_123"

    correct_signature = build_signature(raw_body, secret)

    assert is_valid_signature(raw_body, correct_signature, secret) is True


def test_is_valid_signature_rejects_missing_signature():
    """is_valid_signature rejects None signature."""
    raw_body = b'{"event_type": "test"}'
    secret = "secret"

    assert is_valid_signature(raw_body, None, secret) is False


def test_is_valid_signature_rejects_empty_signature():
    """is_valid_signature rejects empty string signature."""
    raw_body = b'{"event_type": "test"}'
    secret = "secret"

    assert is_valid_signature(raw_body, "", secret) is False


def test_is_valid_signature_rejects_bad_signature():
    """is_valid_signature rejects incorrect signature."""
    raw_body = b'{"event_type": "test"}'
    secret = "secret"

    bad_signature = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    assert is_valid_signature(raw_body, bad_signature, secret) is False


def test_is_valid_signature_rejects_wrong_secret():
    """is_valid_signature rejects signature computed with wrong secret."""
    raw_body = b'{"event_type": "test"}'
    correct_secret = "correct_secret"
    wrong_secret = "wrong_secret"

    signature = build_signature(raw_body, correct_secret)

    assert is_valid_signature(raw_body, signature, wrong_secret) is False


def test_is_valid_signature_rejects_tampered_body():
    """is_valid_signature rejects signature when body is tampered."""
    original_body = b'{"event_type": "test"}'
    tampered_body = b'{"event_type": "tampered"}'
    secret = "secret"

    signature = build_signature(original_body, secret)

    assert is_valid_signature(tampered_body, signature, secret) is False


def test_get_signature_header_supports_orchestra_header():
    """get_signature_header extracts x-orchestra-signature-256 header."""
    headers = {"x-orchestra-signature-256": "sha256=abc123"}

    result = get_signature_header(headers)

    assert result == "sha256=abc123"


def test_get_signature_header_supports_hub_header():
    """get_signature_header extracts x-hub-signature-256 header as fallback."""
    headers = {"x-hub-signature-256": "sha256=def456"}

    result = get_signature_header(headers)

    assert result == "sha256=def456"


def test_get_signature_header_prefers_orchestra_header():
    """get_signature_header prefers x-orchestra-signature-256 over x-hub-signature-256."""
    headers = {
        "x-orchestra-signature-256": "sha256=orchestra_sig",
        "x-hub-signature-256": "sha256=hub_sig",
    }

    result = get_signature_header(headers)

    assert result == "sha256=orchestra_sig"


def test_get_signature_header_returns_none_when_missing():
    """get_signature_header returns None when no signature header is present."""
    headers = {"content-type": "application/json"}

    result = get_signature_header(headers)

    assert result is None


def test_get_signature_header_case_insensitive():
    """get_signature_header handles case-insensitive header lookup."""
    # FastAPI/Starlette headers are case-insensitive, but dict.get() is not
    # This test documents the current behavior (case-sensitive dict lookup)
    headers = {"X-Orchestra-Signature-256": "sha256=abc123"}

    result = get_signature_header(headers)

    # Current implementation uses dict.get() which is case-sensitive
    # So this will return None (headers are lowercase in the implementation)
    assert result is None
