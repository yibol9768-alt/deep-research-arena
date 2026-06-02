"""Per-task evolving-rubric refresh cadence."""

from __future__ import annotations


class RefreshScheduler:
    def __init__(self, n: int = 16) -> None:
        if n <= 0:
            raise ValueError("refresh interval n must be positive")
        self.n = int(n)
        self.last_refresh: dict[str, int] = {}

    def should_refresh(self, task_id: str, step: int) -> bool:
        key = str(task_id)
        current_step = int(step)
        last = self.last_refresh.get(key)
        if last is None or current_step - last >= self.n:
            self.last_refresh[key] = current_step
            return True
        return False
