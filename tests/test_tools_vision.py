from __future__ import annotations

from typing import Any

from src.rl.env import CallTool, MockSandboxBackend, ResearchEnv
from src.rl.tools import ToolContext
from src.rl.tools_vision import ReadImageTool, provide_tools
from src.verifiers.citation_format import canonicalize_url


IMAGE_URL = "http://localhost:7770/media/product/nova.jpg"
CAPTION = "Image shows the NovaMax Pro headphones with padded ear cups."


class FakeCaptioner:
    def __init__(self, caption: str = CAPTION) -> None:
        self.caption_text = caption
        self.calls: list[dict[str, Any]] = []

    def caption(self, image_url: str, page_url: str | None = None, prompt: str | None = None) -> str:
        self.calls.append({"image_url": image_url, "page_url": page_url, "prompt": prompt})
        return self.caption_text


def _ctx(captioner: Any | None = None) -> ToolContext:
    return ToolContext(
        backend=None,
        task_config={},
        extras={"captioner": captioner} if captioner is not None else {},
    )


def test_provide_tools_yields_read_image() -> None:
    tools = provide_tools()
    assert [tool.name for tool in tools] == ["read_image"]


def test_read_image_lands_caption_as_snippet() -> None:
    captioner = FakeCaptioner()
    result = ReadImageTool().run(
        _ctx(captioner),
        {"image_url": IMAGE_URL, "page_url": "http://localhost:7770/novamax-pro.html", "prompt": "OCR"},
    )

    assert result.ok is True
    assert result.snippets == {IMAGE_URL: CAPTION}
    assert result.fetched_urls == [IMAGE_URL]
    assert result.display == CAPTION
    assert captioner.calls[0]["prompt"] == "OCR"


def test_read_image_graceful_errors() -> None:
    assert ReadImageTool().run(_ctx(FakeCaptioner()), {}).error == "empty_image_url"
    assert ReadImageTool().run(_ctx(), {"image_url": IMAGE_URL}).error == "missing_captioner"
    assert ReadImageTool().run(_ctx(FakeCaptioner("")), {"image_url": IMAGE_URL}).error == "empty_caption"


def test_env_call_tool_read_image_folds_into_grounding() -> None:
    cfg = {"task_id": "vision_test", "acquisition": {"tools_allowed": ["read_image"]}}
    env = ResearchEnv(cfg, MockSandboxBackend({}, {}), max_tool_calls=5)
    base_ctx = env._tool_ctx

    def patched_ctx() -> ToolContext:
        ctx = base_ctx()
        ctx.extras["captioner"] = FakeCaptioner()
        return ctx

    env._tool_ctx = patched_ctx  # type: ignore[method-assign]
    env.reset()
    env._tool_ctx = patched_ctx  # type: ignore[method-assign]
    obs, done, info = env.step(CallTool("read_image", {"image_url": IMAGE_URL}))

    assert done is False
    assert info["ok"] is True
    assert obs["retrieved_snippets"] == {canonicalize_url(IMAGE_URL): CAPTION}
    assert obs["fetched_urls"] == [IMAGE_URL]
