"""
后台计算线程基础设施

所有耗时计算在 QThread 中执行，通过信号通知 GUI 更新。
"""

from PySide6.QtCore import QThread, Signal, QObject


class WorkerSignals(QObject):
    """通用 Worker 信号"""
    started = Signal()
    progress = Signal(int, str)       # (百分比, 描述)
    finished = Signal(object)         # 结果对象
    error = Signal(str)               # 错误信息


class BaseWorker(QThread):
    """后台计算基类"""

    signals = None  # 每个实例独立创建

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def is_cancelled(self):
        return self._cancelled

    def run(self):
        self.signals.started.emit()
        try:
            result = self.execute()
            if not self._cancelled:
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

    def execute(self):
        """子类实现具体计算逻辑，返回结果对象"""
        raise NotImplementedError


class SpectrumWorker(BaseWorker):
    """反应谱计算 Worker"""

    def __init__(self, signal_obj, periods, zeta=0.05, method="newmark", parent=None):
        super().__init__(parent)
        self._signal = signal_obj
        self._periods = periods
        self._zeta = zeta
        self._method = method

    def execute(self):
        from seiswave.core import Spectra
        return Spectra.compute(
            self._signal.acc, self._signal.dt,
            self._periods, self._zeta, self._method,
        )


class BatchSpectrumWorker(BaseWorker):
    """批量反应谱计算 Worker"""

    def __init__(self, signals, periods, zeta=0.05, method="newmark", parent=None):
        super().__init__(parent)
        self._signals = signals
        self._periods = periods
        self._zeta = zeta
        self._method = method

    def execute(self):
        from seiswave.core import Spectra
        results = []
        total = len(self._signals)
        for i, sig in enumerate(self._signals):
            if self.is_cancelled:
                break
            spec = Spectra.compute(
                sig.acc, sig.dt, self._periods, self._zeta, self._method,
            )
            results.append((sig, spec))
            pct = int((i + 1) / total * 100)
            self.signals.progress.emit(pct, f"计算反应谱 {i+1}/{total}: {sig.name}")
        return results


class SelectionWorker(BaseWorker):
    """选波计算 Worker"""

    def __init__(self, selector, signals, parent=None):
        super().__init__(parent)
        self._selector = selector
        self._signals = signals

    def execute(self):
        def progress_cb(pct, msg):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            self.signals.progress.emit(pct, msg)

        return self._selector.select(self._signals, progress_callback=progress_cb)


class GeneratorWorker(BaseWorker):
    """人工波生成 Worker"""

    def __init__(self, target_spectrum, periods, n=4096, dt=0.02,
                 zeta=0.05, pga=1.0, tol=0.05, max_iter=50, parent=None):
        super().__init__(parent)
        self._target = target_spectrum
        self._periods = periods
        self._n = n
        self._dt = dt
        self._zeta = zeta
        self._pga = pga
        self._tol = tol
        self._max_iter = max_iter

    def execute(self):
        from seiswave.core import WaveGenerator

        def progress_cb(pct, msg):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            self.signals.progress.emit(pct, msg)

        return WaveGenerator.generate(
            self._target, self._periods,
            n=self._n, dt=self._dt, zeta=self._zeta,
            pga=self._pga, tol=self._tol, max_iter=self._max_iter,
            progress_callback=progress_cb,
        )
