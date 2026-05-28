import os
import tempfile
import warnings
import numpy as np
import pytest

from seiswave.core.io import FileIO, EQRecord


class TestIOReadVariants:
    def _make_at2(self, content, suffix=".AT2"):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    def test_read_at2_header2_two_parts(self):
        content = (
            "Header1\n"
            "EventA,StationB\n"
            "ACCEL\n"
            "NPTS= 5, DT= 0.0200 SEC\n"
            "0.1 0.2 0.3 0.4 0.5\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert rec.metadata['event'] == "EventA"
            assert rec.metadata['station'] == "StationB"
            assert rec.metadata['date'] == ""
            assert len(rec.acc) == 5
            assert rec.dt == 0.02
        finally:
            os.unlink(path)

    def test_read_at2_header2_three_parts(self):
        content = (
            "Header1\n"
            "EventA,DateB,StationC\n"
            "ACCEL\n"
            "NPTS= 5, DT= 0.0200 SEC\n"
            "0.1 0.2 0.3 0.4 0.5\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert rec.metadata['event'] == "EventA"
            assert rec.metadata['date'] == "DateB"
            assert rec.metadata['station'] == "StationC"
            # filename has no RSN_ pattern, so component comes from empty fn_meta
            assert rec.metadata['component'] == ""
        finally:
            os.unlink(path)

    def test_read_at2_header4_numeric_only(self):
        content = (
            "Header1\n"
            "Event,Date,Station,Comp\n"
            "ACCEL\n"
            "5 0.0100\n"
            "0.1 0.2 0.3 0.4 0.5\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert rec.dt == 0.01
            assert len(rec.acc) == 5
        finally:
            os.unlink(path)

    def test_read_at2_header4_format2_fails_fallback_to_format3(self):
        content = (
            "Header1\n"
            "Event,Date,Station,Comp\n"
            "ACCEL\n"
            "NPTS = abc DT = 0.0500\n"
            "0.1 0.2 0.3\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert rec.dt == 0.05
            assert len(rec.acc) == 3
        finally:
            os.unlink(path)

    def test_read_at2_header4_format3_with_equals(self):
        content = (
            "Header1\n"
            "Event,Date,Station,Comp\n"
            "ACCEL\n"
            "NPTS= 3 DT= 0.0800\n"
            "0.1 0.2 0.3\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert rec.dt == 0.08
            assert len(rec.acc) == 3
        finally:
            os.unlink(path)

    def test_read_at2_header4_unparseable_raises(self):
        content = (
            "Header1\n"
            "Event,Date,Station,Comp\n"
            "ACCEL\n"
            "hello world\n"
            "0.1 0.2 0.3\n"
        )
        path = self._make_at2(content)
        try:
            with pytest.raises(ValueError, match="无法从第4行解析"):
                FileIO.read_at2(path)
        finally:
            os.unlink(path)

    def test_read_at2_header4_fallback_parsing(self):
        content = (
            "Header1\n"
            "Event,Date,Station,Comp\n"
            "ACCEL\n"
            "NPTS = 3 DT = 0.0500\n"
            "0.1 0.2 abc 0.3\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert rec.dt == 0.05
            assert len(rec.acc) == 3
        finally:
            os.unlink(path)

    def test_read_at2_trims_extra_data(self):
        content = (
            "Header1\n"
            "Event,Date,Station,Comp\n"
            "ACCEL\n"
            "NPTS= 3, DT= 0.0200 SEC\n"
            "0.1 0.2 0.3 0.4 0.5\n"
        )
        path = self._make_at2(content)
        try:
            rec = FileIO.read_at2(path)
            assert len(rec.acc) == 3
        finally:
            os.unlink(path)

    def test_read_txt_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            FileIO.read_txt("/nonexistent/file.txt")

    def test_read_txt_1d_requires_dt(self, tmp_path):
        path = tmp_path / "a.txt"
        np.savetxt(path, [0.1, 0.2, 0.3])
        with pytest.raises(ValueError, match="必须指定 dt"):
            FileIO.read_txt(str(path))

    def test_read_txt_2d_one_col_requires_dt(self, tmp_path):
        path = tmp_path / "a.txt"
        np.savetxt(path, np.column_stack([0.1, 0.2, 0.3]))
        with pytest.raises(ValueError, match="必须指定 dt"):
            FileIO.read_txt(str(path))

    def test_read_txt_2d_multi_col_single_col_mode(self, tmp_path):
        path = tmp_path / "a.txt"
        np.savetxt(path, np.column_stack([[0.1, 0.2], [0.3, 0.4]]))
        rec = FileIO.read_txt(str(path), dt=0.02, single_col=True)
        assert np.allclose(rec.acc, [0.1, 0.2])
        assert rec.dt == 0.02

    def test_read_txt_2d_two_col_infers_dt(self, tmp_path):
        path = tmp_path / "a.txt"
        np.savetxt(path, [[0.0, 0.1], [0.02, 0.2], [0.04, 0.3]])
        rec = FileIO.read_txt(str(path), single_col=False)
        assert rec.dt == 0.02
        assert np.allclose(rec.acc, [0.1, 0.2, 0.3])

    def test_read_txt_bad_dimension_raises(self, tmp_path, monkeypatch):
        path = tmp_path / "a.txt"
        np.savetxt(path, [[0.1, 0.2], [0.3, 0.4]])
        # mock np.loadtxt to return 3D array
        original_loadtxt = np.loadtxt
        def fake_loadtxt(*a, **k):
            arr = original_loadtxt(*a, **k)
            return arr.reshape(1, *arr.shape)
        monkeypatch.setattr(np, "loadtxt", fake_loadtxt)
        with pytest.raises(ValueError, match="数据维度异常"):
            FileIO.read_txt(str(path))

    def test_batch_load_nonrecursive_case_insensitive_fallback(self, tmp_path):
        d1 = tmp_path / "sub"
        d1.mkdir()
        f1 = d1 / "a.At2"
        f1.write_text(
            "H1\nE,D,S,C\nA\nNPTS= 2, DT= 0.0100 SEC\n0.1 0.2\n"
        )
        # pattern is *.AT2 (uppercase), file is .At2 (mixed case)
        # non-recursive won't find in subdir, so put one in root
        f2 = tmp_path / "b.at2"
        f2.write_text(
            "H1\nE,D,S,C\nA\nNPTS= 2, DT= 0.0200 SEC\n0.1 0.2\n"
        )
        recs = FileIO.batch_load(str(tmp_path), pattern="*.AT2", recursive=False)
        assert len(recs) == 1
        assert recs[0].dt == 0.02

    def test_batch_load_skips_unsupported_and_warns(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("bad content")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            recs = FileIO.batch_load(str(tmp_path), pattern="*.txt")
        assert recs == []
        assert caught

    def test_auto_read_txt_skips_header(self, tmp_path):
        path = tmp_path / "a.txt"
        path.write_text("# comment\n0.0 0.1\n0.02 0.2\n0.04 0.3\n")
        rec = FileIO._auto_read_txt(str(path))
        assert rec.dt == 0.02
        assert np.allclose(rec.acc, [0.1, 0.2, 0.3])

    def test_auto_read_txt_single_col_default_dt(self, tmp_path):
        path = tmp_path / "a.txt"
        np.savetxt(path, [0.1, 0.2, 0.3])
        rec = FileIO._auto_read_txt(str(path))
        assert rec.dt == 0.02
        assert np.allclose(rec.acc, [0.1, 0.2, 0.3])

    def test_auto_read_txt_bad_format_raises(self, tmp_path, monkeypatch):
        path = tmp_path / "a.txt"
        path.write_text("not_a_number\n")
        with pytest.raises(ValueError):
            FileIO._auto_read_txt(str(path))


class TestIOWrite:
    def test_write_at2_with_metadata(self, tmp_path):
        path = str(tmp_path / "out.at2")
        acc = np.array([0.1, 0.2, 0.3])
        FileIO.write_at2(path, acc, dt=0.02, metadata={
            'header1': 'Custom1',
            'header2': 'Custom2',
            'header3': 'Custom3',
        })
        text = open(path).read()
        assert "Custom1" in text
        assert "Custom2" in text
        assert "Custom3" in text
        assert "NPTS=" in text
        assert "DT=" in text
        assert "0.020000" in text

    def test_write_at2_no_metadata_uses_defaults(self, tmp_path):
        path = str(tmp_path / "out.at2")
        acc = np.array([0.1, 0.2])
        FileIO.write_at2(path, acc, dt=0.01)
        text = open(path).read()
        assert "PEER NGA STRONG MOTION DATABASE RECORD" in text
        assert "SeisWave Generated" in text
        assert "ACCELERATION (G)" in text
        assert "NPTS=" in text
        assert "DT=" in text

    def test_write_txt_single_and_two_col(self, tmp_path):
        path1 = str(tmp_path / "out1.txt")
        path2 = str(tmp_path / "out2.txt")
        acc = np.array([0.1, 0.2])
        FileIO.write_txt(path1, acc, dt=0.02, two_col=False)
        FileIO.write_txt(path2, acc, dt=0.02, two_col=True)
        data1 = np.loadtxt(path1)
        data2 = np.loadtxt(path2)
        assert np.allclose(data1, acc)
        assert data2.shape == (2, 2)
        assert np.allclose(data2[:, 1], acc)

    def test_write_csv(self, tmp_path):
        path = str(tmp_path / "out.csv")
        FileIO.write_csv(path, period=[0.1, 0.5], sa=[0.2, 0.3])
        lines = open(path).readlines()
        assert lines[0].strip() == "period,sa"
        assert "1.0000000E-01" in lines[1]
