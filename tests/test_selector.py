"""
WaveSelector 单元测试

覆盖：SelectionConfig 创建、_optimal_scale、隔震双周期匹配、
select() 合成数据流程、mean_spectrum、envelope_spectrum。
不依赖真实 PEER 数据。
"""

import numpy as np
import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Optional

from seiswave.core.selector import SelectionConfig, SelectionResult, WaveSelector
from seiswave.core.peer_db import PeerRecord


# ---------------------------------------------------------------------------
# helpers: 构造合成数据库
# ---------------------------------------------------------------------------

def _make_periods(n=50):
    return np.linspace(0.1, 6.0, n)


def _make_target(periods):
    """简单平坦目标谱 0.5g"""
    return np.ones(len(periods)) * 0.5


def _make_record(rsn, sa, eff_duration=30.0, direction="H"):
    return PeerRecord(
        rsn=rsn, event=f"EQ{rsn}", station=f"STA{rsn}",
        component=f"C{rsn}", direction=direction,
        dt=0.01, npts=3000, pga=0.3,
        duration=30.0, eff_duration=eff_duration,
        sa=sa,
    )


def _make_database(records, spectra_periods):
    """用 MagicMock 构造 PeerDatabase"""
    db = MagicMock()
    db.spectra_periods = spectra_periods
    db.get_horizontal.return_value = [r for r in records if r.direction == "H"]
    return db


# ---------------------------------------------------------------------------
# Test: SelectionConfig 创建
# ---------------------------------------------------------------------------

class TestSelectionConfig:
    def test_default_creation(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0, 0.5, 0.3],
        )
        assert cfg.n_select == 5
        assert cfg.spectral_tol == 0.30
        assert cfg.isolation is False
        assert cfg.T_isolation == []

    def test_isolation_params(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0, 0.5],
            isolation=True,
            T_isolation=[3.0, 4.0],
        )
        assert cfg.isolation is True
        assert cfg.T_isolation == [3.0, 4.0]

    def test_wave_selector_init_indices(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0, 2.0],
            isolation=True,
            T_isolation=[3.0, 5.0],
        )
        ws = WaveSelector(cfg)
        assert len(ws._T_indices) == 2
        assert len(ws._T_iso_indices) == 2
        # 验证索引指向正确的周期
        assert abs(periods[ws._T_indices[0]] - 1.0) < 0.15
        assert abs(periods[ws._T_iso_indices[0]] - 3.0) < 0.15

    def test_no_isolation_empty_indices(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0],
        )
        ws = WaveSelector(cfg)
        assert len(ws._T_iso_indices) == 0


# ---------------------------------------------------------------------------
# Test: _optimal_scale
# ---------------------------------------------------------------------------

class TestOptimalScale:
    def test_half_spectrum_scale_near_two(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0, 0.5, 0.3],
        )
        ws = WaveSelector(cfg)
        rec_sa = target * 0.5  # 记录谱是目标的一半
        scale = ws._optimal_scale(rec_sa, target)
        assert 1.5 < scale < 2.5

    def test_identical_spectrum_scale_near_one(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0, 0.5],
        )
        ws = WaveSelector(cfg)
        scale = ws._optimal_scale(target, target)
        assert abs(scale - 1.0) < 0.05

    def test_zero_record_returns_zero(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0],
        )
        ws = WaveSelector(cfg)
        scale = ws._optimal_scale(np.zeros(len(periods)), target)
        assert scale == 0.0

    def test_isolation_weighting(self):
        """隔震模式下 _optimal_scale 也对隔震周期加权"""
        periods = _make_periods()
        target = _make_target(periods)
        # 构造记录谱：在隔震周期附近偏低
        rec_sa = target * 1.0
        iso_idx = np.argmin(np.abs(periods - 4.0))
        rec_sa[iso_idx] = target[iso_idx] * 0.3

        cfg_no_iso = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], isolation=False,
        )
        cfg_iso = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], isolation=True, T_isolation=[4.0],
        )
        ws_no = WaveSelector(cfg_no_iso)
        ws_iso = WaveSelector(cfg_iso)
        s_no = ws_no._optimal_scale(rec_sa, target)
        s_iso = ws_iso._optimal_scale(rec_sa, target)
        # 隔震模式下缩放系数应略有不同（因为额外加权）
        assert s_no != pytest.approx(s_iso, abs=1e-10)


