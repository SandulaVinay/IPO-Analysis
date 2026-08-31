import os
import pytest
from src.common.config import Settings


def test_settings_default_values():
    s = Settings()
    assert s.enable_whatsapp is False
    assert s.enable_email is False
    assert s.enable_sms is False
    assert s.enable_automated_scheduler is True
    assert s.port == 8000
    assert s.whatsapp_provider == "console"
    assert s.email_provider == "console"


def test_settings_empty_and_masked_env_vars():
    """Test that empty strings and masked secret strings (like in GitHub Actions) do not crash Settings."""
    test_env = {
        "ENABLE_WHATSAPP": "",
        "ENABLE_EMAIL": "***\n",
        "ENABLE_SMS": "   ",
        "ENABLE_AUTOMATED_SCHEDULER": "true\n",
        "PORT": "",
        "SMTP_PORT": "",
        "WHATSAPP_PROVIDER": "",
        "EMAIL_PROVIDER": "",
        "SMS_PROVIDER": "",
        "WEIGHT_VALUATION": "",
    }
    
    # Save original env
    orig = {k: os.environ.get(k) for k in test_env}
    try:
        for k, v in test_env.items():
            os.environ[k] = v
            
        s = Settings()
        assert s.enable_whatsapp is False
        assert s.enable_email is False
        assert s.enable_sms is False
        assert s.enable_automated_scheduler is True
        assert s.port == 8000
        assert s.smtp_port == 587
        assert s.whatsapp_provider == "console"
        assert s.email_provider == "console"
        assert s.sms_provider == "console"
        assert s.weight_valuation == 0.20
    finally:
        for k, orig_v in orig.items():
            if orig_v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig_v


def test_settings_truthy_values():
    for val in ("true", "TRUE", "1", "yes", "Y", "enabled", "on", "  true \n"):
        assert Settings.parse_bool(val) is True


def test_settings_falsy_values():
    for val in ("false", "FALSE", "0", "no", "disabled", "", "random_string", "***\n"):
        assert Settings.parse_bool(val) is False
