"""
Unit tests for Razorpay payment and webhook cryptographic signature verification.
Never allow forged signatures to authorize subscriptions or update balances.
"""
import hmac
import hashlib
import pytest
from app.api.v1.endpoints.webhooks import _verify_razorpay_signature
from app.services.payment.razorpay_service import verify_payment_signature
from app.core.config import settings


def test_webhook_signature_verification():
    # Setup test secret
    test_secret = "test_webhook_secret_key_12345"
    settings.RAZORPAY_WEBHOOK_SECRET = test_secret

    payload = b'{"event":"subscription.activated","id":"evt_123"}'
    valid_sig = hmac.new(
        test_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Valid signature must pass
    assert _verify_razorpay_signature(payload, valid_sig) is True

    # Tampered body must fail
    tampered_payload = b'{"event":"subscription.activated","id":"evt_999"}'
    assert _verify_razorpay_signature(tampered_payload, valid_sig) is False

    # Forged signature must fail
    assert _verify_razorpay_signature(payload, "forged_hex_signature") is False


def test_payment_mandate_signature_verification():
    test_secret = "test_rzp_secret_abc"
    settings.RAZORPAY_KEY_SECRET = test_secret

    sub_id = "sub_M12345678"
    pay_id = "pay_N87654321"

    msg = f"{pay_id}|{sub_id}"
    valid_sig = hmac.new(
        test_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert verify_payment_signature(sub_id, pay_id, valid_sig) is True
    assert verify_payment_signature(sub_id, pay_id, "invalid_sig") is False
    assert verify_payment_signature("sub_other", pay_id, valid_sig) is False

