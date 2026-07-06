"""End-to-end validation harness for GramTrans (helpers, not tests).

These modules shell out to FieldWorks (restore) and drive the api.py engine
facade against a live project pair. They import cleanly without a FLEx host so
the test module that uses them collects (and skips) cleanly; the actual FLEx /
flexicon calls are made lazily inside functions.
"""
