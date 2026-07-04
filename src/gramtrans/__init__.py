"""GramTrans — FlexTools module package.

The shipped module is `gramtrans.gramtrans` — a flat FLExTrans-style entry file
exposing a `docs = {...}` metadata dict and a `MainFunction(project, report,
modifyAllowed)` callable. Helpers live under sibling `Lib/`, loaded at runtime
via `site.addsitedir(r"Lib")` from `gramtrans.py`.

Per constitution v5.1.0 Principle II this repo imports flexicon directly
(no flavor-adapter contract). The LibLCM-direct implementation is a separate
post-Phase-2 sibling repository per Principle IV.

This package's `__init__.py` deliberately does NOT re-export module-level
names from `gramtrans.py`: FlexTools imports `gramtrans.py` directly (which
performs the `site.addsitedir(r"Lib")` call); re-importing through here would
risk loading the helpers before `Lib/` is on `sys.path`.

See:
- README.md — flexicon install steps + repo overview
- CLAUDE.md — flexicon install path + agent context
- STATUS.md — most recent session's validated work
- specs/001-phase0-additive-transfer/ — spec / plan / tasks
"""

__version__ = "0.1.0"
