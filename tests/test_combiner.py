"""
Combiner 模块测试

测试 WaveGroup、add_artificial、export、validate、report_text。
使用合成 EQSignal 进行测试。
"""

import os
import json
import tempfile
import numpy as np
import pytest

from seiswave.core.signal import EQSignal
from seiswave.core.combiner import Combiner, WaveGroup, ValidationResult


def _make_signal(freq=2.0, duration=10.0, dt=0.02, amp=0.3, name="test"):
    """生成合成正弦地震信号"""
    t = np.arange(0, duration, dt)
    # 带包络的正弦波
    env = np.sin(np.pi * t / duration) ** 2
    acc = amp * env * np.sin(2 * np.pi * freq * t)
    return EQSignal(acc, dt, name=name)


class TestWaveGroup:
    def test_creation(self):
        g = WaveGroup(name="test", source="artificial")
        assert g.name == "test"
        assert g.source == "artificial"
        assert g.h1 is None
        assert g.h2 is None
        assert g.v is None
        assert g.scale_factor == 1.0

    def test_with_signals(self):
        h1 = _make_signal(name="h1")
        h2 = _make_signal(name="h2")
        g = WaveGroup(name="grp", source="artificial", h1=h1, h2=h2)
        assert g.h1 is not None
        assert g.h2 is not None
        assert g.v is None


class TestAddArtificial:
    def test_add_single(self):
        c = Combiner()
        h1 = _make_signal(name="art_h1")
        g = c.add_artificial(h1, name="art", index=0)
        assert len(c.groups) == 1
        assert g.source == "artificial"
        assert g.name == "art_1"
        assert g.h1 is h1

    def test_add_three_components(self):
        c = Combiner()
        h1 = _make_signal(name="h1")
        h2 = _make_signal(name="h2")
        v = _make_signal(name="v", amp=0.15)
        g = c.add_artificial(h1, h2, v, name="full", index=0)
        assert g.h1 is not None
        assert g.h2 is not None
        assert g.v is not None

    def test_add_multiple(self):
        c = Combiner()
        for i in range(3):
            c.add_artificial(_make_signal(name=f"h1_{i}"), index=i)
        assert len(c.groups) == 3
        assert c.groups[2].name == "artificial_3"


class TestExport:
    def test_export_at2(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            c = Combiner(output_dir=tmpdir)
            h1 = _make_signal(name="exp_h1")
            c.add_artificial(h1, name="wave", index=0)
            out = c.export(fmt='at2')

            assert os.path.isdir(out)
            # 检查 summary.json
            summary_path = os.path.join(out, 'summary.json')
            assert os.path.isfile(summary_path)
            with open(summary_path) as f:
                summary = json.load(f)
            assert summary['n_groups'] == 1
            assert summary['groups'][0]['has_h1'] is True

    def test_export_txt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            c = Combiner(output_dir=tmpdir)
            h1 = _make_signal(name="txt_h1")
            c.add_artificial(h1, name="txt_wave", index=0)
            out = c.export(fmt='txt')

            # 查找 txt 文件
            group_dir = os.path.join(out, "01_txt_wave_1")
            assert os.path.isdir(group_dir)
            txt_files = [f for f in os.listdir(group_dir) if f.endswith('.txt')]
            assert len(txt_files) == 1

    def test_export_both(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            c = Combiner(output_dir=tmpdir)
            h1 = _make_signal(name="both_h1")
            h2 = _make_signal(name="both_h2")
            c.add_artificial(h1, h2, name="both", index=0)
            c.export(fmt='both')

            group_dir = os.path.join(tmpdir, "01_both_1")
            files = os.listdir(group_dir)
            at2_files = [f for f in files if f.endswith('.AT2')]
            txt_files = [f for f in files if f.endswith('.txt')]
            assert len(at2_files) == 2  # H1 + H2
            assert len(txt_files) == 2


class TestValidate:
    def _build_combiner_with_groups(self, n=7, freq=2.0, amp=0.3):
        """构建含 n 组波的 Combiner"""
        c = Combiner()
        for i in range(n):
            h1 = _make_signal(freq=freq, amp=amp, name=f"h1_{i}")
            c.add_artificial(h1, name=f"wave_{i}", index=i)
        return c

    def test_validate_count_fail(self):
        c = self._build_combiner_with_groups(n=3)
        periods = np.array([0.5, 1.0, 2.0])
        target_sa = np.array([0.5, 0.3, 0.1])
        result = c.validate(0.3, target_sa, periods)
        assert isinstance(result, ValidationResult)
        assert result.n_groups == 3
        assert result.n_required == 7
        assert not result.passed  # 数量不足

    def test_validate_structure(self):
        c = self._build_combiner_with_groups(n=7)
        periods = np.array([0.5, 1.0, 2.0])
        target_sa = np.array([0.5, 0.3, 0.1])
        result = c.validate(0.3, target_sa, periods)
        assert isinstance(result, ValidationResult)
        assert result.n_groups == 7
        assert len(result.individual_checks) == 7
        assert result.mean_ratios is not None
        assert len(result.mean_ratios) == len(periods)

    def test_validate_empty(self):
        c = Combiner()
        periods = np.array([0.5, 1.0])
        target_sa = np.array([0.5, 0.3])
        result = c.validate(0.3, target_sa, periods)
        assert not result.passed
        assert "无有效波形数据" in result.messages[0]


class TestReportText:
    def test_report_text_basic(self):
        c = Combiner()
        h1 = _make_signal(name="rpt_h1")
        c.add_artificial(h1, name="report_wave", index=0)
        text = c.report_text()
        assert "选波结果汇总" in text
        assert "1 组" in text
        assert "report_wave_1" in text
        assert "人工波" in text
        assert "PGA=" in text

    def test_report_text_multiple(self):
        c = Combiner()
        for i in range(3):
            h1 = _make_signal(name=f"h1_{i}")
            c.add_artificial(h1, name=f"w{i}", index=i)
        text = c.report_text()
        assert "3 组" in text
        assert "w0_1" in text
        assert "w2_3" in text


class TestComputeSpectra:
    def test_compute_spectra_returns_list(self):
        c = Combiner()
        h1 = _make_signal(freq=2.0, name="sp_h1")
        c.add_artificial(h1, name="sp", index=0)
        periods = np.array([0.3, 0.5, 1.0])
        result = c.compute_spectra(periods)
        assert len(result) == 1
        assert len(result[0]) == len(periods)
        assert np.all(result[0] > 0)

    def test_compute_spectra_no_h1(self):
        c = Combiner()
        g = WaveGroup(name="empty", source="artificial")
        c.groups.append(g)
        periods = np.array([0.5, 1.0])
        result = c.compute_spectra(periods)
        assert len(result) == 1
        assert np.all(result[0] == 0)


class TestHtmlReport:
    def test_generate_html_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            c = Combiner(output_dir=tmpdir)
            h1 = _make_signal(name="html_h1")
            c.add_artificial(h1, name="html_wave", index=0)
            periods = np.array([0.3, 0.5, 1.0, 2.0])
            target_sa = np.array([0.5, 0.4, 0.2, 0.1])
            path = c.generate_html_report(target_sa, periods)
            assert os.path.isfile(path)
            with open(path, encoding='utf-8') as f:
                html = f.read()
            assert '地震波组合报告' in html
            assert 'html_wave_1' in html
            assert 'data:image/png;base64,' in html

