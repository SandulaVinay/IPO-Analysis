from src.notifications.smtp_diagnostics import authenticate_smtp


def test_smtp_auth_probe_normalizes_password_and_sends_no_message(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, context=None):
            calls.append(("starttls", context is not None))

        def login(self, username, password):
            calls.append(("login", username, password))

        def noop(self):
            calls.append(("noop",))
            return 250, b"OK"

        def sendmail(self, *args, **kwargs):
            raise AssertionError("The SMTP authentication probe must never send email.")

    monkeypatch.setattr("src.notifications.smtp_diagnostics.smtplib.SMTP", FakeSMTP)

    result = authenticate_smtp(
        host="smtp.example.test",
        preferred_port=587,
        username="sender@example.test",
        password=" app-pass word\n",
    )

    assert result["success"] is True
    assert result["port"] == 587
    assert result["attempts"] == [{"port": 587, "stage": "authenticated", "error": None}]
    assert ("login", "sender@example.test", "app-password") in calls
    assert ("noop",) in calls


def test_smtp_auth_probe_tries_gmail_ssl_alternate_port(monkeypatch):
    attempts = []

    class DisconnectedSMTP:
        def __init__(self, host, port, timeout=30):
            attempts.append(("starttls", port))
            raise OSError("network blocked")

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout=30, context=None):
            attempts.append(("ssl", port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            pass

        def login(self, username, password):
            assert password == "app-password"

        def noop(self):
            return 250, b"OK"

    monkeypatch.setattr("src.notifications.smtp_diagnostics.smtplib.SMTP", DisconnectedSMTP)
    monkeypatch.setattr("src.notifications.smtp_diagnostics.smtplib.SMTP_SSL", FakeSMTPSSL)

    result = authenticate_smtp(
        host="smtp.gmail.com",
        preferred_port=587,
        username="sender@gmail.com",
        password="app-password",
    )

    assert result["success"] is True
    assert result["port"] == 465
    assert attempts == [("starttls", 587), ("ssl", 465)]
    assert result["attempts"][0]["error"] == "SMTP OSError during connect on port 587: network blocked"
    assert result["attempts"][1] == {"port": 465, "stage": "authenticated", "error": None}


def test_smtp_auth_probe_reports_both_gmail_login_disconnects(monkeypatch):
    import smtplib

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            pass

        def starttls(self, context=None):
            pass

        def login(self, username, password):
            raise smtplib.SMTPServerDisconnected(
                f"connection unexpectedly closed on port {self.port}"
            )

    class FakeSMTPSSL(FakeSMTP):
        def __init__(self, host, port, timeout=30, context=None):
            self.port = port

    monkeypatch.setattr("src.notifications.smtp_diagnostics.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("src.notifications.smtp_diagnostics.smtplib.SMTP_SSL", FakeSMTPSSL)

    result = authenticate_smtp(
        host="smtp.gmail.com",
        preferred_port=587,
        username="sender@gmail.com",
        password="app-password",
    )

    assert result["success"] is False
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["port"] == 587
    assert result["attempts"][0]["stage"] == "login"
    assert "closed on port 587" in result["attempts"][0]["error"]
    assert result["attempts"][1]["port"] == 465
    assert result["attempts"][1]["stage"] == "login"
    assert "closed on port 465" in result["attempts"][1]["error"]


def test_smtp_auth_probe_reports_missing_configuration():
    result = authenticate_smtp(
        host="smtp.gmail.com",
        preferred_port=587,
        username="",
        password="",
    )

    assert result["success"] is False
    assert result["stage"] == "configuration"
    assert result["attempts"] == []


def test_settings_map_uppercase_github_actions_smtp_variables(monkeypatch):
    from src.common.config import Settings

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")

    loaded = Settings(_env_file=None)

    assert loaded.smtp_host == "smtp.example.test"
    assert loaded.smtp_port == 465
    assert loaded.smtp_user == "sender@example.test"
    assert loaded.smtp_password == "app-password"
