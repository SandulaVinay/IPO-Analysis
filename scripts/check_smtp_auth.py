"""Run a no-email SMTP authentication diagnostic from GitHub Actions."""

import sys
from pathlib import Path

# When Python executes "python scripts/check_smtp_auth.py", sys.path[0]
# is the scripts directory, not the repository root. Add the project root
# before importing the src package so direct invocation works in Actions
# and from a local checkout.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import settings
from src.notifications.smtp_diagnostics import authenticate_smtp


def main() -> int:
    print(f"SMTP_HOST={settings.smtp_host}")
    print(f"SMTP_PORT={settings.smtp_port}")
    print(f"SMTP_USER_CONFIGURED={bool(settings.smtp_user.strip())}")
    normalized_password = "".join((settings.smtp_password or "").split())
    print(f"SMTP_PASSWORD_CONFIGURED={bool(normalized_password)}")
    print(f"SMTP_PASSWORD_LENGTH_AFTER_NORMALIZATION={len(normalized_password)}")

    if settings.smtp_host.strip().lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
        if normalized_password and len(normalized_password) != 16:
            print("WARNING: a Gmail App Password is normally 16 characters after whitespace is removed.")

    result = authenticate_smtp(
        host=settings.smtp_host,
        preferred_port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
    )

    print(f"SMTP_AUTHENTICATED={result['success']}")
    print(f"CONNECTED_PORT={result['port']}")
    print(f"STAGE={result['stage']}")
    if result["error"]:
        print(f"ERROR={result['error']}")

    if result["success"]:
        print("No email was sent. SMTP login and NOOP succeeded.")
        return 0
    print("No email was sent. SMTP authentication check failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
