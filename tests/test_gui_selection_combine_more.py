import numpy as np
import pytest
from types import SimpleNamespace

from seiswave.gui.workers import (
    CombinerWorker,
    PeerIndexWorker,
    PeerLoadWorker,
    PeerSelectWorker,
    SelectorWorker,
    SpectraPrecomputeWorker,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_sig(name="sig", dt=0.02):
    from seiswave.core import EQSignal

    acc = np.sin(np.linspace(0, 2, 128)) * 0.1
    return EQSignal(acc, dt, name=name)
class TestMoreWorkers:
    def test_peer_load_worker_builds_index_and_precomputes(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1, 2, 3]
                self.precompute_calls = []
            def load_index(self):
                return False
            def build_index(self):
                self.built = True
            def __len__(self):
                return len(self.records)
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                self.precompute_calls.append((periods, zeta))
                progress_cb(2, 4)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerLoadWorker("/tmp/fake")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()

        assert isinstance(db, FakeDB)
        assert getattr(db, "built", False) is True
        assert db.precompute_calls
        assert progress[0] == (10, "检查索引缓存...")
        assert progress[-1] == (100, "加载完成")

    def test_peer_index_worker_uses_cache_shortcut(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1, 2]
            def load_index(self):
                return True
            def __len__(self):
                return len(self.records)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerIndexWorker("/tmp/fake")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()

        assert isinstance(db, FakeDB)
        assert progress == [(5, "检查索引缓存..."), (100, "从缓存加载 2 条记录")]

    def test_spectra_precompute_worker_uses_cache_when_available(self):
        records = [SimpleNamespace(sa=np.array([1.0])), SimpleNamespace(sa=None)]
        db = SimpleNamespace(records=records, load_spectra_cache=lambda z: True)
        worker = SpectraPrecomputeWorker(db)
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        result = worker.execute()

        assert result is db
        assert progress == [(5, "检查反应谱缓存..."), (100, "从缓存加载 1 条反应谱")]

    def test_peer_select_worker_delegates_to_wave_selector(self, monkeypatch):
        result = ["r1", "r2"]

        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(2, 5)
                return result

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = PeerSelectWorker(config="cfg", database="db")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        out = worker.execute()

        assert out == result
        assert progress == [(40, "筛选 2/5")]

    def test_selector_worker_emits_completion_progress(self, monkeypatch):
        result = [1, 2, 3]

        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 4)
                return result

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = SelectorWorker(config="cfg", database="db")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        out = worker.execute()

        assert out == result
        assert progress[-1] == (100, "选波完成: 3 条")

    def test_peer_load_worker_raises_on_cancel_during_precompute(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1]
            def load_index(self):
                return True
            def __len__(self):
                return len(self.records)
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                progress_cb(1, 2)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerLoadWorker("/tmp/fake")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_spectra_precompute_worker_raises_on_cancel(self):
        class FakeDB:
            def __init__(self):
                self.records = []
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                progress_cb(1, 2)

        worker = SpectraPrecomputeWorker(FakeDB())
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_selector_worker_raises_on_cancel_from_progress_callback(self, monkeypatch):
        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 3)
                return []

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = SelectorWorker(config="cfg", database="db")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_combiner_worker_stops_when_cancelled_before_loop(self, monkeypatch):
        class FakeCombiner:
            def __init__(self, output_dir=None):
                self.output_dir = output_dir
            def add_natural(self, r, db):
                raise AssertionError("should not reach add_natural")

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        worker = CombinerWorker(
            results=["r1"],
            database="db",
            generated_waves=[],
            output_dir="/tmp/out",
        )
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_combiner_worker_adds_waves_and_generates_report(self, monkeypatch):
        class FakeCombiner:
            def __init__(self, output_dir=None):
                self.output_dir = output_dir
                self.natural = []
                self.artificial = []
            def add_natural(self, r, db):
                self.natural.append((r, db))
            def add_artificial(self, h1=None, name=None, index=None):
                self.artificial.append((h1, name, index))
            def export(self, fmt='at2'):
                self.fmt = fmt
            def generate_html_report(self, sa, periods):
                return "/tmp/fake_report.html"

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        sig = _make_sig("art")
        worker = CombinerWorker(
            results=["r1"],
            database="db",
            generated_waves=[sig],
            output_dir="/tmp/out",
            fmt="txt",
            target_sa=np.array([0.2, 0.3]),
            periods=np.array([0.1, 0.5]),
        )
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        out = worker.execute()

        assert out["output_dir"] == "/tmp/out"
        assert out["report_path"] == "/tmp/fake_report.html"
        assert out["combiner"].natural == [("r1", "db")]
        assert out["combiner"].artificial[0][2] == 0
        assert progress[-1] == (100, "组合输出完成")
