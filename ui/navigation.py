"""Browser-like navigation history.

A small, pure-Python history used by the main window: :meth:`push` records
a state, :meth:`back` / :meth:`forward` move between visited states the way
a browser does. Pushing a new state clears the forward stack (a new
navigation invalidates the forward path).

The history is deliberately generic — a state is any ``(page, payload)``
tuple — so it stays reusable and trivially testable without Qt.
"""

from __future__ import annotations

from typing import Any

State = tuple[str, Any]

#: Maximum number of states kept (oldest are dropped, browser-style).
MAX_STATES = 500


class NavigationHistory:
    def __init__(self) -> None:
        self._back: list[State] = []
        self._forward: list[State] = []

    # ------------------------------------------------------------------ #
    @property
    def can_go_back(self) -> bool:
        """True when a previous state exists (i.e. the current state is not
        the first one ever visited)."""
        return len(self._back) > 1

    @property
    def can_go_forward(self) -> bool:
        return bool(self._forward)

    @property
    def states(self) -> list[State]:
        """A copy of the back stack (used to re-resolve payloads)."""
        return list(self._back)

    def current(self) -> State | None:
        """The state currently displayed, or ``None`` when empty."""
        return self._back[-1] if self._back else None

    # ------------------------------------------------------------------ #
    def push(self, state: State) -> None:
        """Record a newly visited state and invalidate the forward stack."""
        self._back.append(state)
        self._forward.clear()
        if len(self._back) > MAX_STATES:
            self._back.pop(0)

    def back(self) -> State | None:
        """Move one step back. Returns the state to display, or ``None``
        when there is nothing to go back to."""
        if not self.can_go_back:
            return None
        self._forward.append(self._back.pop())
        return self._back[-1]

    def forward(self) -> State | None:
        """Move one step forward. Returns the state to display, or ``None``
        when there is no forward path."""
        if not self.can_go_forward:
            return None
        state = self._forward.pop()
        self._back.append(state)
        return state

    def replace_current(self, state: State) -> None:
        """Replace the current state in place (e.g. an updated search query
        or filters) and invalidate the forward path."""
        if self._back:
            self._back[-1] = state
        else:
            self._back.append(state)
        self._forward.clear()

    def drop_current(self) -> None:
        """Remove the current state without keeping it in the forward stack
        (used when leaving a search that became empty)."""
        if self._back:
            self._back.pop()
        self._forward.clear()

    def clear(self) -> None:
        self._back.clear()
        self._forward.clear()

    # ------------------------------------------------------------------ #
    def __bool__(self) -> bool:
        return bool(self._back)

    def __len__(self) -> int:
        return len(self._back) + len(self._forward)
