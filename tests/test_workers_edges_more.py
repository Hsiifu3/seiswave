import numpy as np
import pytest
from types import SimpleNamespace

from seiswave.gui.workers import (
    BaseWorker,
    BatchSpectrumWorker,
    CombinerWorker,
    GeneratorWorker,
    MultiTrialGeneratorWorker,
    PeerIndexWorker,
    PeerLoadWorker,
    PeerSelectWorker,
    SpectraPrecomputeWorker,
    _generator_subprocess,
)


class _ParentConn:
    def __init__(self, msgs):
        self._msgs = list(msgs)
        self.closed = False

    def poll(self, timeout=None):
        return bool(self._msgs)

    def recv(self):
        return self._msgs.pop(0)

    def close(self):
        self.closed = True


class _DummyProcess:
    def __init__(self, alive=False):
        self._alive = alive
        self.terminated = False

    def is_alive(self):
        return self._alive

    def terminate(self):
        self.terminated = True


class TestWorkerEdges:
    def test_base_worker_execute_not_implemented(self):
        with pytest.raises(NotImplementedError):
            BaseWorker().execute()

    def test_batch_spectrum_worker_breaks_when_cancelled_during_loop(self, monkeypatch):
        calls = []

        class Sig:
            def __init__(self, name):
                self.name = name
                self.acc = np.array([0.0, 1.0])
                self.dt = 0.02

        worker = BatchSpectrumWorker([Sig("a"), Sig("b")], np.array([0.1]))

        def fake_compute(*args, **kwargs):
            calls.append(1)
            worker.cancel()
            return "spec"

        monkeypatch.setattr("seiswave.core.Spectra.compute", fake_compute)
        out = worker.execute()
        assert len(out) == 1
        assert len(calls) == 1

    def test_generator_subprocess_sends_done_and_error(self, monkeypatch):
        sent = []

        class Conn:
            def send(self, msg):
                sent.append(msg)
            def close(self):
                sent.append(("closed",))

        def fake_generate(*args, **kwargs):
            kwargs["progress_callback"](1, 0.2, 0.1)
            return SimpleNamespace(acc=np.array([0.1]), dt=0.02, name="ok")

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", fake_generate)
        _generator_subprocess(Conn(), np.array([1.0]), np.array([0.1]), 1, 0.02, 0.05, 1.0, 0.1, 3)
        assert sent[0] == ("progress", 1, 0.2, 0.1)
        assert sent[1][0] == "done"
        assert sent[-1] == ("closed",)

        sent2 = []

        class Conn2:
            def send(self, msg):
                sent2.append(msg)
            def close(self):
                sent2.append(("closed",))

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        _generator_subprocess(Conn2(), np.array([1.0]), np.array([0.1]), 1, 0.02, 0.05, 1.0, 0.1, 3)
        assert sent2[0] == ("error", "boom")
        assert sent2[-1] == ("closed",)

    def test_generator_subprocess_ignores_progress_send_failure(self, monkeypatch):
        sent = []

        class Conn:
            def __init__(self):
                self.calls = 0
            def send(self, msg):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("send failed")
                sent.append(msg)
            def close(self):
                sent.append(("closed",))

        def fake_generate(*args, **kwargs):
            kwargs["progress_callback"](1, 0.2, 0.1)
            return SimpleNamespace(acc=np.array([0.1]), dt=0.02, name="ok")

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", fake_generate)
        _generator_subprocess(Conn(), np.array([1.0]), np.array([0.1]), 1, 0.02, 0.05, 1.0, 0.1, 3)
        assert sent[0][0] == "done"

    def test_generator_worker_cancel_terminates_process(self):
        worker = GeneratorWorker(np.array([1.0]), np.array([0.1]))
        proc = _DummyProcess(alive=True)
        worker._process = proc
        worker.cancel()
        assert proc.terminated is True

    def test_generator_worker_inprocess_progress_raises_if_cancelled(self, monkeypatch):
        def fake_generate(*args, **kwargs):
            kwargs["progress_callback"](1, 0.2, 0.1)
            return "never"

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", fake_generate)
        worker = GeneratorWorker(np.array([1.0]), np.array([0.1]), max_iter=4)
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker._generate_inprocess()

    def test_generator_worker_falls_back_after_silent_subprocess_exit(self, monkeypatch):
        parent_conn = _ParentConn([])

        class Proc:
            def start(self):
                return None
            def is_alive(self):
                return False
            def terminate(self):
                pass

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, object()))
        monkeypatch.setattr(workers_mod.mp, "Process", lambda *a, **k: Proc())
        worker = GeneratorWorker(np.array([1.0]), np.array([0.1]))
        monkeypatch.setattr(worker, "_generate_inprocess", lambda: "fallback")
        assert worker.execute() == "fallback"
        assert parent_conn.closed is True

    def test_multitrial_cancel_terminates_process(self):
        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]))
        proc = _DummyProcess(alive=True)
        worker._process = proc
        worker.cancel()
        assert proc.terminated is True

    def test_multitrial_run_single_trial_raises_when_cancelled(self, monkeypatch):
        parent_conn = _ParentConn([])

        class Proc:
            def start(self):
                return None
            def is_alive(self):
                return True
            def terminate(self):
                parent_conn.closed = True

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, object()))
        monkeypatch.setattr(workers_mod.mp, "Process", lambda *a, **k: Proc())

        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]))
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker._run_single_trial(0)

    def test_generate_inprocess_trial_emits_progress(self, monkeypatch):
        events = []

        def fake_generate(*args, **kwargs):
            kwargs["progress_callback"](2, 0.2, 0.1)
            return "sig"

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", fake_generate)
        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]), max_iter=4, n_trials=2)
        worker.signals.progress.connect(lambda pct, text: events.append((pct, text)))
        assert worker._generate_inprocess_trial(1) == "sig"
        assert events == [(75, "Trial 2/2 迭代 2: 最大误差 0.2000, 均值误差 0.1000")]

    def test_generate_inprocess_trial_raises_if_cancelled(self, monkeypatch):
        def fake_generate(*args, **kwargs):
            kwargs["progress_callback"](1, 0.2, 0.1)
            return "never"

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", fake_generate)
        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]), n_trials=2)
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker._generate_inprocess_trial(0)

    def test_multitrial_run_single_trial_falls_back_after_silent_exit(self, monkeypatch):
        parent_conn = _ParentConn([])

        class Proc:
            def start(self):
                return None
            def is_alive(self):
                return False
            def terminate(self):
                pass

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, object()))
        monkeypatch.setattr(workers_mod.mp, "Process", lambda *a, **k: Proc())
        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]))
        monkeypatch.setattr(worker, "_generate_inprocess_trial", lambda idx: ("fallback", idx))
        assert worker._run_single_trial(1) == ("fallback", 1)
        assert parent_conn.closed is True

    def test_multitrial_execute_raises_when_cancelled_before_loop(self):
        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]))
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_peer_load_worker_builds_and_precomputes_when_cache_missing(self, monkeypatch):
        events = []

        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = []
            def load_index(self):
                return False
            def build_index(self):
                events.append("built")
            def __len__(self):
                return 2
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                progress_cb(1, 2)
                events.append((len(periods), zeta))

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerLoadWorker("/tmp/fake")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()
        assert isinstance(db, FakeDB)
        assert "built" in events
        assert any(p == 77 for p, _ in progress)
        assert progress[-1] == (100, "加载完成")

    def test_special_ground_motion_worker_progress_raises_if_cancelled(self, monkeypatch):
        def fake_create_ground_motion(**kwargs):
            kwargs["progress_callback"](1, 0.2, 0.1)
            return "never"

        monkeypatch.setattr("seiswave.core.generator.create_ground_motion", fake_create_ground_motion)
        from seiswave.gui.workers import SpecialGroundMotionWorker

        worker = SpecialGroundMotionWorker("FF", 7.0, 10.0)
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_peer_select_worker_raises_when_cancelled(self, monkeypatch):
        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 2)
                return ["hit"]

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = PeerSelectWorker({}, object())
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_peer_index_worker_raises_when_cancelled_in_progress(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                pass
            def load_index(self):
                return False
            def build_index(self, progress_cb=None):
                progress_cb(1, 2)
            def save_index(self):
                raise AssertionError("should not reach save")

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerIndexWorker("/tmp/fake")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_spectra_precompute_worker_default_periods_and_cancel(self):
        seen = {}

        class FakeDB:
            records = []
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                seen["len"] = len(periods)
                progress_cb(1, 2)

        worker = SpectraPrecomputeWorker(FakeDB())
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()
        assert seen["len"] == 200

    def test_selector_worker_raises_when_cancelled(self, monkeypatch):
        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 2)
                return ["hit"]

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        from seiswave.gui.workers import SelectorWorker
        worker = SelectorWorker({}, object())
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_combiner_worker_raises_when_cancelled_on_natural_or_generated(self, monkeypatch):
        class FakeCombiner:
            def __init__(self, output_dir):
                pass
            def add_natural(self, r, db):
                pass
            def add_artificial(self, sig, name, index):
                pass
            def export(self, fmt="at2"):
                pass

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        worker = CombinerWorker([object()], object(), [], "/tmp/out")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

        worker2 = CombinerWorker([], object(), [object()], "/tmp/out")
        worker2.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker2.execute()

    def test_peer_select_worker_progress_and_return(self, monkeypatch):
        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 2)
                return ["hit"]

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = PeerSelectWorker({}, object())
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        assert worker.execute() == ["hit"]
        assert progress == [(50, "筛选 1/2")]

    def test_peer_index_worker_returns_cached_db(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                pass
            def load_index(self):
                return True
            def __len__(self):
                return 7

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerIndexWorker("/tmp/fake")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()
        assert isinstance(db, FakeDB)
        assert progress[-1] == (100, "从缓存加载 7 条记录")

    def test_spectra_precompute_worker_returns_cached_db(self):
        recs = [SimpleNamespace(sa=1), SimpleNamespace(sa=None), SimpleNamespace(sa=2)]

        class FakeDB:
            records = recs
            def load_spectra_cache(self, zeta):
                return True

        worker = SpectraPrecomputeWorker(FakeDB())
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()
        assert isinstance(db, FakeDB)
        assert progress[-1] == (100, "从缓存加载 2 条反应谱")

    def test_combiner_worker_skips_report_when_target_missing(self, monkeypatch):
        class FakeCombiner:
            def __init__(self, output_dir):
                self.output_dir = output_dir
            def add_natural(self, r, db):
                pass
            def add_artificial(self, sig, name, index):
                pass
            def export(self, fmt="at2"):
                self.fmt = fmt
            def generate_html_report(self, *args, **kwargs):
                raise AssertionError("should not be called")

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        worker = CombinerWorker([object()], object(), [object()], "/tmp/out", fmt="txt")
        out = worker.execute()
        assert out["report_path"] is None
        assert out["output_dir"] == "/tmp/out"
