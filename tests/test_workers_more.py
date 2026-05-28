import numpy as np
import pytest

from seiswave.gui.workers import (
    FileLoadWorker,
    GeneratorWorker,
    MultiTrialGeneratorWorker,
    PeerIndexWorker,
    SelectionWorker,
    SpectrumWorker,
)


def _fake_pipe_with_messages(messages):
    class FakeParentConn:
        def __init__(self, msgs):
            self._msgs = list(msgs)
            self.closed = False

        def poll(self, timeout=None):
            return bool(self._msgs)

        def recv(self):
            return self._msgs.pop(0)

        def close(self):
            self.closed = True

    return FakeParentConn(messages), object()


class TestSpectrumAndSelectionWorkers:
    def test_spectrum_worker_delegates_to_spectra_compute(self, monkeypatch):
        sig = type("Sig", (), {"acc": np.array([1.0, 2.0]), "dt": 0.02})()
        periods = np.array([0.1, 0.5])
        captured = {}

        def fake_compute(acc, dt, periods_arg, zeta, method):
            captured["args"] = (acc, dt, periods_arg, zeta, method)
            return "spec"

        monkeypatch.setattr("seiswave.core.Spectra.compute", fake_compute)
        worker = SpectrumWorker(sig, periods, zeta=0.1, method="fft")
        out = worker.execute()

        assert out == "spec"
        assert captured["args"][1:] == (0.02, periods, 0.1, "fft")

    def test_selection_worker_emits_zero_progress_for_empty_total(self, monkeypatch):
        calls = []

        class FakeSelector:
            def select(self, db, progress_cb=None):
                progress_cb(0, 0)
                return ["ok"]

        worker = SelectionWorker(FakeSelector(), database="db")
        worker.signals.progress.connect(lambda pct, text: calls.append((pct, text)))
        out = worker.execute()

        assert out == ["ok"]
        assert calls == [(0, "筛选 0/0")]

    def test_selection_worker_raises_when_cancelled_in_callback(self):
        class FakeSelector:
            def select(self, db, progress_cb=None):
                progress_cb(1, 3)
                return []

        worker = SelectionWorker(FakeSelector(), database="db")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()


class TestPeerIndexAndFileLoad:
    def test_peer_index_worker_builds_and_saves_when_cache_missing(self, monkeypatch):
        events = []

        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1, 2, 3]
                self.saved = False
            def load_index(self):
                return False
            def build_index(self, progress_cb=None):
                progress_cb(2, 4)
            def save_index(self):
                self.saved = True
            def __len__(self):
                return len(self.records)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerIndexWorker("/tmp/fake")
        worker.signals.progress.connect(lambda pct, text: events.append((pct, text)))
        db = worker.execute()

        assert db.saved is True
        assert events[0] == (5, "检查索引缓存...")
        assert (50, "索引 2/4") in events
        assert events[-1] == (100, "索引完成: 3 条记录")

    def test_file_load_worker_uses_txt_loader_for_single_and_multi_column(self, monkeypatch):
        calls = []

        class FakeSignal:
            def __init__(self, name):
                self.name = name

        def fake_from_txt(path, dt=0.02, single_col=False):
            calls.append((path, dt, single_col))
            return FakeSignal(path)

        monkeypatch.setattr("seiswave.core.signal.EQSignal.from_txt", staticmethod(fake_from_txt))

        worker_single = FileLoadWorker(["a.txt"], fmt_idx=1)
        out_single = worker_single.execute()
        worker_multi = FileLoadWorker(["b.txt"], fmt_idx=2)
        out_multi = worker_multi.execute()

        assert [s.name for s in out_single] == ["a.txt"]
        assert [s.name for s in out_multi] == ["b.txt"]
        assert calls == [("a.txt", 0.02, True), ("b.txt", 0.02, False)]

    def test_file_load_worker_stops_when_cancelled(self, monkeypatch):
        class FakeSignal:
            def __init__(self, name):
                self.name = name

        def fake_from_at2(path):
            return FakeSignal(path)

        monkeypatch.setattr("seiswave.core.signal.EQSignal.from_at2", staticmethod(fake_from_at2))
        worker = FileLoadWorker(["a.at2", "b.at2"], fmt_idx=0)
        worker.cancel()
        assert worker.execute() == []


