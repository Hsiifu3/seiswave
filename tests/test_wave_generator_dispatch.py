"""
Task 8 — 统一入口与类型分发 单元测试

覆盖:
- WaveGenerator.generate(type="FF") 调用 FarFieldGenerator
- WaveGenerator.generate(type="NF") 调用 NearFieldNoPulseGenerator
- WaveGenerator.generate(type="NFP") 调用 NearFieldPulseGenerator
- WaveGenerator.generate(type=None) 保持现有通用谱匹配行为（向后兼容）
- 错误类型时抛出 ValueError
- create_ground_motion() 便捷函数
"""

import numpy as np
import pytest

# 测试用小参数，加速谱匹配
TEST_N = 1024
TEST_DT = 0.02
TEST_TOL = 0.10
TEST_MAX_ITER = 15


class TestWaveGeneratorDispatch:
    @pytest.mark.parametrize(
        ("gm_type", "kwargs", "name_tag"),
        [
            ("FF", {"Mw": 7.0, "R": 50.0, "Vs30": 760.0, "dt": TEST_DT}, "FF"),
            ("NF", {"Mw": 7.0, "R": 5.0, "Vs30": 760.0, "dt": TEST_DT}, "NF"),
            ("NFP", {"Mw": 7.5, "R": 5.0, "Vs30": 760.0, "dt": 0.01}, "NFP"),
        ],
    )
    def test_dispatch_special_generators_do_not_call_baseline_correction(
        self, gm_type, kwargs, name_tag, monkeypatch
    ):
        """FF/NF/NFP 主生成链路默认不应隐式触发 EQSignal 基线校正。"""
        from seiswave.core.generator import WaveGenerator

        def fail_if_called(self, *args, **kwargs):
            raise AssertionError("baseline_correction should not be called during generation")

        monkeypatch.setattr(
            "seiswave.core.signal.EQSignal.baseline_correction",
            fail_if_called,
        )

        sig = WaveGenerator.generate(
            type=gm_type,
            n=TEST_N,
            max_iter=TEST_MAX_ITER,
            tol=TEST_TOL,
            **kwargs,
        )

        assert sig.n == TEST_N
        assert hasattr(sig, "acc")
        assert hasattr(sig, "vel")
        assert hasattr(sig, "disp")
        assert name_tag in sig.name

    def test_dispatch_ff(self):
        """type='FF' 应调用 FarFieldGenerator 并返回 EQSignal"""
        from seiswave.core.generator import WaveGenerator

        sig = WaveGenerator.generate(
            type="FF",
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.n == TEST_N
        assert sig.dt == TEST_DT
        assert hasattr(sig, "acc")
        assert hasattr(sig, "vel")
        assert hasattr(sig, "disp")
        assert "FF" in sig.name
        assert sig.pga > 0

    def test_dispatch_nf(self):
        """type='NF' 应调用 NearFieldNoPulseGenerator 并返回 EQSignal"""
        from seiswave.core.generator import WaveGenerator

        sig = WaveGenerator.generate(
            type="NF",
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.n == TEST_N
        assert sig.dt == TEST_DT
        assert hasattr(sig, "acc")
        assert hasattr(sig, "vel")
        assert hasattr(sig, "disp")
        assert "NF" in sig.name
        assert sig.pga > 0

    def test_dispatch_nfp(self):
        """type='NFP' 应调用 NearFieldPulseGenerator 并返回含脉冲元数据的 EQSignal"""
        from seiswave.core.generator import WaveGenerator

        sig = WaveGenerator.generate(
            type="NFP",
            Mw=7.5, R=5.0, Vs30=760.0,
            n=TEST_N, dt=0.01,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.n == TEST_N
        assert sig.dt == 0.01
        assert hasattr(sig, "acc")
        assert hasattr(sig, "vel")
        assert hasattr(sig, "disp")
        assert "NFP" in sig.name
        assert sig.pga > 0

        # NFP 特有的脉冲元数据
        assert hasattr(sig, "pulse_params")
        assert hasattr(sig, "pulse_metrics")
        assert hasattr(sig, "pulse_acc")
        assert hasattr(sig, "pulse_vel")
        assert hasattr(sig, "residual_acc")
        assert hasattr(sig, "total_spectrum")
        assert hasattr(sig, "spectrum_periods")

    def test_dispatch_none_backward_compatible(self):
        """type=None 时应保持原有通用谱匹配行为，不破坏现有调用"""
        from seiswave.core.generator import WaveGenerator
        from seiswave.core.spectrum import Spectra

        periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0])
        target = np.array([0.5, 0.8, 1.0, 0.7, 0.4, 0.2])

        sig = WaveGenerator.generate(
            target, periods,
            n=TEST_N, dt=TEST_DT,
            pga=0.5, tol=TEST_TOL, max_iter=TEST_MAX_ITER,
        )
        assert sig.n == TEST_N
        assert sig.dt == TEST_DT
        assert hasattr(sig, "acc")
        assert hasattr(sig, "vel")
        assert hasattr(sig, "disp")
        assert sig.pga > 0

    def test_dispatch_none_requires_target_spectrum(self):
        """type=None 但不提供 target_spectrum/periods 时应报错"""
        from seiswave.core.generator import WaveGenerator

        with pytest.raises(ValueError, match="target_spectrum"):
            WaveGenerator.generate(
                n=TEST_N, dt=TEST_DT,
                tol=TEST_TOL, max_iter=TEST_MAX_ITER,
            )

    def test_dispatch_invalid_type_raises(self):
        """错误类型应抛出 ValueError"""
        from seiswave.core.generator import WaveGenerator

        with pytest.raises(ValueError, match="无效"):
            WaveGenerator.generate(
                type="INVALID",
                Mw=7.0, R=50.0,
                n=TEST_N, dt=TEST_DT,
                max_iter=TEST_MAX_ITER, tol=TEST_TOL,
            )

    def test_dispatch_case_insensitive(self):
        """类型参数应大小写不敏感"""
        from seiswave.core.generator import WaveGenerator

        sig_ff = WaveGenerator.generate(
            type="ff",
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "FF" in sig_ff.name

        sig_nf = WaveGenerator.generate(
            type="nF",
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "NF" in sig_nf.name

        sig_nfp = WaveGenerator.generate(
            type="Nfp",
            Mw=7.5, R=5.0, Vs30=760.0,
            n=TEST_N, dt=0.01,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "NFP" in sig_nfp.name

    def test_create_ground_motion_convenience_ff(self):
        """create_ground_motion 便捷函数 FF 分支"""
        from seiswave.core.generator import create_ground_motion

        sig = create_ground_motion(
            type="FF", Mw=7.0, R=50.0,
            n=TEST_N, dt=TEST_DT,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "FF" in sig.name
        assert sig.pga > 0

    def test_create_ground_motion_convenience_nf(self):
        """create_ground_motion 便捷函数 NF 分支"""
        from seiswave.core.generator import create_ground_motion

        sig = create_ground_motion(
            type="NF", Mw=7.0, R=5.0,
            n=TEST_N, dt=TEST_DT,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "NF" in sig.name
        assert sig.pga > 0

    def test_create_ground_motion_convenience_nfp(self):
        """create_ground_motion 便捷函数 NFP 分支，验证脉冲元数据"""
        from seiswave.core.generator import create_ground_motion

        sig = create_ground_motion(
            type="NFP", Mw=7.5, R=5.0,
            n=TEST_N, dt=0.01,
            max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "NFP" in sig.name
        assert sig.pga > 0
        assert hasattr(sig, "pulse_params")
        assert hasattr(sig, "pulse_metrics")

    def test_create_ground_motion_invalid_type_raises(self):
        """create_ground_motion 传入错误类型也应报错"""
        from seiswave.core.generator import create_ground_motion

        with pytest.raises(ValueError, match="无效"):
            create_ground_motion(
                type="XYZ", Mw=7.0, R=50.0,
                n=TEST_N, dt=TEST_DT,
                max_iter=TEST_MAX_ITER, tol=TEST_TOL,
            )

    def test_backward_compatible_positional_args(self):
        """原有位置参数调用方式不受影响"""
        from seiswave.core.generator import WaveGenerator

        periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0])
        target = np.array([0.5, 0.8, 1.0, 0.7, 0.4, 0.2])

        # 原有调用方式：位置参数
        sig = WaveGenerator.generate(
            target, periods,
            512, 0.02, 0.05, 0.5, 0.10, 10, 1, None,
        )
        assert sig.n == 512
        assert sig.pga > 0

    def test_backward_compatible_keyword_args(self):
        """原有关键字参数调用方式不受影响"""
        from seiswave.core.generator import WaveGenerator

        periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0])
        target = np.array([0.5, 0.8, 1.0, 0.7, 0.4, 0.2])

        sig = WaveGenerator.generate(
            target_spectrum=target,
            periods=periods,
            n=512,
            dt=0.02,
            pga=0.5,
            tol=0.10,
            max_iter=10,
        )
        assert sig.n == 512
        assert sig.pga > 0
