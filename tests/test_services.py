"""Tests for app/services.py.

schedule_next() is pure logic and currently has NO tests. Writing them is the
Week 1 testing exercise.

TODO(student): test schedule_next(rating, interval, ease). Cover at least:
  - happy path: a "good" review grows the interval
  - "again" resets the interval to 0
  - ease never drops below EASE_FLOOR (1.3)
  - an unknown rating raises ValueError
"""

from __future__ import annotations
