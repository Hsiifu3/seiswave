"""SignalRecord / SignalPool 单元测试。"""

import numpy as np
import pytest

from seiswave.core.signal import EQSignal
from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.spectrum import Spectra


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class TestSignalRecord:
    def test_vel_and_disp_match_eqsignal(self):
        acc = np.array([0.0, 0.2, -0.1, 0.05, 0.0], dtype=np.float64)
        dt = 0.02

        rec = SignalRecord(acc=acc, dt=dt, name="RSN1", kind="natural")
        sig = EQSignal(acc, dt, name="RSN1")
        sig.a2vd()

        vel1 = rec.vel()
        disp1 = rec.disp()

        np.testing.assert_allclose(vel1, sig.vel)
        np.testing.assert_allclose(disp1, sig.disp)
        assert rec.vel() is vel1
        assert rec.disp() is disp1

    def test_spectrum_is_cached_by_periods_and_zeta(self, monkeypatch):
        calls = []

        def fake_compute(acc, dt, periods, zeta=0.05, method="mixed",
                         parallel=False, max_workers=None):
            sp = Spectra(periods, zeta)
            sp.sa = np.full(len(periods), len(calls) + 1.0)
            sp.sv = np.zeros(len(periods))
            sp.sd = np.zeros(len(periods))
            sp.se = np.zeros(len(periods))
            calls.append((acc.copy(), dt, periods.copy(), zeta))
            return sp

        monkeypatch.setattr(
            "seiswave.core.signal_pool.Spectra.compute",
            fake_compute,
        )

        rec = SignalRecord(acc=np.array([0.0, 0.1, -0.1]), dt=0.02,
                           name="cache", kind="natural")
        periods = np.array([0.1, 0.5, 1.0])

        sp1 = rec.spectrum(periods, zeta=0.05)
        sp2 = rec.spectrum(periods.copy(), zeta=0.05)
        sp3 = rec.spectrum(periods, zeta=0.10)

        assert sp1 is sp2
        assert sp3 is not sp1
        assert len(calls) == 2
        np.testing.assert_allclose(calls[0][2], periods)


class TestSignalPool:
    def test_add_remove_and_selection_emit_signals(self, qapp):
        pool = SignalPool()
        changed = {"signals": 0, "selection": 0}

        pool.signals_changed.connect(
            lambda: changed.__setitem__("signals", changed["signals"] + 1)
        )
        pool.selection_changed.connect(
            lambda: changed.__setitem__("selection", changed["selection"] + 1)
        )

        rec = SignalRecord(
            acc=np.array([0.0, 0.1, -0.1, 0.0]),
            dt=0.02,
            name="RSN2",
            kind="natural",
        )
        pool.add(rec)
        pool.set_selection([rec.id, rec.id, "missing"])
        selected = pool.selection()
        pool.remove(rec.id)

        assert changed["signals"] == 2
        assert changed["selection"] == 2
        assert [item.id for item in selected] == [rec.id]
        assert pool.selection() == []
        assert pool.all() == []

    def test_derive_tracks_parent_and_preserves_original(self, qapp):
        acc = np.array([0.0, 0.1, -0.05, 0.0], dtype=np.float64)
        pool = SignalPool()
        parent = SignalRecord(
            acc=acc,
            dt=0.01,
            name="原始波",
            kind="natural",
            meta={"rsn": 1234},
        )
        pool.add(parent)

        derived_acc = acc * 1.5
        child = pool.derive(parent, derived_acc, "基线校正后")

        assert child.parent_id == parent.id
        assert child.dt == parent.dt
        assert child.kind == "processed"
        assert child.name.endswith("基线校正后")
        assert child.meta == parent.meta
        assert child.meta is not parent.meta
        np.testing.assert_allclose(child.acc, derived_acc)
        np.testing.assert_allclose(parent.acc, acc)
        assert pool.get(child.id) is child
