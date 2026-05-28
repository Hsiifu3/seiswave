import json
import os
import tempfile

import numpy as np

from seiswave.core.combiner import Combiner
from seiswave.core.signal import EQSignal


def _make_signal(freq=2.0, duration=5.0, dt=0.02, amp=0.3, name="edge"):
    t = np.arange(0, duration, dt)
    env = np.sin(np.pi * t / duration) ** 2
    acc = amp * env * np.sin(2 * np.pi * freq * t)
    return EQSignal(acc, dt, name=name)


def test_export_with_no_groups_writes_empty_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        c = Combiner(output_dir=tmpdir)
        out = c.export(fmt="at2")
        summary_path = os.path.join(out, "summary.json")
        assert os.path.isfile(summary_path)
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        assert summary["n_groups"] == 0
        assert summary["groups"] == []


def test_generate_html_report_without_valid_h1_still_succeeds():
    with tempfile.TemporaryDirectory() as tmpdir:
        c = Combiner(output_dir=tmpdir)
        c.add_artificial(h1=None, name="empty", index=0)
        periods = np.array([0.3, 0.5, 1.0])
        target_sa = np.array([0.5, 0.3, 0.1])
        path = c.generate_html_report(target_sa, periods)
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        assert "地震波组合报告" in html
        assert "empty_1" in html
        assert "平均谱最小比值" not in html
