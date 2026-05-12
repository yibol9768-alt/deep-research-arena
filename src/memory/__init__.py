"""Memory module — standalone, no pydantic dependency."""


def __getattr__(name):
    if name == "HierarchicalMemory":
        from .hierarchical import HierarchicalMemory
        return HierarchicalMemory
    if name == "mine_all":
        from .workflow_miner import mine_all
        return mine_all
    raise AttributeError(name)


__all__ = ["HierarchicalMemory", "mine_all"]
