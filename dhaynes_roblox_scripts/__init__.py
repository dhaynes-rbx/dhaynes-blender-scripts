"""DHaynes Roblox Scripts.

Top-level Blender extension that auto-discovers and registers every tool module
found in the ``tools`` sub-package. To add a new tool, drop a ``.py`` file into
``tools/`` that exposes ``register()`` / ``unregister()`` functions; it will be
picked up automatically with no edits to this file.
"""

import importlib
import pkgutil

from . import tools

_loaded = []


def _iter_tool_modules():
    for _, name, _ in pkgutil.iter_modules(tools.__path__):
        if name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.tools.{name}")
        # Reload so "Reload Scripts" (F3) picks up edits during development.
        importlib.reload(mod)
        if hasattr(mod, "register") and hasattr(mod, "unregister"):
            yield mod


def register():
    global _loaded
    _loaded = list(_iter_tool_modules())
    for mod in _loaded:
        mod.register()


def unregister():
    for mod in reversed(_loaded):
        mod.unregister()
    _loaded.clear()
