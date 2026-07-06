"""Unit tests for Lib/debuglog.py — flag-gated diagnostic logging.

Covers the GRAMTRANS_DEBUG on/off gate, that enabling is a strict no-op when
off, that a `.debug()` write lands in the configured file when on, and that
`enable_from_env()` is idempotent (no duplicate handlers).
"""
import logging

import pytest

from gramtrans.Lib import debuglog


@pytest.fixture(autouse=True)
def _reset_debuglog(monkeypatch):
    """Ensure each test starts from a clean, disabled state and that no
    handlers / configured latch leak between tests."""
    monkeypatch.delenv(debuglog.DEBUG_ENV, raising=False)
    monkeypatch.delenv(debuglog.DEBUG_FILE_ENV, raising=False)
    debuglog._reset_for_tests()
    yield
    debuglog._reset_for_tests()


# ---------------------------------------------------------------------------
# is_enabled()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "anything"])
def test_is_enabled_truthy(monkeypatch, value):
    monkeypatch.setenv(debuglog.DEBUG_ENV, value)
    assert debuglog.is_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "FALSE", "no", "off", "  off  "])
def test_is_enabled_falsy(monkeypatch, value):
    monkeypatch.setenv(debuglog.DEBUG_ENV, value)
    assert debuglog.is_enabled() is False


def test_is_enabled_unset(monkeypatch):
    monkeypatch.delenv(debuglog.DEBUG_ENV, raising=False)
    assert debuglog.is_enabled() is False


# ---------------------------------------------------------------------------
# enable_from_env() — off
# ---------------------------------------------------------------------------

def test_enable_off_is_noop(monkeypatch):
    monkeypatch.delenv(debuglog.DEBUG_ENV, raising=False)
    assert debuglog.enable_from_env() is False
    for name in debuglog.LOGGER_NAMES:
        assert logging.getLogger(name).handlers == []


def test_enable_falsy_value_is_noop(monkeypatch):
    monkeypatch.setenv(debuglog.DEBUG_ENV, "0")
    assert debuglog.enable_from_env() is False
    for name in debuglog.LOGGER_NAMES:
        assert logging.getLogger(name).handlers == []


# ---------------------------------------------------------------------------
# enable_from_env() — on
# ---------------------------------------------------------------------------

def test_enable_on_creates_file_and_writes(monkeypatch, tmp_path):
    log_file = tmp_path / "gt-debug.log"
    monkeypatch.setenv(debuglog.DEBUG_ENV, "1")
    monkeypatch.setenv(debuglog.DEBUG_FILE_ENV, str(log_file))

    assert debuglog.enable_from_env() is True
    assert log_file.exists()

    marker = "persist-diagnostic-marker-123"
    logging.getLogger("gramtrans.Lib.transfer").debug(marker)
    for h in logging.getLogger("gramtrans").handlers:
        h.flush()

    contents = log_file.read_text(encoding="utf-8")
    assert marker in contents


def test_enable_on_configures_all_base_loggers(monkeypatch, tmp_path):
    monkeypatch.setenv(debuglog.DEBUG_ENV, "1")
    monkeypatch.setenv(debuglog.DEBUG_FILE_ENV, str(tmp_path / "d.log"))
    assert debuglog.enable_from_env() is True
    for name in debuglog.LOGGER_NAMES:
        lg = logging.getLogger(name)
        assert lg.level == logging.DEBUG
        assert lg.propagate is False
        assert len(lg.handlers) >= 1


def test_flat_logger_write_lands(monkeypatch, tmp_path):
    """A flat module logger (FlexTools runtime scheme) also reaches the file."""
    log_file = tmp_path / "flat.log"
    monkeypatch.setenv(debuglog.DEBUG_ENV, "1")
    monkeypatch.setenv(debuglog.DEBUG_FILE_ENV, str(log_file))
    assert debuglog.enable_from_env() is True

    marker = "flat-transfer-marker-456"
    logging.getLogger("transfer").debug(marker)
    for h in logging.getLogger("transfer").handlers:
        h.flush()
    assert marker in log_file.read_text(encoding="utf-8")


def test_enable_default_path(monkeypatch):
    """With no GRAMTRANS_DEBUG_FILE, the default temp-dir path is used."""
    monkeypatch.setenv(debuglog.DEBUG_ENV, "1")
    monkeypatch.delenv(debuglog.DEBUG_FILE_ENV, raising=False)
    assert debuglog.resolve_log_path() == debuglog.default_log_path()
    assert debuglog.enable_from_env() is True


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------

def test_enable_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv(debuglog.DEBUG_ENV, "1")
    monkeypatch.setenv(debuglog.DEBUG_FILE_ENV, str(tmp_path / "idem.log"))

    assert debuglog.enable_from_env() is True
    counts = {n: len(logging.getLogger(n).handlers) for n in debuglog.LOGGER_NAMES}

    # Many more calls must not add handlers.
    for _ in range(5):
        assert debuglog.enable_from_env() is True
    for name in debuglog.LOGGER_NAMES:
        assert len(logging.getLogger(name).handlers) == counts[name]


def test_bad_file_path_degrades_to_stderr(monkeypatch, tmp_path):
    """A bad GRAMTRANS_DEBUG_FILE must not crash; logging still enables
    (stderr StreamHandler only)."""
    bad = tmp_path / "no_such_dir" / "nested" / "x.log"
    monkeypatch.setenv(debuglog.DEBUG_ENV, "1")
    monkeypatch.setenv(debuglog.DEBUG_FILE_ENV, str(bad))

    assert debuglog.enable_from_env() is True
    # At least the stderr stream handler is attached.
    handlers = logging.getLogger("gramtrans").handlers
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)
