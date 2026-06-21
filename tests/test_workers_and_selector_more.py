import numpy as np
import pytest
from types import SimpleNamespace


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_sig(name="sig", dt=0.02, n=128):
    from seiswave.core import EQSignal
    t = np.arange(n) * dt
    acc = np.sin(2 * np.pi * 2.0 * t) * 0.1
    return EQSignal(acc, dt, name=name)


# ──────────── workers.py ────────────

class TestWorkersMore:
    def test_base_worker_cancel_and_error_path(self, qapp):
        from seiswave.gui.workers import BaseWorker

        class BadWorker(BaseWorker):
            def execute(self):
                raise RuntimeError("boom")

        w = BadWorker()
        errors = []
        w.signals.error.connect(errors.append)
        w.cancel()
        assert w.is_cancelled
        w.run()  # run directly (not start, to avoid thread issues in test)
        assert errors == ["boom"]

    def test_file_load_worker_txt_path(self, qapp, tmp_path):
        from seiswave.gui.workers import FileLoadWorker

        f1 = tmp_path / "a.txt"
        np.savetxt(f1, np.column_stack([np.arange(10) * 0.02, np.ones(10) * 0.1]))

        w = FileLoadWorker([str(f1)], fmt_idx=1)
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        result = w.execute()
        assert len(result) == 1
        assert progress[-1][0] == 100

    def test_special_ground_motion_worker_execute(self, qapp, monkeypatch):
        from seiswave.gui.workers import SpecialGroundMotionWorker

        called = {}

        def fake_create(*a, **k):
            called["args"] = a
            called["kwargs"] = k
            return _make_sig("special")

        monkeypatch.setattr("seiswave.core.generator.create_ground_motion", fake_create)
        w = SpecialGroundMotionWorker("FF", 7.0, 10.0)
        result = w.execute()
        assert result.name == "special"
        assert called["kwargs"]["type"] == "FF"

    def test_peer_load_worker_with_mock_db(self, qapp, monkeypatch):
        from seiswave.gui.workers import PeerLoadWorker

        class FakeDB:
            def __init__(self, data_dir):
                self.records = []
                self._spectra_periods = None

            def __len__(self):
                return 3

            def load_index(self):
                return True

            def load_spectra_cache(self, zeta):
                return True

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        w = PeerLoadWorker("/fake/dir")
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        db = w.execute()
        assert len(db) == 3
        assert any(p == 100 for p, _ in progress)

    def test_peer_index_worker_builds_when_no_cache(self, qapp, monkeypatch):
        from seiswave.gui.workers import PeerIndexWorker

        built = []
        saved = []

        class FakeDB:
            def __init__(self, data_dir):
                self.records = [1, 2, 3]

            def __len__(self):
                return 3

            def load_index(self):
                return False

            def build_index(self, progress_cb=None):
                built.append(True)
                if progress_cb:
                    progress_cb(1, 2)

            def save_index(self):
                saved.append(True)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        w = PeerIndexWorker("/fake/dir")
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        db = w.execute()
        assert len(db) == 3
        assert built
        assert saved

    def test_spectra_precompute_worker_uses_periods(self, qapp, monkeypatch):
        from seiswave.gui.workers import SpectraPrecomputeWorker

        precomputed = []

        class FakeDB:
            def load_spectra_cache(self, zeta):
                return False

            def precompute_spectra(self, periods, zeta, progress_cb=None):
                precomputed.append((list(periods), zeta))
                if progress_cb:
                    progress_cb(1, 1)

        db = FakeDB()
        w = SpectraPrecomputeWorker(db, periods=np.array([0.1, 0.5]), zeta=0.05)
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        result = w.execute()
        assert precomputed[0][0] == [0.1, 0.5]
        assert result is db

    def test_selector_worker(self, qapp, monkeypatch):
        from seiswave.gui.workers import SelectorWorker

        class FakeSelector:
            def __init__(self, config):
                self.config = config

            def select(self, db, progress_cb=None):
                if progress_cb:
                    progress_cb(1, 2)
                return ["result1"]

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        w = SelectorWorker({}, object())
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        result = w.execute()
        assert result == ["result1"]
        assert any(p == 100 for p, _ in progress)

    def test_combiner_worker(self, qapp, monkeypatch):
        from seiswave.gui.workers import CombinerWorker

        exported = []
        reported = []

        class FakeCombiner:
            def __init__(self, output_dir):
                pass

            def add_natural(self, r, db):
                pass

            def add_artificial(self, sig, name, index):
                pass

            def export(self, fmt="at2"):
                exported.append(fmt)

            def generate_html_report(self, target_sa, periods):
                reported.append(True)
                return "/fake/report.html"

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        sig = _make_sig("art1")
        w = CombinerWorker(
            results=[object()], database=object(), generated_waves=[sig],
            output_dir="/fake", fmt="txt", target_sa=np.array([0.1]), periods=np.array([0.1])
        )
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        result = w.execute()
        assert exported == ["txt"]
        assert reported
        assert result["report_path"] == "/fake/report.html"

    def test_generator_worker_inprocess_path(self, qapp, monkeypatch):
        from seiswave.gui.workers import GeneratorWorker

        monkeypatch.setattr("seiswave.core.WaveGenerator.generate", lambda *a, **k: _make_sig("gen1"))
        w = GeneratorWorker(np.array([0.1, 0.2]), np.array([0.1, 0.5]))
        result = w._generate_inprocess()
        assert result.name == "gen1"

    def test_multi_trial_worker_mock_trial(self, qapp, monkeypatch):
        from seiswave.gui.workers import MultiTrialGeneratorWorker

        monkeypatch.setattr("seiswave.core.generator.WaveGenerator.generate", lambda *a, **k: _make_sig("trial"))
        monkeypatch.setattr("seiswave.core.spectrum.Spectra.compute", lambda *a, **k: SimpleNamespace(sa=np.array([0.1, 0.2])))
        monkeypatch.setattr("seiswave.core.generator.WaveGenerator.fit_error", lambda sa, target: {"mean_error": 0.01})
        w = MultiTrialGeneratorWorker(np.array([0.1]), np.array([0.1]), n_trials=2)
        progress = []
        w.signals.progress.connect(lambda p, m: progress.append((p, m)))
        result = w.execute()
        assert "best" in result
        assert len(result["all_results"]) == 2
