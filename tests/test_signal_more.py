"""
EQSignal 边缘方法测试

覆盖：batch_load, save_txt, save_at2, save_csv, filter 分支, auto_trim 边界。
"""

import numpy as np
import pytest
from types import SimpleNamespace

from seiswave.core import EQSignal


def _make_sig(acc=None, dt=0.02, n=128, name="test"):
    if acc is None:
        t = np.arange(n) * dt
        acc = np.sin(2 * np.pi * 2.0 * t) * 0.1
    return EQSignal(acc, dt, name=name)


class TestIOHelpers:
    def test_batch_load_delegates_to_fileio(self, monkeypatch):
        rec1 = SimpleNamespace(acc=np.array([1.0, 2.0]), dt=0.02, name="r1")
        rec2 = SimpleNamespace(acc=np.array([3.0, 4.0]), dt=0.02, name="r2")
        monkeypatch.setattr(
            "seiswave.core.io.FileIO.batch_load",
            lambda d, p: [rec1, rec2],
        )
        signals = EQSignal.batch_load("/tmp/fake", "*.AT2")
        assert len(signals) == 2
        assert signals[0].name == "r1"
        assert signals[1].name == "r2"

    def test_save_txt_delegates_to_fileio(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(
            "seiswave.core.io.FileIO.write_txt",
            lambda path, acc, dt, two_col=False: calls.append((path, len(acc), two_col)),
        )
        sig = _make_sig(n=64)
        sig.save_txt(str(tmp_path / "out.txt"), two_col=True)
        assert calls == [(str(tmp_path / "out.txt"), 64, True)]

    def test_save_at2_delegates_to_fileio(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(
            "seiswave.core.io.FileIO.write_at2",
            lambda path, acc, dt, metadata=None: calls.append((path, len(acc), metadata)),
        )
        sig = _make_sig(n=64)
        sig.save_at2(str(tmp_path / "out.AT2"), metadata={"name": "x"})
        assert calls[0][2] == {"name": "x"}

    def test_save_csv_delegates_to_fileio(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(
            "seiswave.core.io.FileIO.write_csv",
            lambda path, **cols: calls.append((path, list(cols.keys()))),
        )
        sig = _make_sig(n=64)
        sig.save_csv(str(tmp_path / "out.csv"))
        assert calls[0][1] == ["time", "acc", "vel", "disp"]


class TestFilterBranches:
    def test_lowpass_and_highpass_filter(self, monkeypatch):
        from seiswave.core.filter import Filter

        calls = []
        def mock_butter(acc, dt, ftype, order, freqs):
            calls.append((ftype, freqs))
            return acc * 0.9

        monkeypatch.setattr(Filter, "butterworth", staticmethod(mock_butter))
        sig = _make_sig(n=256)
        sig.filter(ftype="lowpass", f1=0.1, f2=25.0)
        assert calls[-1] == ("lowpass", 25.0)

        sig2 = _make_sig(n=256)
        sig2.filter(ftype="highpass", f1=0.1, f2=25.0)
        assert calls[-1] == ("highpass", 0.1)

    def test_unknown_filter_type_raises(self):
        sig = _make_sig(n=64)
        with pytest.raises(ValueError, match="未知的滤波类型"):
            sig.filter(ftype="notch")


class TestAutoTrim:
    def test_auto_trim_on_zero_signal(self):
        sig = EQSignal(np.zeros(100), 0.02, name="zero")
        i1, i2 = sig.auto_trim()
        assert i1 == 0
        assert i2 == 99
        assert len(sig.acc) == 100

    def test_auto_trim_actually_trims(self):
        acc = np.zeros(200)
        acc[50:150] = 1.0  # 脉冲在中间
        sig = EQSignal(acc, 0.02, name="pulse")
        i1, i2 = sig.auto_trim()
        assert i1 < i2
        assert i2 < 199
        assert len(sig.acc) == i2 - i1 + 1


class TestResample:
    def test_resample_changes_dt_and_length(self):
        sig = _make_sig(dt=0.02, n=100)
        old_duration = sig.duration
        sig.resample(new_dt=0.01)
        assert sig.dt == 0.01
        assert abs(sig.duration - old_duration) < 0.1
        assert len(sig.acc) > 100

    def test_resample_larger_dt(self):
        sig = _make_sig(dt=0.02, n=100)
        sig.resample(new_dt=0.04)
        assert sig.dt == 0.04
        assert len(sig.acc) < 100


class TestNormalizeAndScale:
    def test_normalize_sets_pga_to_one(self):
        sig = _make_sig(n=64)
        old_pga = sig.pga
        sig.normalize()
        assert sig.pga == pytest.approx(1.0)
        assert np.max(np.abs(sig.acc)) == pytest.approx(1.0)

    def test_scale_multiplies(self):
        sig = _make_sig(n=64)
        old_max = np.max(np.abs(sig.acc))
        sig.scale(2.5)
        assert np.max(np.abs(sig.acc)) == pytest.approx(old_max * 2.5)

    def test_scale_by_zero_clears(self):
        sig = _make_sig(n=64)
        sig.scale(0.0)
        assert np.all(sig.acc == 0)
