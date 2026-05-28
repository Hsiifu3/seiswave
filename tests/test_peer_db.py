"""
peer_db.py 单元测试

覆盖：PeerRecord、PeerDatabase 初始化、索引构建、header 解析、
filter、水平/竖向筛选、Arias 持时、索引持久化、反应谱缓存。
使用 tmp_path 创建真实 AT2 文件，避免外部依赖。
"""

import numpy as np
import os
import pytest


@pytest.fixture
def fake_at2(tmp_path):
    """创建一个格式合规的临时 AT2 文件"""
    def _make(name, npts=10, dt=0.01, header2="EventA, 2020/01/01, STA1, COMP1",
              acc_values=None):
        path = tmp_path / name
        lines = [
            "Header1\n",
            f"{header2}\n",
            "ACCELERATION (G)\n",
            f"NPTS= {npts:>8d}, DT= {dt:>10.6f} SEC\n",
        ]
        acc = acc_values if acc_values is not None else np.ones(npts, dtype=float)
        for i in range(0, npts, 5):
            chunk = acc[i:i+5]
            line = "".join(f"{v:15.7E}" for v in chunk)
            lines.append(line + "\n")
        path.write_text("".join(lines), encoding="utf-8")
        return str(path)
    return _make


class TestPeerRecord:
    def test_to_dict_excludes_waveform(self):
        from seiswave.core.peer_db import PeerRecord

        rec = PeerRecord(rsn=1, event="EQ1", station="STA", pga=0.5,
                         acc=np.array([1.0, 2.0]), sa=np.array([3.0, 4.0]))
        d = rec.to_dict()
        assert "acc" not in d
        assert "sa" not in d
        assert d["rsn"] == 1
        assert d["pga"] == 0.5


class TestPeerDatabaseInit:
    def test_default_data_dir(self):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase()
        assert os.path.isabs(db.data_dir)
        assert "data" in db.data_dir

    def test_custom_data_dir(self, tmp_path):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase(str(tmp_path))
        assert db.data_dir == str(tmp_path)


