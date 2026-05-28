import numpy as np
import pytest

from seiswave.gui.workers import (
    BaseWorker,
    BatchSpectrumWorker,
    FileLoadWorker,
    GeneratorWorker,
    MultiTrialGeneratorWorker,
    SpecialGroundMotionWorker,
)


def _target_spectrum():
    periods = np.linspace(0.04, 6.0, 80)
    target = np.ones_like(periods) * 0.2
    return target, periods


def test_generator_worker_fallback_when_process_start_fails(monkeypatch):
    """当 multiprocessing 子进程无法启动时，应自动回退并仍可生成人工波。"""
    target, periods = _target_spectrum()

    class BadProcess:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("spawn bootstrap failed")

        def is_alive(self):
            return False

        def terminate(self):
            pass

    import seiswave.gui.workers as workers_mod
    monkeypatch.setattr(workers_mod.mp, "Process", BadProcess)

    worker = GeneratorWorker(target, periods, n=1024, dt=0.02, pga=0.2, max_iter=6)
    result = worker.execute()

    assert result is not None
    assert len(result.acc) == 1024
    assert result.dt == 0.02
    assert np.isclose(result.pga, 0.2, atol=1e-2)


class _DummyWorker(BaseWorker):
    def __init__(self, result=None, err=None):
        super().__init__()
        self._result = result
        self._err = err

    def execute(self):
        if self._err is not None:
            raise self._err
        return self._result


def test_base_worker_run_emits_finished_for_success():
    events = {"started": 0, "finished": [], "errors": []}
    worker = _DummyWorker(result={"ok": True})
    worker.signals.started.connect(lambda: events.__setitem__("started", events["started"] + 1))
    worker.signals.finished.connect(lambda result: events["finished"].append(result))
    worker.signals.error.connect(lambda err: events["errors"].append(err))

    worker.run()

    assert events["started"] == 1
    assert events["finished"] == [{"ok": True}]
    assert events["errors"] == []


def test_base_worker_run_emits_error_for_exception():
    events = {"finished": [], "errors": []}
    worker = _DummyWorker(err=RuntimeError("boom"))
    worker.signals.finished.connect(lambda result: events["finished"].append(result))
    worker.signals.error.connect(lambda err: events["errors"].append(err))

    worker.run()

    assert events["finished"] == []
    assert events["errors"] == ["boom"]


def test_batch_spectrum_worker_emits_progress_and_returns_pairs():
    from seiswave.core import EQSignal

    sig1 = EQSignal(np.sin(np.linspace(0, 4, 512)), 0.02, name="s1")
    sig2 = EQSignal(np.cos(np.linspace(0, 4, 512)), 0.02, name="s2")
    periods = np.array([0.1, 0.5, 1.0])

    worker = BatchSpectrumWorker([sig1, sig2], periods)
    progress = []
    worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
    result = worker.execute()

    assert len(result) == 2
    assert result[0][0] is sig1
    assert result[1][0] is sig2
    assert progress[-1][0] == 100
    assert "s2" in progress[-1][1]


def test_file_load_worker_skips_bad_file_and_reports_progress(monkeypatch):
    class FakeSignal:
        def __init__(self, name):
            self.name = name

    calls = []

    def fake_from_at2(path):
        calls.append(path)
        if path.endswith("bad.at2"):
            raise ValueError("bad file")
        return FakeSignal(path)

    import seiswave.core.signal as signal_mod
    monkeypatch.setattr(signal_mod.EQSignal, "from_at2", staticmethod(fake_from_at2))

    worker = FileLoadWorker(["good1.at2", "bad.at2", "good2.at2"], fmt_idx=0)
    progress = []
    worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
    result = worker.execute()

    assert [sig.name for sig in result] == ["good1.at2", "good2.at2"]
    assert calls == ["good1.at2", "bad.at2", "good2.at2"]
    assert progress[-1][0] == 100
    assert "good2.at2" in progress[-1][1]


def test_special_ground_motion_worker_progress_callback_and_params(monkeypatch):
    class FakeSignal:
        name = "special"

    progress_events = []

    def fake_create_ground_motion(**kwargs):
        kwargs["progress_callback"](3, 0.12, 0.05)
        return FakeSignal()

    monkeypatch.setattr(
        "seiswave.core.generator.create_ground_motion",
        fake_create_ground_motion,
    )

    worker = SpecialGroundMotionWorker(
        gm_type="NF", Mw=6.8, R=12.0, Vs30=500.0,
        fault_type="reverse", n=2048, dt=0.01,
        max_iter=10, fm=1,
    )
    worker.signals.progress.connect(lambda pct, text: progress_events.append((pct, text)))
    result = worker.execute()

    assert result.name == "special"
    assert progress_events == [(30, "迭代 3/10: 最大误差 0.1200, 平均误差 0.0500")]


def test_multi_trial_worker_selects_lowest_mean_error(monkeypatch):
    from seiswave.core import EQSignal

    target, periods = _target_spectrum()
    sig_a = EQSignal(np.zeros(64), 0.02, name="a")
    sig_b = EQSignal(np.zeros(64), 0.02, name="b")
    sig_c = EQSignal(np.zeros(64), 0.02, name="c")

    worker = MultiTrialGeneratorWorker(target, periods, n_trials=3)
    seq = iter([sig_a, sig_b, sig_c])
    monkeypatch.setattr(worker, "_run_single_trial", lambda idx: next(seq))

    class FakeSpec:
        def __init__(self, val):
            self.sa = np.array([val])

    spec_vals = iter([0.3, 0.1, 0.2])
    monkeypatch.setattr(
        "seiswave.core.Spectra.compute",
        lambda acc, dt, periods, zeta: FakeSpec(next(spec_vals)),
    )
    monkeypatch.setattr(
        "seiswave.core.WaveGenerator.fit_error",
        lambda sa, target: {"mean_error": float(sa[0])},
    )

    progress = []
    worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
    result = worker.execute()

    assert result["best"] is sig_b
    assert result["best_index"] == 1
    assert result["all_results"] == [sig_a, sig_b, sig_c]
    assert progress[-1] == (100, "完成: 最优 Trial 2")
