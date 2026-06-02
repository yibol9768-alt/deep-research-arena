"""Vision extraction tool for on-page image content."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.rl.tools import ToolContext, ToolResult


@runtime_checkable
class Captioner(Protocol):
    """Injected caption/OCR seam. Real VLM clients attach here."""

    def caption(
        self,
        image_url: str,
        page_url: str | None = None,
        prompt: str | None = None,
    ) -> str: ...


class ReadImageTool:
    """``read_image`` captions/OCRs an image and lands text into grounding."""

    name = "read_image"
    description = "Caption or OCR an image URL, returning citeable text for grounding."
    args_schema: dict[str, Any] = {
        "image_url": {"type": "string", "required": True},
        "page_url": {"type": "string", "required": False},
        "prompt": {"type": "string", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        image_url = str(args.get("image_url") or args.get("url") or "").strip()
        if not image_url:
            return ToolResult(ok=False, error="empty_image_url")
        captioner = (ctx.extras or {}).get("captioner")
        if captioner is None:
            return ToolResult(ok=False, error="missing_captioner")
        page_url = str(args.get("page_url") or "").strip() or None
        prompt = str(args.get("prompt") or "").strip() or None
        try:
            if callable(captioner) and not hasattr(captioner, "caption"):
                caption = captioner(image_url, page_url=page_url, prompt=prompt)
            else:
                caption = captioner.caption(image_url, page_url=page_url, prompt=prompt)
        except Exception as exc:
            return ToolResult(ok=False, error=f"caption_failed:{type(exc).__name__}")
        text = str(caption or "").strip()
        if not text:
            return ToolResult(ok=False, error="empty_caption")
        return ToolResult(
            snippets={image_url: text},
            fetched_urls=[image_url],
            display=text,
            n_results=1,
            ok=True,
        )


def provide_tools() -> list[Any]:
    return [ReadImageTool()]


__all__ = ["Captioner", "ReadImageTool", "provide_tools"]
