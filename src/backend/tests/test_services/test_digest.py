from datetime import date, datetime

from app.config import config
from app.services.digest import should_run


def test_config_digest_defaults():
    assert config.DIGEST_ENABLED is False
    assert config.DIGEST_HOUR == 7
    assert config.DIGEST_POLL_SECONDS == 300


def test_should_run_false_when_already_ran_today():
    now = datetime(2026, 6, 3, 9, 0)
    assert should_run(now, date(2026, 6, 3), hour=7) is False


def test_should_run_true_when_new_day_and_hour_passed():
    now = datetime(2026, 6, 3, 9, 0)
    assert should_run(now, date(2026, 6, 2), hour=7) is True


def test_should_run_true_when_never_ran_and_hour_passed():
    now = datetime(2026, 6, 3, 7, 0)
    assert should_run(now, None, hour=7) is True


def test_should_run_false_before_hour():
    now = datetime(2026, 6, 3, 6, 59)
    assert should_run(now, None, hour=7) is False
