"""Flag-gated diagnostic logging for the GramTrans export/persist path.

Turned on with the ``GRAMTRANS_DEBUG`` environment variable (truthy = on).
When OFF this module is a strict no-op: ``enable_from_env()`` configures no
handlers and returns ``False``, and the ``_log.debug(...)`` calls sprinkled
through the engine short-circuit inside stdlib ``logging`` at negligible cost.

Why this exists
---------------
Users report "Export doesn't persist for any items." The export→persist chain
(``api.execute_move`` → ``transfer.execute`` → ``gramtrans._run_gui``'s
``CloseProject()``) swallows per-item exceptions and builds its RunReport from
the *plan* rather than from what actually got written, so a silent failure is
invisible. Setting ``GRAMTRANS_DEBUG=1`` before running the FlexTools module
turns on DEBUG logging across that chain to a file (and stderr) so the failing
step can be identified. This module changes NO transfer behavior.

Logger-name note
----------------
The engine modules use dual-mode imports (``from .models import ...`` when run
as the ``gramtrans`` package, ``from models import ...`` when FlexTools puts
``Lib/`` on ``sys.path`` via ``site.addsitedir``). As a result the same module
has ``__name__ == "gramtrans.Lib.transfer"`` in package/test contexts but a
flat ``__name__ == "transfer"`` under FlexTools at export runtime. To catch the
``logging.getLogger(__name__)`` loggers in BOTH schemes we configure handlers
on every relevant base logger name (see ``LOGGER_NAMES``).
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import List, Optional

# Environment variables.
DEBUG_ENV = "GRAMTRANS_DEBUG"
DEBUG_FILE_ENV = "GRAMTRANS_DEBUG_FILE"

# Values that count as "off" even when the variable is present.
_FALSY = frozenset({"", "0", "false", "no", "off"})

# Base logger names to configure. ``gramtrans`` covers the package/test scheme
# (``gramtrans.Lib.transfer``, ``gramtrans.gramtrans``, ...) AND a flat
# ``gramtrans`` entry module; the remaining names cover the flat FlexTools
# scheme where ``site.addsitedir`` yields top-level module names.
LOGGER_NAMES = (
    "gramtrans",
    "transfer",
    "api",
    "preview",
    "selection_wizard",
)

# Module state (guards idempotency of enable_from_env).
_configured = False
_handlers: List[logging.Handler] = []


def _truthy(value: Optional[str]) -> bool:
    """Return True when ``value`` is a truthy flag string.

    ``None`` (unset) and the case-insensitive members of ``_FALSY`` are off;
    everything else is on.
    """
    if value is None:
        return False
    return value.strip().lower() not in _FALSY


def is_enabled() -> bool:
    """Return True when ``GRAMTRANS_DEBUG`` is set to a truthy value.

    Read at call time so tests / callers can flip the flag at runtime.
    """
    return _truthy(os.environ.get(DEBUG_ENV))


def default_log_path() -> str:
    """Default debug-log path: ``<tempdir>/gramtrans-debug.log``."""
    return os.path.join(tempfile.gettempdir(), "gramtrans-debug.log")


def resolve_log_path() -> str:
    """Resolve the debug-log path: ``GRAMTRANS_DEBUG_FILE`` if set and
    non-empty, otherwise :func:`default_log_path`."""
    return os.environ.get(DEBUG_FILE_ENV) or default_log_path()


def enable_from_env() -> bool:
    """Configure flag-gated debug logging if ``GRAMTRANS_DEBUG`` is truthy.

    Idempotent: safe to call many times (e.g. once per export entry point);
    handlers are attached at most once. Returns True when logging is (now or
    already) enabled, False when the flag is off.

    When enabling, the configured base loggers (:data:`LOGGER_NAMES`) are set
    to DEBUG with ``propagate=False`` and receive a shared FileHandler +
    stderr StreamHandler using a timestamped formatter. A one-line banner
    naming the resolved log-file path is emitted. FileHandler creation is
    wrapped in ``try/except OSError`` so a bad ``GRAMTRANS_DEBUG_FILE`` path
    cannot crash the export — logging degrades to stderr only.
    """
    global _configured
    if not is_enabled():
        return False
    if _configured:
        return True

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = resolve_log_path()
    file_status = None
    try:
        file_handler: Optional[logging.Handler] = logging.FileHandler(
            log_path, mode="a", encoding="utf-8"
        )
    except OSError as exc:  # bad path / permissions — never crash the export
        file_handler = None
        file_status = f"file handler unavailable ({exc}); stderr only"

    handlers: List[logging.Handler] = []
    if file_handler is not None:
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)

    stream_handler = logging.StreamHandler()  # stderr by default
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)
    handlers.append(stream_handler)

    for name in LOGGER_NAMES:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        for h in handlers:
            lg.addHandler(h)

    _handlers[:] = handlers
    _configured = True

    banner = logging.getLogger("gramtrans")
    banner.debug(
        "GRAMTRANS_DEBUG enabled; debug log -> %s%s",
        log_path,
        "" if file_status is None else f"  [{file_status}]",
    )
    return True


def _reset_for_tests() -> None:
    """Detach configured handlers and clear module state (test-only).

    Not part of the runtime API; used by the test fixture so tests don't leak
    handlers or the ``_configured`` latch into one another.
    """
    global _configured
    for name in LOGGER_NAMES:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            if h in _handlers:
                lg.removeHandler(h)
        lg.setLevel(logging.NOTSET)
        lg.propagate = True
    for h in _handlers:
        try:
            h.close()
        except Exception:
            pass
    _handlers.clear()
    _configured = False
