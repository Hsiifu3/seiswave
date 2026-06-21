"""build.spec 的轻量烟测。"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "build.spec"


class _StubResult(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def _analysis_stub(*args, **kwargs):
    return _StubResult(
        name="Analysis",
        args=args,
        kwargs=kwargs,
        pure=["pure-module"],
        zipped_data=["zip-data"],
        scripts=["script.py"],
        binaries=["binary"],
        zipfiles=["zipfile"],
        datas=kwargs.get("datas", []),
    )


def _stub(name: str):
    def factory(*args, **kwargs):
        return _StubResult(name=name, args=args, kwargs=kwargs)

    return factory


def _run_spec_for(platform_name: str, monkeypatch) -> dict[str, object]:
    monkeypatch.setattr(sys, "platform", platform_name)
    return runpy.run_path(
        str(SPEC_PATH),
        init_globals={
            "Analysis": _analysis_stub,
            "BUNDLE": _stub("BUNDLE"),
            "COLLECT": _stub("COLLECT"),
            "EXE": _stub("EXE"),
            "PYZ": _stub("PYZ"),
            "SPECPATH": str(PROJECT_ROOT),
        },
    )


def test_build_spec_executes_for_windows(monkeypatch):
    result = _run_spec_for("win32", monkeypatch)
    analysis = result["a"]

    assert analysis["args"][0] == [str(PROJECT_ROOT / "seiswave" / "__main__.py")]
    assert analysis["kwargs"]["pathex"] == [str(PROJECT_ROOT)]
    assert "seiswave.gui.workbench.app_window" in analysis["kwargs"]["hiddenimports"]
    assert "seiswave.core.signal_pool" in analysis["kwargs"]["hiddenimports"]


def test_build_spec_executes_for_macos(monkeypatch):
    result = _run_spec_for("darwin", monkeypatch)

    assert result["exe"]["kwargs"]["name"] == "SeisWave"
    assert result["exe"]["kwargs"]["argv_emulation"] is True
    assert result["app"]["kwargs"]["bundle_identifier"] == "com.seiswave.workbench"
