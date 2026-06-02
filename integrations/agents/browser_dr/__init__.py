"""Browser-DR adapter package.

Empty package marker. The :class:`BrowserDRAgent` lives in ``agent.py`` and is
registered lazily under the slug ``"browser-dr"`` in
``integrations/agents/__init__.py``; importing this package does NOT import
playwright or the RL env (the agent imports those lazily inside ``run()``).
"""
