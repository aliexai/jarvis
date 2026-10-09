"""NOVA - a local, voice-driven command-center desktop AI assistant for Windows.

This package is organised into independently testable modules:

* ``config``    - settings schema, paths and migrations
* ``security``  - policy engine, allowlists, secret store, redaction, audit log
* ``providers`` - LLM providers (added in a later phase)
* ``voice``     - STT / TTS / VAD (added in a later phase)
* ``agent``     - planner, tool router, sub-agents, approvals
* ``tools``     - PC-control tools
* ``memory``    - SQLite-backed memory
* ``api``       - local FastAPI + WebSocket surface
* ``ui``        - PySide6 shell and the React front-end
"""

__version__ = "0.1.0"
__app_name__ = "Nova"

__all__ = ["__version__", "__app_name__"]
