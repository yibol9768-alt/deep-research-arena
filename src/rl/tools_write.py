"""Write-action tools for execution-scored RL tasks.

These tools are deliberately not grounding tools: they mutate an injected
sandbox state store and return ``ToolResult.state_delta`` for a separate
state-diff verifier. They never populate snippets or fetched URLs.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.rl.tools import ToolContext, ToolResult


@runtime_checkable
class WriteStore(Protocol):
    """Injected state store seam for transactional sandbox actions."""

    def cart_add(self, **kwargs: Any) -> dict[str, Any]: ...

    def order_place(self, **kwargs: Any) -> dict[str, Any]: ...

    def order_cancel(self, **kwargs: Any) -> dict[str, Any]: ...


def _store(ctx: ToolContext) -> Any | None:
    return (ctx.extras or {}).get("write_store")


def _call_store(store: Any, primary: str, fallback: str, payload: dict[str, Any]) -> dict[str, Any]:
    for name in (primary, fallback):
        fn = getattr(store, name, None)
        if callable(fn):
            result = fn(**payload)
            return dict(result or {}) if isinstance(result, dict) else {"result": result}
    raise AttributeError(f"write_store_missing_method:{primary}")


def _int_arg(args: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(args.get(key, default))
    except (TypeError, ValueError):
        return default


class CartAddTool:
    name = "cart_add"
    description = "Add a product to a sandbox cart; returns state_delta only."
    args_schema: dict[str, Any] = {
        "sku": {"type": "string", "required": False},
        "product_id": {"type": "string", "required": False},
        "quantity": {"type": "int", "required": False, "default": 1},
        "cart_id": {"type": "string", "required": False},
        "user_id": {"type": "string", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return ToolResult(ok=False, error="missing_write_store")
        sku = str(args.get("sku") or "").strip()
        product_id = str(args.get("product_id") or args.get("product") or "").strip()
        if not sku and not product_id:
            return ToolResult(ok=False, error="missing_product")
        payload = {
            "sku": sku or None,
            "product_id": product_id or None,
            "quantity": max(1, _int_arg(args, "quantity", 1)),
            "cart_id": str(args.get("cart_id") or "").strip() or None,
            "user_id": str(args.get("user_id") or "").strip() or None,
        }
        try:
            result = _call_store(store, "cart_add", "add_to_cart", payload)
        except Exception as exc:
            return ToolResult(ok=False, error=f"cart_add_failed:{type(exc).__name__}")
        delta = {"op": self.name, "item": payload, "result": result}
        return ToolResult(state_delta=delta, display=f"cart_add ok: {result}", ok=True, n_results=1)


class OrderPlaceTool:
    name = "order_place"
    description = "Place an order from a sandbox cart; returns state_delta only."
    args_schema: dict[str, Any] = {
        "cart_id": {"type": "string", "required": False},
        "user_id": {"type": "string", "required": False},
        "order_id": {"type": "string", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return ToolResult(ok=False, error="missing_write_store")
        payload = {
            "cart_id": str(args.get("cart_id") or "").strip() or None,
            "user_id": str(args.get("user_id") or "").strip() or None,
            "order_id": str(args.get("order_id") or "").strip() or None,
        }
        try:
            result = _call_store(store, "order_place", "place_order", payload)
        except Exception as exc:
            return ToolResult(ok=False, error=f"order_place_failed:{type(exc).__name__}")
        delta = {"op": self.name, "order": payload, "result": result}
        return ToolResult(state_delta=delta, display=f"order_place ok: {result}", ok=True, n_results=1)


class OrderCancelTool:
    name = "order_cancel"
    description = "Cancel an order in the sandbox; returns state_delta only."
    args_schema: dict[str, Any] = {
        "order_id": {"type": "string", "required": True},
        "reason": {"type": "string", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        store = _store(ctx)
        if store is None:
            return ToolResult(ok=False, error="missing_write_store")
        order_id = str(args.get("order_id") or args.get("order") or "").strip()
        if not order_id:
            return ToolResult(ok=False, error="missing_order_id")
        payload = {
            "order_id": order_id,
            "reason": str(args.get("reason") or "").strip() or None,
        }
        try:
            result = _call_store(store, "order_cancel", "cancel_order", payload)
        except Exception as exc:
            return ToolResult(ok=False, error=f"order_cancel_failed:{type(exc).__name__}")
        delta = {"op": self.name, "order": payload, "result": result}
        return ToolResult(state_delta=delta, display=f"order_cancel ok: {result}", ok=True, n_results=1)


def provide_tools() -> list[Any]:
    return [CartAddTool(), OrderPlaceTool(), OrderCancelTool()]


__all__ = [
    "CartAddTool",
    "OrderPlaceTool",
    "OrderCancelTool",
    "WriteStore",
    "provide_tools",
]