class TestGeneratorWorkerMore:
    def test_execute_handles_subprocess_progress_and_done(self, monkeypatch):
        parent_conn, child_conn = _fake_pipe_with_messages([
            ("progress", 2, 0.2, 0.1),
            ("done", [0.0, 0.1, 0.2], 0.02, "generated"),
        ])

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                self.terminated = False
            def start(self):
                return None
            def is_alive(self):
                return False
            def terminate(self):
                self.terminated = True

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, child_conn))
        monkeypatch.setattr(workers_mod.mp, "Process", FakeProcess)

        worker = GeneratorWorker(np.array([1.0]), np.array([0.1]), max_iter=4)
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        result = worker.execute()

        assert result.name == "generated"
        assert result.dt == 0.02
        assert progress == [(50, "迭代 2: 最大误差 0.2000, 平均误差 0.1000")]
        assert parent_conn.closed is True

    def test_execute_raises_subprocess_error(self, monkeypatch):
        parent_conn, child_conn = _fake_pipe_with_messages([
            ("error", "subprocess boom"),
        ])

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                return None
            def is_alive(self):
                return False
            def terminate(self):
                pass

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, child_conn))
        monkeypatch.setattr(workers_mod.mp, "Process", FakeProcess)

        worker = GeneratorWorker(np.array([1.0]), np.array([0.1]))
        with pytest.raises(RuntimeError, match="subprocess boom"):
            worker.execute()
        assert parent_conn.closed is True

    def test_execute_terminates_process_when_already_cancelled(self, monkeypatch):
        parent_conn, child_conn = _fake_pipe_with_messages([])
        holder = {}

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                self.terminated = False
                holder["proc"] = self
            def start(self):
                return None
            def is_alive(self):
                return True
            def terminate(self):
                self.terminated = True

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, child_conn))
        monkeypatch.setattr(workers_mod.mp, "Process", FakeProcess)

        worker = GeneratorWorker(np.array([1.0]), np.array([0.1]))
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()
        assert holder["proc"].terminated is True


class TestMultiTrialWorkerMore:
    def test_run_single_trial_handles_progress_and_done(self, monkeypatch):
        parent_conn, child_conn = _fake_pipe_with_messages([
            ("progress", 2, 0.3, 0.1),
            ("done", [0.0, 0.1], 0.02, "trial-1"),
        ])

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                return None
            def is_alive(self):
                return False
            def terminate(self):
                pass

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: (parent_conn, child_conn))
        monkeypatch.setattr(workers_mod.mp, "Process", FakeProcess)

        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]), max_iter=4, n_trials=4)
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        result = worker._run_single_trial(1)

        assert result.name == "trial-1"
        assert progress == [(37, "Trial 2/4 迭代 2: 最大误差 0.3000, 均值误差 0.1000")]
        assert parent_conn.closed is True

    def test_run_single_trial_falls_back_when_process_start_fails(self, monkeypatch):
        worker = MultiTrialGeneratorWorker(np.array([1.0]), np.array([0.1]), n_trials=3)
        monkeypatch.setattr(worker, "_generate_inprocess_trial", lambda idx: ("fallback", idx))

        class BadProcess:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                raise RuntimeError("boom")
            def is_alive(self):
                return False
            def terminate(self):
                pass

        import seiswave.gui.workers as workers_mod

        monkeypatch.setattr(workers_mod.mp, "Pipe", lambda: _fake_pipe_with_messages([]))
        monkeypatch.setattr(workers_mod.mp, "Process", BadProcess)
        assert worker._run_single_trial(2) == ("fallback", 2)
