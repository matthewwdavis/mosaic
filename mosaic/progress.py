"""How far a long job has got (export, the figure report, Check, Refresh all pictures), for the
editor's progress bars, and its Stop.

The job plans its steps with rough weights (seconds, say, at 600 dpi), says what it's on before
each (`step`), and moves on after (`advance`). The editor asks for `state()` a few times a second
(api.job_progress) and can ask it to stop (`cancel`): the job stops at its next step with
Cancelled, cleaning up after itself. A job with no bar uses a Progress nobody looks at.
"""
from __future__ import annotations

import threading


class Cancelled(Exception):
    """The job was stopped (Stop in its window or note)."""


class Progress:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.done = 0.0
        self.total = 1.0
        self.label = ""
        self.cancelled = False

    def plan(self, total: float) -> None:
        """The whole job's weight (more can be added as it turns out to be needed)."""
        with self._lock:
            self.total = max(float(total), 1e-9)

    def add(self, weight: float) -> None:
        with self._lock:
            self.total += float(weight)

    def step(self, label: str) -> None:
        """What it's doing next; stops here if asked to."""
        self.check()
        with self._lock:
            self.label = label

    def advance(self, weight: float = 1.0) -> None:
        with self._lock:
            self.done = min(self.total, self.done + float(weight))
        self.check()

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled()

    def cancel(self) -> None:
        self.cancelled = True

    def state(self) -> dict:
        with self._lock:
            return {"fraction": min(1.0, self.done / self.total), "label": self.label, "cancelled": self.cancelled}
