"""Smoke test — verify all bot modules import without error."""

import importlib
import pkgutil

import bot


def _collect_submodules(package) -> list[str]:
    """Recursively collect all submodule names under a package."""
    names: list[str] = []
    prefix = package.__name__ + "."
    for info in pkgutil.walk_packages(package.__path__, prefix=prefix):
        names.append(info.name)
    return names


def test_all_bot_modules_importable():
    """Every module under bot/ should import without raising."""
    modules = _collect_submodules(bot)
    assert len(modules) > 10, f"Expected 10+ modules, found {len(modules)}"

    failures: list[tuple[str, str]] = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append((name, str(exc)))

    if failures:
        report = "\n".join(f"  {mod}: {err}" for mod, err in failures)
        raise AssertionError(f"Failed to import {len(failures)} module(s):\n{report}")