# ---------------------------------------------------------------------------
# Test: 隔震双周期匹配
# ---------------------------------------------------------------------------

class TestIsolationDualPeriod:
    def test_isolation_rejects_bad_iso_period(self):
        """隔震周期偏差超限时应被过滤"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], spectral_tol=0.20,
            isolation=True, T_isolation=[3.0],
            n_select=1, scale_range=(0.5, 2.0),
            duration_factor=1.0,
        )
        ws = WaveSelector(cfg)

        # 记录谱：主周期匹配好，但隔震周期偏差大
        rec_sa = target.copy()
        iso_idx = np.argmin(np.abs(periods - 3.0))
        rec_sa[iso_idx] = target[iso_idx] * 0.5  # 50% 偏差 > 20% 容限

        rec = _make_record(1, rec_sa, eff_duration=30.0)
        db = _make_database([rec], periods)
        results = ws.select(db)
        assert len(results) == 0  # 应被过滤掉

    def test_isolation_accepts_good_match(self):
        """主周期和隔震周期都匹配时应通过"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], spectral_tol=0.30,
            isolation=True, T_isolation=[3.0],
            n_select=1, scale_range=(0.5, 2.0),
            duration_factor=1.0,
        )
        ws = WaveSelector(cfg)

        # 记录谱与目标谱完全一致
        rec = _make_record(1, target.copy(), eff_duration=30.0)
        db = _make_database([rec], periods)
        results = ws.select(db)
        assert len(results) == 1
        # deviations 应包含隔震周期
        assert 3.0 in results[0].deviations

    def test_non_isolation_ignores_T_isolation(self):
        """非隔震模式不检查 T_isolation"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], spectral_tol=0.20,
            isolation=False, T_isolation=[3.0],
            n_select=1, scale_range=(0.5, 2.0),
            duration_factor=1.0,
        )
        ws = WaveSelector(cfg)

        rec_sa = target.copy()
        iso_idx = np.argmin(np.abs(periods - 3.0))
        rec_sa[iso_idx] = target[iso_idx] * 0.5  # 隔震周期偏差大

        rec = _make_record(1, rec_sa, eff_duration=30.0)
        db = _make_database([rec], periods)
        results = ws.select(db)
        # 非隔震模式不检查隔震周期，应通过
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Test: select() 合成数据完整流程
# ---------------------------------------------------------------------------

class TestSelectFlow:
    def test_select_returns_n_waves(self):
        """合成数据 select() 应返回 n_select 条"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0, 0.5], spectral_tol=0.30,
            n_select=3, scale_range=(0.5, 2.0),
            duration_factor=1.0,
        )
        ws = WaveSelector(cfg)

        # 构造 10 条匹配良好的记录（不同 RSN）
        records = []
        for i in range(10):
            noise = np.random.RandomState(i).normal(0, 0.02, len(periods))
            sa = target * (1.0 + noise)
            records.append(_make_record(i + 1, sa, eff_duration=30.0))

        db = _make_database(records, periods)
        results = ws.select(db)
        assert len(results) == 3
        # 每条结果都应标记通过
        for r in results:
            assert r.passed_duration is True
            assert r.passed_spectrum is True
            assert r.scale_factor > 0

    def test_select_filters_short_duration(self):
        """持时不足的记录应被过滤"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], spectral_tol=0.30,
            n_select=1, scale_range=(0.5, 2.0),
            duration_factor=5.0,  # 需要 5s
        )
        ws = WaveSelector(cfg)

        rec = _make_record(1, target.copy(), eff_duration=3.0)  # 不足 5s
        db = _make_database([rec], periods)
        results = ws.select(db)
        assert len(results) == 0

    def test_select_filters_out_of_scale_range(self):
        """缩放系数超范围的记录应被过滤"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], spectral_tol=0.30,
            n_select=1, scale_range=(0.5, 2.0),
            duration_factor=1.0,
        )
        ws = WaveSelector(cfg)

        # 记录谱极小，需要缩放 > 2.0
        rec = _make_record(1, target * 0.1, eff_duration=30.0)
        db = _make_database([rec], periods)
        results = ws.select(db)
        assert len(results) == 0

    def test_select_no_spectra_raises(self):
        """无反应谱数据应抛出 RuntimeError"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], n_select=1,
        )
        ws = WaveSelector(cfg)

        rec = _make_record(1, None, eff_duration=30.0)
        db = _make_database([rec], periods)
        with pytest.raises(RuntimeError, match="无反应谱"):
            ws.select(db)

    def test_select_avoids_duplicate_rsn(self):
        """贪心组合应避免同一 RSN 重复选取"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], spectral_tol=0.30,
            n_select=2, scale_range=(0.5, 2.0),
            duration_factor=1.0,
        )
        ws = WaveSelector(cfg)

        # 3 条记录，其中 2 条同 RSN
        records = [
            _make_record(1, target.copy(), eff_duration=30.0),
            _make_record(1, target * 0.95, eff_duration=30.0),
            _make_record(2, target * 1.02, eff_duration=30.0),
        ]
        db = _make_database(records, periods)
        results = ws.select(db)
        rsns = [r.record.rsn for r in results]
        assert len(set(rsns)) == len(rsns)  # 无重复 RSN


