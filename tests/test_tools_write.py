from __future__ import annotations

from typing import Any

from src.rl.env import CallTool, MockSandboxBackend, ResearchEnv
from src.rl.tools import ToolContext
from src.rl.tools_write import CartAddTool, OrderCancelTool, OrderPlaceTool, provide_tools


class FakeWriteStore:
    def __init__(self) -> None:
        self.cart: dict[str, Any] = {"items": []}
        self.orders: dict[str, Any] = {}

    def cart_add(self, **kwargs: Any) -> dict[str, Any]:
        item = {"sku": kwargs.get("sku"), "quantity": kwargs.get("quantity")}
        self.cart["items"].append(item)
        return {"observed_state": {"cart": self.cart}, "item": item}

    def order_place(self, **kwargs: Any) -> dict[str, Any]:
        order_id = kwargs.get("order_id") or "ord-1"
        self.orders[order_id] = {"status": "placed", "items": list(self.cart["items"])}
        return {"order_id": order_id, "observed_state": {"orders": self.orders}}

    def order_cancel(self, **kwargs: Any) -> dict[str, Any]:
        order_id = kwargs.get("order_id")
        self.orders.setdefault(order_id, {})["status"] = "cancelled"
        return {"order_id": order_id, "status": "cancelled", "observed_state": {"orders": self.orders}}


def _ctx(store: Any | None = None) -> ToolContext:
    return ToolContext(
        backend=None,
        task_config={},
        extras={"write_store": store} if store is not None else {},
    )


def test_provide_tools_lists_write_actions() -> None:
    assert [tool.name for tool in provide_tools()] == ["cart_add", "order_place", "order_cancel"]


def test_cart_add_returns_state_delta_only() -> None:
    result = CartAddTool().run(_ctx(FakeWriteStore()), {"sku": "NMX-PRO", "quantity": 2})

    assert result.ok is True
    assert result.state_delta["op"] == "cart_add"
    assert result.snippets == {}
    assert result.fetched_urls == []
    assert "cart_add ok" in result.display


def test_write_tools_validate_required_args() -> None:
    assert CartAddTool().run(_ctx(FakeWriteStore()), {}).error == "missing_product"
    assert OrderCancelTool().run(_ctx(FakeWriteStore()), {}).error == "missing_order_id"
    assert OrderPlaceTool().run(_ctx(), {}).error == "missing_write_store"


def test_env_records_write_state_delta_without_grounding() -> None:
    cfg = {"task_id": "write_test", "acquisition": {"tools_allowed": ["cart_add"]}}
    env = ResearchEnv(cfg, MockSandboxBackend({}, {}), max_tool_calls=5)
    base_ctx = env._tool_ctx
    store = FakeWriteStore()

    def patched_ctx() -> ToolContext:
        ctx = base_ctx()
        ctx.extras["write_store"] = store
        return ctx

    env._tool_ctx = patched_ctx  # type: ignore[method-assign]
    env.reset()
    env._tool_ctx = patched_ctx  # type: ignore[method-assign]
    obs, done, info = env.step(CallTool("cart_add", {"sku": "NMX-PRO", "quantity": 2}))

    assert done is False
    assert info["ok"] is True
    assert obs["retrieved_snippets"] == {}
    assert obs["fetched_urls"] == []
    rollout = env.to_rollout()
    assert rollout.trace is not None
    assert rollout.trace["tool_state_deltas"][0]["tool"] == "cart_add"
    assert rollout.trace["tool_state_deltas"][0]["delta"]["op"] == "cart_add"
