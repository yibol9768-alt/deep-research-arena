from __future__ import annotations

from typing import Any

from src.rl.backends import ComputerUseBackend
from src.rl.env import Hit, MockSandboxBackend


class CountingBackend(MockSandboxBackend):
    def __init__(self) -> None:
        super().__init__({"http://localhost:7770/p.html": "exact inner text"}, {})
        self.fetch_calls = 0

    def fetch(self, url: str) -> str:
        self.fetch_calls += 1
        return super().fetch(url)


class ScriptedPolicy:
    def __init__(self, actions: list[dict[str, Any]]) -> None:
        self.actions = list(actions)
        self.observations: list[dict[str, Any]] = []

    def observe(self, url: str) -> dict[str, Any]:
        return {"screenshot": None, "text": f"proxy text {url}", "elements": []}

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        self.observations.append(dict(observation))
        if self.actions:
            return self.actions.pop(0)
        return {"action": "done"}


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    def click(self) -> None:
        self.page.events.append(("click", self.selector))

    def dblclick(self) -> None:
        self.page.events.append(("double_click", self.selector))

    def fill(self, text: str) -> None:
        self.page.events.append(("fill", self.selector, text))
        self.page.text = text


class FakeMouse:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def click(self, x: float, y: float) -> None:
        self.page.events.append(("mouse_click", x, y))

    def wheel(self, dx: float, dy: float) -> None:
        self.page.events.append(("wheel", dx, dy))

    def move(self, x: float, y: float) -> None:
        self.page.events.append(("move", x, y))

    def down(self) -> None:
        self.page.events.append(("down",))

    def up(self) -> None:
        self.page.events.append(("up",))


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def type(self, text: str) -> None:
        self.page.events.append(("type", text))
        self.page.text = text

    def press(self, key: str) -> None:
        self.page.events.append(("press", key))


class FakePage:
    def __init__(self) -> None:
        self.url = ""
        self.text = "initial page text"
        self.events: list[tuple[Any, ...]] = []
        self.mouse = FakeMouse(self)
        self.keyboard = FakeKeyboard(self)

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self.events.append(("goto", url))

    def wait_for_load_state(self, state: str) -> None:
        self.events.append(("load", state))

    def evaluate(self, expr: str) -> str:
        self.events.append(("evaluate", expr[:24]))
        return self.text

    def screenshot(self) -> bytes:
        self.events.append(("screenshot",))
        return b"png"

    def snapshot_accessibility(self) -> list[dict[str, Any]]:
        return [{"role": "button", "name": "Add to cart"}]

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)


def test_text_proxy_stays_byte_identical_and_single_fetch() -> None:
    inner = CountingBackend()
    backend = ComputerUseBackend.text_proxy(inner=inner)

    assert backend.fetch("http://localhost:7770/p.html") == "exact inner text"
    assert inner.fetch_calls == 1


def test_page_loop_applies_actions_and_returns_grounding_text() -> None:
    page = FakePage()
    policy = ScriptedPolicy(
        [
            {"action": "click", "selector": "#buy"},
            {"action": "type", "selector": "#note", "text": "typed note"},
            {"action": "scroll", "dy": 120},
            {"action": "keypress", "key": "Enter"},
            {"action": "screenshot"},
            {"action": "done"},
        ]
    )
    backend = ComputerUseBackend(policy, page=page, max_steps=10)

    text = backend.fetch("__SHOPPING__/p.html")

    assert text == "typed note"
    assert page.url == "http://localhost:7770/p.html"
    assert ("click", "#buy") in page.events
    assert ("fill", "#note", "typed note") in page.events
    assert ("wheel", 0.0, 120.0) in page.events
    assert ("press", "Enter") in page.events
    assert ("screenshot",) in page.events
    assert policy.observations[0]["screenshot"] == b"png"
    assert policy.observations[0]["elements"] == [{"role": "button", "name": "Add to cart"}]


def test_page_loop_supports_coordinate_move_and_drag() -> None:
    page = FakePage()
    policy = ScriptedPolicy(
        [
            {"action": "move", "point": [1, 2]},
            {"action": "drag", "from": {"x": 1, "y": 2}, "to": {"x": 3, "y": 4}},
            {"action": "done"},
        ]
    )
    backend = ComputerUseBackend(policy, page=page, max_steps=5)

    backend.fetch("http://localhost:7770/p.html")

    assert ("move", 1.0, 2.0) in page.events
    assert ("move", 3.0, 4.0) in page.events
    assert ("down",) in page.events
    assert ("up",) in page.events
