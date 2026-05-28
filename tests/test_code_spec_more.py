import os
import tempfile

import numpy as np
import pytest

from seiswave.core import CodeSpectrum


class TestEurocode8:
    def test_type1_spectrum_covers_all_segments(self):
        periods = np.array([0.0, 0.10, 0.30, 1.0, 3.0])
        se = CodeSpectrum.eurocode8(periods, ag=0.3, soil_type="C", spectrum_type=1, zeta=0.05)

        assert len(se) == len(periods)
        assert np.all(se >= 0)
        assert se[1] < se[2]  # rising to plateau
        assert se[2] > se[3] > se[4]  # decay branches

    def test_type2_and_high_damping_floor_eta(self):
        periods = np.array([0.0, 0.02, 0.10, 0.40, 2.0])
        se = CodeSpectrum.eurocode8(periods, ag=0.25, soil_type="D", spectrum_type=2, zeta=0.50)

        assert np.all(se >= 0)
        assert se[2] <= 0.25 * 1.8 * 2.5  # eta floor should cap reduction
        assert se[3] > se[4]

    def test_invalid_type_and_soil_raise(self):
        periods = np.array([0.1, 0.5])
        with pytest.raises(ValueError, match="无效的谱类型"):
            CodeSpectrum.eurocode8(periods, ag=0.3, spectrum_type=3)
        with pytest.raises(ValueError, match="无效的场地类别"):
            CodeSpectrum.eurocode8(periods, ag=0.3, soil_type="Z", spectrum_type=1)


class TestASCE7:
    def test_asce7_covers_four_segments(self):
        sds = 1.0
        sd1 = 0.6
        tl = 4.0
        periods = np.array([0.0, 0.05, 0.2, 1.0, 6.0])
        sa = CodeSpectrum.asce7(periods, sds=sds, sd1=sd1, tl=tl)

        assert np.all(sa >= 0)
        assert sa[0] == pytest.approx(0.4)
        assert sa[1] > sa[0]
        assert sa[2] == pytest.approx(sds)
        assert sa[3] == pytest.approx(sd1 / periods[3])
        assert sa[4] == pytest.approx(sd1 * tl / periods[4] ** 2)


class TestFromCSVMore:
    def _write_tmp(self, content, suffix=".csv"):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    def test_utf8_sig_and_invalid_short_lines_are_ignored(self):
        content = "\ufeff# comment\n0.1\n0.2,0.5\n0.4\t0.9\n"
        path = self._write_tmp(content)
        try:
            periods, sa = CodeSpectrum.from_csv(path)
            np.testing.assert_array_equal(periods, [0.2, 0.4])
            np.testing.assert_array_equal(sa, [0.5, 0.9])
        finally:
            os.unlink(path)
