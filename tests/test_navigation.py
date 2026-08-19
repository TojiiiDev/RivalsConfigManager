"""Tests for ui/navigation.py — browser-like back/forward history."""

from __future__ import annotations

from ui.navigation import NavigationHistory


def test_empty_history() -> None:
    h = NavigationHistory()
    assert h.current() is None
    assert not h.can_go_back
    assert not h.can_go_forward
    assert h.back() is None
    assert h.forward() is None
    assert not h


def test_push_and_current() -> None:
    h = NavigationHistory()
    h.push(("home", None))
    assert h.current() == ("home", None)
    assert not h.can_go_back  # first state: nothing before it

    h.push(("browse", "x"))
    assert h.current() == ("browse", "x")
    assert h.can_go_back


def test_back_and_forward() -> None:
    h = NavigationHistory()
    h.push(("a", 1))
    h.push(("b", 2))
    h.push(("c", 3))

    assert h.back() == ("b", 2)
    assert h.current() == ("b", 2)
    assert h.can_go_forward

    assert h.back() == ("a", 1)
    assert not h.can_go_back
    assert h.back() is None  # at the start: nothing to go back to
    assert h.current() == ("a", 1)

    assert h.forward() == ("b", 2)
    assert h.forward() == ("c", 3)
    assert not h.can_go_forward
    assert h.forward() is None


def test_push_clears_forward() -> None:
    """A new navigation invalidates the forward path (browser behaviour)."""
    h = NavigationHistory()
    h.push(("a", 1))
    h.push(("b", 2))
    h.back()
    assert h.can_go_forward

    h.push(("c", 3))
    assert not h.can_go_forward
    assert h.forward() is None
    assert h.current() == ("c", 3)


def test_back_then_forward_roundtrip() -> None:
    h = NavigationHistory()
    for i in range(5):
        h.push(("p", i))
    # Back to the start: the previous state is returned each time.
    for i in range(3, -1, -1):
        assert h.back() == ("p", i)
    assert not h.can_go_back
    # Forward back to the end, in reverse order of the backs.
    for i in range(1, 5):
        assert h.forward() == ("p", i)
    assert h.current() == ("p", 4)


def test_replace_current_updates_current_and_clears_forward() -> None:
    """Updating the current state (e.g. an edited search) replaces it in
    place, keeps the back path, and invalidates the forward stack."""
    h = NavigationHistory()
    h.push(("home", None))
    h.push(("search", "v1"))
    h.replace_current(("search", "v2"))
    assert h.current() == ("search", "v2")
    assert h.can_go_back
    assert h.back() == ("home", None)  # the back path is preserved
    assert h.forward() == ("search", "v2")

    # After going back, replacing the current state clears forward.
    h.back()  # -> home again
    assert h.can_go_forward
    h.replace_current(("home", None))
    assert not h.can_go_forward


def test_drop_current() -> None:
    """Leaving an empty search drops the state without a forward entry."""
    h = NavigationHistory()
    h.push(("home", None))
    h.push(("search", "q"))
    h.drop_current()
    assert h.current() == ("home", None)
    assert not h.can_go_forward
    assert h.forward() is None


def test_clear() -> None:
    h = NavigationHistory()
    h.push(("a", 1))
    h.push(("b", 2))
    h.back()
    h.clear()
    assert h.current() is None
    assert not h.can_go_back
    assert not h.can_go_forward
    assert not h
    assert len(h) == 0


def test_states_returns_snapshot() -> None:
    h = NavigationHistory()
    h.push(("a", 1))
    h.push(("b", 2))
    snapshot = h.states
    h.back()
    # The snapshot is a copy, not a live view.
    assert snapshot == [("a", 1), ("b", 2)]
    assert h.states == [("a", 1)]


def test_bounded_size() -> None:
    from ui.navigation import MAX_STATES

    h = NavigationHistory()
    for i in range(MAX_STATES + 50):
        h.push(("p", i))
    assert len(h) == MAX_STATES
    # The oldest states were dropped: the first remaining one is reachable.
    assert h.states[0] == ("p", 50)
    h.back()
    assert h.current() == ("p", MAX_STATES + 48)
