"""Tests for CodeSpectrum: gb51408, from_custom, from_csv."""

import os
import tempfile

import numpy as np
import pytest

from seiswave.core import CodeSpectrum


# ---------------------------------------------------------------------------
# gb51408
# ---------------------------------------------------------------------------

class TestGB51408:
    def test_returns_correct_length(self):
        periods = np.linspace(0.01, 6.0, 200)
        sa = CodeSpectrum.gb51408(periods, 8, 2, "II")
        assert len(sa) == 200

    def test_uses_isolation_spectrum(self):
        """gb51408 should produce a 3-segment (isolation) spectrum, not 4-segment."""
        periods = np.linspace(0.01, 6.0, 600)
        sa_51408 = CodeSpectrum.gb51408(periods, 8, 2, "II")
        # Compare with manual gb50011 isolation call using same adjusted Tg
        params = CodeSpectrum.get_params(8, 2, "II", "rare")
        Tg_iso = params["Tg"] + 0.05
        sa_manual = CodeSpectrum.gb50011(
            periods, Tg_iso, params["alpha_max"], zeta=0.05, isolation=True
        )
        np.testing.assert_allclose(sa_51408, sa_manual)

    def test_tg_shifted_from_gb50011(self):
        """51408 spectrum should differ from plain gb50011 isolation due to Tg shift."""
        periods = np.linspace(0.01, 6.0, 300)
        params = CodeSpectrum.get_params(8, 2, "II", "rare")
        sa_50011 = CodeSpectrum.gb50011(
            periods, params["Tg"], params["alpha_max"], isolation=True
        )
        sa_51408 = CodeSpectrum.gb51408(periods, 8, 2, "II")
        # They should NOT be identical because Tg is shifted
        assert not np.allclose(sa_50011, sa_51408)
    def test_default_level_is_rare(self):
        """Default level should be 'rare'."""
        periods = np.linspace(0.01, 6.0, 100)
        sa_default = CodeSpectrum.gb51408(periods, 8, 2, "II")
        sa_rare = CodeSpectrum.gb51408(periods, 8, 2, "II", level="rare")
        np.testing.assert_allclose(sa_default, sa_rare)

    def test_all_values_non_negative(self):
        periods = np.linspace(0.0, 6.0, 500)
        sa = CodeSpectrum.gb51408(periods, 7, 1, "III", level="frequent")
        assert np.all(sa >= 0)

    def test_invalid_params_raise(self):
        periods = np.linspace(0.01, 6.0, 50)
        with pytest.raises(KeyError):
            CodeSpectrum.gb51408(periods, 5, 1, "II")


# ---------------------------------------------------------------------------
# from_custom
# ---------------------------------------------------------------------------

class TestFromCustom:
    def test_linear_interpolation(self):
        custom_t = np.array([0.0, 0.5, 1.0, 2.0])
        custom_sa = np.array([0.1, 0.5, 0.3, 0.1])
        target = np.array([0.25, 0.75, 1.5])
        result = CodeSpectrum.from_custom(custom_t, custom_sa, target, "linear")
        expected = np.interp(target, custom_t, custom_sa)
        np.testing.assert_allclose(result, expected)

    def test_log_interpolation(self):
        custom_t = np.array([0.1, 1.0, 10.0])
        custom_sa = np.array([1.0, 0.5, 0.1])
        target = np.array([0.5, 5.0])
        result = CodeSpectrum.from_custom(custom_t, custom_sa, target, "log")
        # Log-log interpolation: result should be between neighbors
        assert 0.5 < result[0] < 1.0
        assert 0.1 < result[1] < 0.5

    def test_exact_points_preserved(self):
        custom_t = np.array([0.1, 0.5, 1.0, 2.0])
        custom_sa = np.array([0.2, 0.8, 0.4, 0.15])
        result = CodeSpectrum.from_custom(custom_t, custom_sa, custom_t, "linear")
        np.testing.assert_allclose(result, custom_sa)

    def test_log_exact_points_preserved(self):
        custom_t = np.array([0.1, 0.5, 1.0, 2.0])
        custom_sa = np.array([0.2, 0.8, 0.4, 0.15])
        result = CodeSpectrum.from_custom(custom_t, custom_sa, custom_t, "log")
        np.testing.assert_allclose(result, custom_sa, rtol=1e-10)

    def test_invalid_mode_raises(self):
        t = np.array([0.1, 1.0])
        sa = np.array([0.5, 0.3])
        with pytest.raises(ValueError, match="不支持的插值方式"):
            CodeSpectrum.from_custom(t, sa, t, "cubic")


# ---------------------------------------------------------------------------
# from_csv
# ---------------------------------------------------------------------------

class TestFromCSV:
    def _write_tmp(self, content, suffix=".csv"):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        f.write(content)
        f.close()
        return f.name

    def test_comma_separated(self):
        path = self._write_tmp("0.1,0.5\n0.5,0.8\n1.0,0.3\n")
        try:
            t, sa = CodeSpectrum.from_csv(path)
            np.testing.assert_array_equal(t, [0.1, 0.5, 1.0])
            np.testing.assert_array_equal(sa, [0.5, 0.8, 0.3])
        finally:
            os.unlink(path)

    def test_space_separated(self):
        path = self._write_tmp("0.1 0.5\n0.5 0.8\n1.0 0.3\n")
        try:
            t, sa = CodeSpectrum.from_csv(path)
            np.testing.assert_array_equal(t, [0.1, 0.5, 1.0])
            np.testing.assert_array_equal(sa, [0.5, 0.8, 0.3])
        finally:
            os.unlink(path)

    def test_tab_separated(self):
        path = self._write_tmp("0.1\t0.5\n0.5\t0.8\n1.0\t0.3\n")
        try:
            t, sa = CodeSpectrum.from_csv(path)
            np.testing.assert_array_equal(t, [0.1, 0.5, 1.0])
            np.testing.assert_array_equal(sa, [0.5, 0.8, 0.3])
        finally:
            os.unlink(path)

    def test_skip_comments_and_blanks(self):
        content = "# Header comment\n\n0.1,0.5\n# another comment\n\n0.5,0.8\n"
        path = self._write_tmp(content)
        try:
            t, sa = CodeSpectrum.from_csv(path)
            assert len(t) == 2
            np.testing.assert_array_equal(t, [0.1, 0.5])
            np.testing.assert_array_equal(sa, [0.5, 0.8])
        finally:
            os.unlink(path)

    def test_returns_tuple_of_arrays(self):
        path = self._write_tmp("0.1,0.5\n1.0,0.3\n")
        try:
            result = CodeSpectrum.from_csv(path)
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert isinstance(result[0], np.ndarray)
            assert isinstance(result[1], np.ndarray)
        finally:
            os.unlink(path)

    def test_txt_extension(self):
        path = self._write_tmp("0.1 0.5\n1.0 0.3\n", suffix=".txt")
        try:
            t, sa = CodeSpectrum.from_csv(path)
            assert len(t) == 2
        finally:
            os.unlink(path)
