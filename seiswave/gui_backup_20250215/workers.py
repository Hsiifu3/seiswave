"""
后台计算线程基础设施

所有耗时计算在 QThread 中执行，通过信号通知 GUI 更新。
Fortran 加速函数不释放 GIL，需要用 multiprocessing 隔离。
"""

import numpy as np
import multiprocessing as mp
from PySide6.QtCore import QThread, Signal, QObject


class WorkerSignals(QObject):
    """通用 Worker 信号"""
    started = Signal()
    progress = Signal(int, str)       # (百分比, 描述)
    finished = Signal(object)         # 结果对象
    error = Signal(str)               # 错误信息


class BaseWorker(QThread):
    """后台计算基类"""

    signals = None

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
    """旧版选波计算 Worker（兼容）"""

    def __init__(self, selector, database, parent=None):
        super().__init__(parent)
        self._selector = selector
        self._database = database

    def execute(self):
        def progress_cb(current, total):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            pct = int(current / total * 100) if total > 0 else 0
            self.signals.progress.emit(pct, f"筛选 {current}/{total}")

        return self._selector.select(self._database, progress_cb=progress_cb)


def _generator_subprocess(conn, target, periods, n, dt, zeta, pga, tol, max_iter):
    """在独立进程中执行人工波生成（绕开 Fortran GIL 阻塞）"""
    try:
        from seiswave.core import WaveGenerator

        def progress_cb(iteration, max_err, mean_err):
            try:
                conn.send(('progress', iteration, max_err, mean_err))
            except Exception:
                pass

        result = WaveGenerator.generate(
            target, periods,
            n=n, dt=dt, zeta=zeta,
            pga=pga, tol=tol, max_iter=max_iter,
            progress_callback=progress_cb,
        )
        conn.send(('done', result.acc, result.dt, result.name))
    except Exception as e:
        conn.send(('error', str(e)))
    finally:
        conn.close()


class GeneratorWorker(BaseWorker):
    """人工波生成 Worker（子进程隔离，避免 Fortran GIL 阻塞）"""

    def __init__(self, target_spectrum, periods, n=4096, dt=0.02,
                 zeta=0.05, pga=1.0, tol=0.05, max_iter=50, parent=None):
        super().__init__(parent)
        self._target = np.asarray(target_spectrum, dtype=np.float64)
        self._periods = np.asarray(periods, dtype=np.float64)
        self._n = n
        self._dt = dt
        self._zeta = zeta
        self._pga = pga
        self._tol = tol
        self._max_iter = max_iter
        self._process = None

    def cancel(self):
        super().cancel()
        if self._process and self._process.is_alive():
            self._process.terminate()

    def execute(self):
        from seiswave.core.signal import EQSignal

        parent_conn, child_conn = mp.Pipe()

        self._process = mp.Process(
            target=_generator_subprocess,
            args=(child_conn, self._target, self._periods,
                  self._n, self._dt, self._zeta, self._pga,
                  self._tol, self._max_iter),
            daemon=True,
        )
        self._process.start()

        # 轮询子进程消息，保持 GIL 可释放
        while self._process.is_alive() or parent_conn.poll():
            if self.is_cancelled:
                self._process.terminate()
                raise InterruptedError("用户取消")

            if parent_conn.poll(timeout=0.1):
                msg = parent_conn.recv()
                if msg[0] == 'progress':
                    _, iteration, max_err, mean_err = msg
                    pct = int(iteration / self._max_iter * 100)
                    text = f"迭代 {iteration}: 最大误差 {max_err:.4f}, 平均误差 {mean_err:.4f}"
                    self.signals.progress.emit(pct, text)
                elif msg[0] == 'done':
                    _, acc, dt, name = msg
                    result = EQSignal(np.asarray(acc), dt, name=name)
                    result.a2vd()
                    parent_conn.close()
                    return result
                elif msg[0] == 'error':
                    parent_conn.close()
                    raise RuntimeError(msg[1])

        parent_conn.close()
        raise RuntimeError("子进程异常退出")


# ──────────── PEER 数据库相关 Workers ────────────

class PeerLoadWorker(BaseWorker):
    """PEER 数据库加载 + 反应谱预计算 Worker"""

    def __init__(self, data_dir, zeta=0.05, parent=None):
        super().__init__(parent)
        self._data_dir = data_dir
        self._zeta = zeta

    def execute(self):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase(data_dir=self._data_dir)

        # 尝试加载缓存
        self.signals.progress.emit(10, "检查索引缓存...")
        if not db.load_index():
            self.signals.progress.emit(20, "构建索引...")
            db.build_index()

        n = len(db)
        self.signals.progress.emit(40, f"已索引 {n} 条记录")

        # 尝试加载反应谱缓存
        self.signals.progress.emit(50, "检查反应谱缓存...")
        if not db.load_spectra_cache(self._zeta):
            self.signals.progress.emit(60, "预计算反应谱...")
            periods = np.linspace(0.04, 6.0, 200)

            def progress_cb(i, total):
                if self.is_cancelled:
                    raise InterruptedError("用户取消")
                pct = 60 + int(i / total * 35)
                self.signals.progress.emit(pct, f"反应谱 {i}/{total}")

            db.precompute_spectra(periods, self._zeta, progress_cb=progress_cb)

        self.signals.progress.emit(100, "加载完成")
        return db


class PeerSelectWorker(BaseWorker):
    """PEER 数据库选波 Worker"""

    def __init__(self, config, database, parent=None):
        super().__init__(parent)
        self._config = config
        self._db = database

    def execute(self):
        from seiswave.core.selector import WaveSelector

        selector = WaveSelector(self._config)

        def progress_cb(i, total):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            pct = int(i / total * 100)
            self.signals.progress.emit(pct, f"筛选 {i}/{total}")

        return selector.select(self._db, progress_cb=progress_cb)
