"""
io.py 单元测试

覆盖：AT2 读写、txt 读写（单列/双列）、CSV 写入、batch_load、错误路径。
使用临时文件真实读写。
"""

import os
import numpy as np
import pytest
import tempfile

from seiswave.core.io import FileIO, EQRecord, parse_peer_filename


class TestParsePeerFilename:
    def test_rsn_event_station(self):
        result = parse_peer_filename("RSN1004_NORTHR_SPV270.AT2")
        assert result['rsn'] == 1004
        assert result['event_tag'] == 'NORTHR'
        assert result['station_tag'] == 'SPV270'

    def test_no_rsn(self):
        result = parse_peer_filename("EVENT_STATION.COMP")
        assert result['rsn'] == 0
        assert result['event_tag'] == 'EVENT'
        assert result['station_tag'] == 'STATION'


class TestReadAT2:
    def test_reads_valid_at2(self, tmp_path):
        path = tmp_path / "RSN1_TEST_STA.AT2"
        lines = [
            "Header line 1\n",
            "Event, Date, Station, Component\n",
            "ACCELERATION (G)\n",
            "NPTS=    10, DT=   0.0100 SEC\n",
        ]
        acc = np.arange(10, dtype=float)
        # 每行5个数据
        for i in range(0, 10, 5):
            chunk = acc[i:i+5]
            line = "".join(f"{v:15.7E}" for v in chunk)
            lines.append(line + "\n")
        path.write_text("".join(lines), encoding="utf-8")

        rec = FileIO.read_at2(str(path))
        assert rec.dt == pytest.approx(0.01)
        assert len(rec.acc) == 10
        assert rec.npts == 10
        assert rec.name == "RSN1_TEST_STA"
        assert rec.metadata['rsn'] == 1

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FileIO.read_at2("/tmp/nonexistent.at2")

    def test_too_few_lines(self, tmp_path):
        path = tmp_path / "bad.at2"
        path.write_text("1\n2\n3\n", encoding="utf-8")
        with pytest.raises(ValueError, match="行数不足"):
            FileIO.read_at2(str(path))

    def test_format2_numbers_only(self, tmp_path):
        path = tmp_path / "RSN2_EVT_STA.AT2"
        lines = [
            "H1\n", "H2\n", "H3\n",
            "10    0.0200\n",
        ]
        acc = np.ones(10, dtype=float)
        for i in range(0, 10, 5):
            chunk = acc[i:i+5]
            line = "".join(f"{v:15.7E}" for v in chunk)
            lines.append(line + "\n")
        path.write_text("".join(lines), encoding="utf-8")

        rec = FileIO.read_at2(str(path))
        assert rec.dt == pytest.approx(0.02)
        assert len(rec.acc) == 10


class TestReadTxt:
    def test_single_column_with_dt(self, tmp_path):
        path = tmp_path / "single.txt"
        data = np.arange(10, dtype=float)
        np.savetxt(path, data, fmt="%.4f")

        rec = FileIO.read_txt(str(path), dt=0.02)
        assert len(rec.acc) == 10
        assert rec.dt == pytest.approx(0.02)

    def test_single_column_no_dt_raises(self, tmp_path):
        path = tmp_path / "single.txt"
        np.savetxt(path, np.arange(5, dtype=float), fmt="%.4f")
        with pytest.raises(ValueError, match="必须指定 dt"):
            FileIO.read_txt(str(path))

    def test_two_column_auto_dt(self, tmp_path):
        path = tmp_path / "double.txt"
        time = np.arange(10) * 0.01
        acc = np.ones(10)
        np.savetxt(path, np.column_stack([time, acc]), fmt="%.4f")

        rec = FileIO.read_txt(str(path), single_col=False)
        assert len(rec.acc) == 10
        assert rec.dt == pytest.approx(0.01)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FileIO.read_txt("/tmp/nonexistent.txt")


class TestWriteAT2:
    def test_roundtrip(self, tmp_path):
        acc = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        path = tmp_path / "out.AT2"
        FileIO.write_at2(str(path), acc, dt=0.02, metadata={"header1": "Test"})

        text = path.read_text(encoding="utf-8")
        assert "Test" in text
        assert "NPTS=" in text
        assert "DT=" in text

        rec = FileIO.read_at2(str(path))
        assert len(rec.acc) == 5
        assert rec.dt == pytest.approx(0.02)


class TestWriteTxt:
    def test_single_column(self, tmp_path):
        acc = np.array([1.0, 2.0, 3.0])
        path = tmp_path / "out.txt"
        FileIO.write_txt(str(path), acc, dt=0.01, two_col=False)
        content = path.read_text(encoding="utf-8")
        assert "dt=0.01" in content
        data = np.loadtxt(path, skiprows=1)
        assert np.allclose(data, acc)

    def test_two_column(self, tmp_path):
        acc = np.array([1.0, 2.0, 3.0])
        path = tmp_path / "out2.txt"
        FileIO.write_txt(str(path), acc, dt=0.01, two_col=True)
        data = np.loadtxt(path, skiprows=2)
        assert data.shape[1] == 2
        assert np.allclose(data[:, 1], acc)


class TestWriteCSV:
    def test_writes_columns(self, tmp_path):
        path = tmp_path / "out.csv"
        t = np.array([0.0, 0.1, 0.2])
        sa = np.array([0.5, 0.6, 0.7])
        FileIO.write_csv(str(path), time=t, sa=sa)

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert lines[0] == "time,sa"
        assert len(lines) == 4  # header + 3 rows


class TestBatchLoad:
    def test_loads_at2_files(self, tmp_path):
        # 创建两个 AT2 文件
        for i in range(2):
            path = tmp_path / f"RSN{i}_EVT_STA.AT2"
            lines = [
                "H1\n", "H2\n", "H3\n",
                f"5    0.0200\n",
            ]
            acc = np.ones(5, dtype=float)
            for j in range(0, 5, 5):
                chunk = acc[j:j+5]
                line = "".join(f"{v:15.7E}" for v in chunk)
                lines.append(line + "\n")
            path.write_text("".join(lines), encoding="utf-8")

        recs = FileIO.batch_load(str(tmp_path), "*.AT2")
        assert len(recs) == 2

    def test_empty_dir(self, tmp_path):
        recs = FileIO.batch_load(str(tmp_path), "*.AT2")
        assert recs == []

    def test_bad_dir(self):
        with pytest.raises(FileNotFoundError):
            FileIO.batch_load("/tmp/nonexistent_dir_xyz")


class TestAutoReadTxt:
    def test_double_column(self, tmp_path):
        path = tmp_path / "auto.txt"
        time = np.arange(10) * 0.02
        acc = np.ones(10)
        np.savetxt(path, np.column_stack([time, acc]), fmt="%.5f")

        rec = FileIO._auto_read_txt(str(path))
        assert len(rec.acc) == 10
        assert rec.dt == pytest.approx(0.02)

    def test_single_column(self, tmp_path):
        path = tmp_path / "auto_single.txt"
        np.savetxt(path, np.ones(10), fmt="%.5f")
        rec = FileIO._auto_read_txt(str(path))
        assert len(rec.acc) == 10
        assert rec.dt == pytest.approx(0.02)  # 默认 dt
