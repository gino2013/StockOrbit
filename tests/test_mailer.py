import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def demo():
    os.environ.pop("SMTP_HOST", None)
    from app.infrastructure import mailer

    assert mailer.is_enabled() is False

    # disabled -> logs instead of raising / hanging
    with __import__("io").StringIO() as buf:
        handler = logging.StreamHandler(buf)
        mailer.logger.addHandler(handler)
        try:
            mailer.send("a@b.com", "subj", "body text")
        finally:
            mailer.logger.removeHandler(handler)
        log_output = buf.getvalue()
    assert "a@b.com" in log_output and "body text" in log_output

    os.environ["SMTP_HOST"] = "smtp.example.test"
    assert mailer.is_enabled() is True


if __name__ == "__main__":
    demo()
    print("OK")