# ---------------------------------------------------------------------------
# Test: mean_spectrum / envelope_spectrum
# ---------------------------------------------------------------------------

class TestSpectrumHelpers:
    def _setup(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], n_select=2,
            duration_factor=1.0, scale_range=(0.5, 4.0),
        )
        ws = WaveSelector(cfg)

        sa1 = np.ones(len(periods)) * 0.4
        sa2 = np.ones(len(periods)) * 0.6
        r1 = SelectionResult(
            record=_make_record(1, sa1), scale_factor=1.0,
            passed_duration=True, passed_spectrum=True,
        )
        r2 = SelectionResult(
            record=_make_record(2, sa2), scale_factor=1.0,
            passed_duration=True, passed_spectrum=True,
        )
        db = _make_database([r1.record, r2.record], periods)
        return ws, [r1, r2], db, periods

    def test_mean_spectrum(self):
        ws, results, db, periods = self._setup()
        mean_sa = ws.mean_spectrum(results, db)
        assert len(mean_sa) == len(periods)
        # mean of 0.4 and 0.6 = 0.5
        np.testing.assert_allclose(mean_sa, 0.5, atol=1e-10)

    def test_envelope_spectrum(self):
        ws, results, db, periods = self._setup()
        env_sa = ws.envelope_spectrum(results, db)
        assert len(env_sa) == len(periods)
        # max of 0.4 and 0.6 = 0.6
        np.testing.assert_allclose(env_sa, 0.6, atol=1e-10)

    def test_mean_spectrum_with_scale(self):
        """缩放系数应体现在平均谱中"""
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], n_select=1,
        )
        ws = WaveSelector(cfg)

        sa = np.ones(len(periods)) * 0.25
        r = SelectionResult(
            record=_make_record(1, sa), scale_factor=2.0,
            passed_duration=True, passed_spectrum=True,
        )
        db = _make_database([r.record], periods)
        mean_sa = ws.mean_spectrum([r], db)
        np.testing.assert_allclose(mean_sa, 0.5, atol=1e-10)

    def test_empty_results(self):
        periods = _make_periods()
        target = _make_target(periods)
        cfg = SelectionConfig(
            target_sa=target, periods=periods,
            T_main=[1.0], n_select=1,
        )
        ws = WaveSelector(cfg)
        db = _make_database([], periods)
        mean_sa = ws.mean_spectrum([], db)
        env_sa = ws.envelope_spectrum([], db)
        np.testing.assert_array_equal(mean_sa, 0.0)
        np.testing.assert_array_equal(env_sa, 0.0)