class TestBuildIndex:
    def test_scans_at2_files(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1001_EVT_STA.AT2", npts=10, dt=0.02,
                 header2="Northridge, 1994/01/17, STA, COMP1")
        fake_at2("RSN1002_EVT_STB_UP.AT2", npts=20, dt=0.01,
                 header2="LomaPrieta, 1989/10/17, STB, UP")

        db = PeerDatabase(str(tmp_path))
        count = db.build_index()
        assert count == 2
        assert len(db.records) == 2

    def test_progress_callback(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        for i in range(60):
            fake_at2(f"RSN{i:04d}_EVT_STA.AT2", npts=5, dt=0.02,
                     header2=f"Event{i}, 2020/01/01, STA, COMP")

        db = PeerDatabase(str(tmp_path))
        progress = []

        def cb(current, total):
            progress.append((current, total))

        db.build_index(progress_cb=cb)
        assert len(progress) > 0
        assert progress[-1] == (60, 60)

    def test_skips_bad_files(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1001_EVT_STA.AT2", npts=10, dt=0.02)
        (tmp_path / "bad.AT2").write_text("too\nshort\n", encoding="utf-8")

        db = PeerDatabase(str(tmp_path))
        count = db.build_index()
        assert count == 1

    def test_empty_dir(self, tmp_path):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase(str(tmp_path))
        assert db.build_index() == 0


class TestParseHeader:
    def test_parses_rsn_from_filename(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN2048_EVT_STA.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].rsn == 2048

    def test_vertical_detection_up(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA_UP.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].direction == 'V'

    def test_vertical_detection_dwn(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA_DWN.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].direction == 'V'

    def test_vertical_detection_dash(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA-UP.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].direction == 'V'

    def test_horizontal_by_default(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA_H1.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].direction == 'H'

    def test_header2_two_parts(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=10, dt=0.02,
                 header2="EventOnly, StationOnly")
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].event == "EventOnly"
        assert db.records[0].station == "StationOnly"

    def test_dt_fallback_numeric_format(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        # 创建一个没有 NPTS= / DT= 字样、只有纯数字的文件
        path = tmp_path / "RSN1_EVT_STA.AT2"
        lines = [
            "H1\n", "H2\n", "H3\n",
            "10    0.0300\n",
        ]
        acc = np.ones(10, dtype=float)
        for i in range(0, 10, 5):
            chunk = acc[i:i+5]
            line = "".join(f"{v:15.7E}" for v in chunk)
            lines.append(line + "\n")
        path.write_text("".join(lines), encoding="utf-8")

        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert db.records[0].dt == pytest.approx(0.03)


class TestAriasDuration:
    def test_empty_array(self):
        from seiswave.core.peer_db import PeerDatabase

        assert PeerDatabase._arias_duration(np.array([]), 0.01) == 0.0

    def test_single_element(self):
        from seiswave.core.peer_db import PeerDatabase

        assert PeerDatabase._arias_duration(np.array([1.0]), 0.01) == 0.0

    def test_normal_acc(self):
        from seiswave.core.peer_db import PeerDatabase

        acc = np.ones(100)
        dt = 0.01
        dur = PeerDatabase._arias_duration(acc, dt)
        # 对于 uniform acc，arias 强度线性累积，5%-95% 约为 90% 区间
        assert dur > 0.8 * 100 * dt
        assert dur < 100 * dt

    def test_zero_total_ia(self):
        from seiswave.core.peer_db import PeerDatabase

        assert PeerDatabase._arias_duration(np.zeros(10), 0.01) == 0.0


class TestGetHorizontalVertical:
    def test_filter_direction(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        fake_at2("RSN2_EVT_STA_UP.AT2", npts=5, dt=0.02)

        db = PeerDatabase(str(tmp_path))
        db.build_index()
        h = db.get_horizontal()
        v = db.get_vertical()
        assert len(h) == 1 and h[0].rsn == 1
        assert len(v) == 1 and v[0].rsn == 2


class TestFilter:
    def test_filter_rsn(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_A.AT2", npts=5, dt=0.02)
        fake_at2("RSN2_EVT_B.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert len(db.filter(rsn=1)) == 1
        assert db.filter(rsn=1)[0].rsn == 1

    def test_filter_event(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_Northridge_STA.AT2", npts=5, dt=0.02,
                 header2="Northridge, 2020/01/01, STA, COMP")
        fake_at2("RSN2_LomaPrieta_STA.AT2", npts=5, dt=0.02,
                 header2="LomaPrieta, 2020/01/01, STA, COMP")
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert len(db.filter(event="north")) == 1

    def test_filter_station(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        fake_at2("RSN2_EVT_STB.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert len(db.filter(station="sta")) == 2  # 大小写不敏感

    def test_filter_pga_range(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02,
                 acc_values=np.array([0.1, 0.2, 0.3, 0.4, 0.5]))
        fake_at2("RSN2_EVT_STA.AT2", npts=5, dt=0.02,
                 acc_values=np.array([0.01, 0.02, 0.03, 0.04, 0.05]))
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        high = db.filter(pga_range=(0.2, 1.0))
        assert len(high) == 1 and high[0].rsn == 1

    def test_filter_duration_range(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=100, dt=0.02)
        fake_at2("RSN2_EVT_STA.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        long_dur = db.filter(duration_range=(0.5, 10.0))
        assert len(long_dur) == 1
        assert long_dur[0].npts == 100

    def test_filter_direction(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        fake_at2("RSN2_EVT_STA_UP.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert len(db.filter(direction='H')) == 1
        assert len(db.filter(direction='V')) == 1

    def test_filter_chained(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_Northridge_STA.AT2", npts=5, dt=0.02,
                 header2="Northridge, 2020/01/01, STA, COMP")
        fake_at2("RSN2_LomaPrieta_STA.AT2", npts=5, dt=0.02,
                 header2="LomaPrieta, 2020/01/01, STA, COMP")
        fake_at2("RSN3_Northridge_STB_UP.AT2", npts=5, dt=0.02,
                 header2="Northridge, 2020/01/01, STB, UP")
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        result = db.filter(event="north", direction='H')
        assert len(result) == 1 and result[0].rsn == 1


class TestIndexPersistence:
    def test_save_and_load_index(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        db.save_index()

        db2 = PeerDatabase(str(tmp_path))
        ok = db2.load_index()
        assert ok is True
        assert len(db2.records) == 1
        assert db2.records[0].rsn == 1

    def test_load_index_no_file(self, tmp_path):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase(str(tmp_path))
        assert db.load_index() is False


class TestSpectraCache:
    def test_precompute_and_save(self, tmp_path, fake_at2, monkeypatch):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=10, dt=0.02,
                 acc_values=np.ones(10, dtype=float))
        db = PeerDatabase(str(tmp_path))
        db.build_index()

        # mock spectrum 计算，避免 Fortran 依赖
        monkeypatch.setattr("seiswave.core.fortran_bridge.HAS_FORTRAN", True)
        monkeypatch.setattr("seiswave.core.fortran_bridge.spectrum_mixed",
                            lambda acc, dt, zeta, periods: (np.full(len(periods), 0.5), np.arange(len(periods))))

        periods = np.array([0.1, 0.5, 1.0])
        db.precompute_spectra(periods=periods, zeta=0.05)
        assert db.records[0].sa is not None
        assert len(db.records[0].sa) == 3
        assert np.allclose(db.records[0].sa, 0.5)

    def test_load_spectra_cache(self, tmp_path, fake_at2, monkeypatch):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=10, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()

        monkeypatch.setattr("seiswave.core.fortran_bridge.HAS_FORTRAN", True)
        monkeypatch.setattr("seiswave.core.fortran_bridge.spectrum_mixed",
                            lambda acc, dt, zeta, periods: (np.full(len(periods), 0.5), np.arange(len(periods))))

        periods = np.array([0.1, 0.5])
        db.precompute_spectra(periods=periods, zeta=0.05)

        db2 = PeerDatabase(str(tmp_path))
        db2.records = db.records[:]  # 共享索引
        ok = db2.load_spectra_cache(zeta=0.05)
        assert ok is True
        assert db2.records[0].sa is not None
        assert len(db2.records[0].sa) == 2

    def test_load_spectra_cache_no_file(self, tmp_path):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase(str(tmp_path))
        assert db.load_spectra_cache() is False


class TestMagicMethods:
    def test_len(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        assert len(db) == 1

    def test_repr(self, tmp_path, fake_at2):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        fake_at2("RSN2_EVT_STA_UP.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        r = repr(db)
        assert "2 records" in r
        assert "1H + 1V" in r


class TestLoadWaveform:
    def test_lazy_load(self, tmp_path, fake_at2, monkeypatch):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        rec = db.records[0]
        assert rec.acc is None  # 延迟加载，build_index 后应为 None

    def test_load_waveform_returns_acc(self, tmp_path, fake_at2, monkeypatch):
        from seiswave.core.peer_db import PeerDatabase
        from types import SimpleNamespace

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02,
                 acc_values=np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        rec = db.records[0]

        # mock FileIO.read_at2
        monkeypatch.setattr("seiswave.core.io.FileIO.read_at2",
                            staticmethod(lambda path: SimpleNamespace(acc=np.array([10.0, 20.0, 30.0, 40.0, 50.0]))))

        acc = db.load_waveform(rec)
        assert np.array_equal(acc, np.array([10.0, 20.0, 30.0, 40.0, 50.0]))
        assert rec.acc is not None

    def test_load_waveform_uses_cache(self, tmp_path, fake_at2, monkeypatch):
        from seiswave.core.peer_db import PeerDatabase

        fake_at2("RSN1_EVT_STA.AT2", npts=5, dt=0.02)
        db = PeerDatabase(str(tmp_path))
        db.build_index()
        rec = db.records[0]
        rec.acc = np.array([99.0])

        calls = []
        monkeypatch.setattr("seiswave.core.io.FileIO.read_at2",
                            staticmethod(lambda path: (calls.append(path), None)[1]))

        acc = db.load_waveform(rec)
        assert np.array_equal(acc, np.array([99.0]))
        assert len(calls) == 0  # 已缓存，不重新读取
