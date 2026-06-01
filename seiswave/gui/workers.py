"""
后台计算线程基础设施

所有耗时计算在 QThread 中执行，通过信号通知 GUI 更新。
Fortran 加速函数不释放 GIL，需要用 multiprocessing 隔离。
"""

import os
import time
import uuid
import logging
import traceback
import numpy as np
import multiprocessing as mp
from PySide6.QtCore import QThread, Signal, QObject, Qt

logger = logging.getLogger(__name__)


def _ensure_child_logging():
    """spawn 子进程内兜底启用日志，避免调试信息丢失。"""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        filename='/tmp/seiswave.log',
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        force=True,
    )


def _algo_name(fm: int) -> str:
    return 'time-domain' if int(fm) == 1 else 'freq-domain'


class WorkerSignals(QObject):
    """通用 Worker 信号"""
    started = Signal()
    progress = Signal(int, str)       # (百分比, 描述)
    finished = Signal(object)         # 结果对象
    error = Signal(str)               # 错误信息


class BaseWorker(QThread):
    """后台计算基类"""

    def __init__(self, parent=None, job_id=None):
        super().__init__(parent)
        self.signals = WorkerSignals()
        self._cancelled = False
        self._job_id = job_id or uuid.uuid4().hex[:8]

    def cancel(self):
        self._cancelled = True
        logger.info("[%s] %s cancel requested", self._job_id, self.__class__.__name__)

    @property
    def is_cancelled(self):
        return self._cancelled

    def run(self):
        logger.info("[%s] %s run started", self._job_id, self.__class__.__name__)
        self.signals.started.emit()
        try:
            result = self.execute()
            if not self._cancelled:
                logger.info("[%s] %s run finished successfully", self._job_id, self.__class__.__name__)
                self.signals.finished.emit(result)
            else:
                logger.info("[%s] %s run finished after cancellation", self._job_id, self.__class__.__name__)
        except Exception as e:
            logger.exception("[%s] %s run failed: %s", self._job_id, self.__class__.__name__, e)
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


def _generator_subprocess(conn, target, periods, n, dt, zeta, pga, tol, max_iter, fm=0, job_id='unknown', trial_idx=None):
    """在独立进程中执行人工波生成（绕开 Fortran GIL 阻塞）"""
    _ensure_child_logging()
    trial_text = '' if trial_idx is None else f' trial={trial_idx+1}'
    logger.info("[%s]%s subprocess start algo=%s n=%s dt=%.5f periods=%s pga=%.4f tol=%.4f max_iter=%s",
                job_id, trial_text, _algo_name(fm), n, dt, len(periods), pga, tol, max_iter)
    try:
        from seiswave.core import WaveGenerator

        def progress_cb(iteration, max_err, mean_err):
            try:
                logger.info("[%s]%s subprocess progress iter=%s max_err=%.6f mean_err=%.6f",
                            job_id, trial_text, iteration, max_err, mean_err)
                conn.send(('progress', iteration, max_err, mean_err))
            except Exception:
                pass

        result = WaveGenerator.generate(
            target, periods,
            n=n, dt=dt, zeta=zeta,
            pga=pga, tol=tol, max_iter=max_iter,
            fm=fm,
            progress_callback=progress_cb,
            n_trials=1,
        )
        logger.info("[%s]%s subprocess done name=%s len=%s dt=%.5f",
                    job_id, trial_text, result.name, len(result.acc), result.dt)
        conn.send(('done', result.acc, result.dt, result.name))
    except Exception as e:
        logger.exception("[%s]%s subprocess failed: %s", job_id, trial_text, e)
        conn.send(('error', str(e)))
    finally:
        conn.close()


class GeneratorWorker(BaseWorker):
    """人工波生成 Worker（子进程隔离，避免 Fortran GIL 阻塞）"""

    def __init__(self, target_spectrum, periods, n=4096, dt=0.02,
                 zeta=0.05, pga=1.0, tol=0.05, max_iter=50, fm=0, parent=None,
                 job_id=None):
        super().__init__(parent, job_id=job_id)
        self._target = np.asarray(target_spectrum, dtype=np.float64)
        self._periods = np.asarray(periods, dtype=np.float64)
        self._n = n
        self._dt = dt
        self._zeta = zeta
        self._pga = pga
        self._tol = tol
        self._max_iter = max_iter
        self._fm = fm
        self._process = None

    def _generate_inprocess(self):
        """兼容模式：子进程不可用时回退到主进程计算。"""
        from seiswave.core import WaveGenerator
        logger.info("[%s] GeneratorWorker fallback to in-process algo=%s", self._job_id, _algo_name(self._fm))

        def progress_cb(iteration, max_err, mean_err):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            pct = int(iteration / self._max_iter * 100)
            text = f"迭代 {iteration}: 最大误差 {max_err:.4f}, 平均误差 {mean_err:.4f}"
            self.signals.progress.emit(pct, text)

        result = WaveGenerator.generate(
            self._target, self._periods,
            n=self._n, dt=self._dt, zeta=self._zeta,
            pga=self._pga, tol=self._tol, max_iter=self._max_iter,
            fm=self._fm,
            progress_callback=progress_cb,
            n_trials=1,
        )
        logger.info("[%s] GeneratorWorker in-process done name=%s len=%s", self._job_id, result.name, len(result.acc))
        return result

    def cancel(self):
        super().cancel()
        if self._process and self._process.is_alive():
            self._process.terminate()

    def execute(self):
        from seiswave.core.signal import EQSignal

        parent_conn, child_conn = mp.Pipe()

        logger.info("[%s] GeneratorWorker execute start algo=%s n=%s dt=%.5f periods=%s pga=%.4f tol=%.4f max_iter=%s",
                    self._job_id, _algo_name(self._fm), self._n, self._dt, len(self._periods), self._pga, self._tol, self._max_iter)
        self._process = mp.Process(
            target=_generator_subprocess,
            args=(child_conn, self._target, self._periods,
                  self._n, self._dt, self._zeta, self._pga,
                  self._tol, self._max_iter, self._fm, self._job_id, None),
            daemon=True,
        )
        try:
            self._process.start()
            logger.info("[%s] GeneratorWorker child pid=%s started", self._job_id, getattr(self._process, 'pid', '?'))
        except Exception:
            logger.exception("[%s] GeneratorWorker child start failed", self._job_id)
            parent_conn.close()
            return self._generate_inprocess()

        start_time = time.monotonic()
        timeout_seconds = max(120.0, float(self._max_iter) * 2.0)

        while self._process.is_alive() or parent_conn.poll():
            if self.is_cancelled:
                logger.warning("[%s] GeneratorWorker cancelled, terminating child pid=%s", self._job_id, getattr(self._process, 'pid', '?'))
                self._process.terminate()
                raise InterruptedError("用户取消")

            elapsed = time.monotonic() - start_time
            if elapsed > timeout_seconds:
                logger.warning("[%s] GeneratorWorker child timeout after %.2fs, switching to in-process", self._job_id, elapsed)
                self._process.terminate()
                self._process.join(timeout=1.0)
                parent_conn.close()
                self.signals.progress.emit(
                    99,
                    f"子进程超时 ({timeout_seconds:.0f}s)，切换兼容模式继续计算..."
                )
                return self._generate_inprocess()

            if parent_conn.poll(timeout=0.1):
                msg = parent_conn.recv()
                logger.info("[%s] GeneratorWorker received message type=%s", self._job_id, msg[0])
                if msg[0] == 'progress':
                    _, iteration, max_err, mean_err = msg
                    pct = int(iteration / self._max_iter * 100)
                    text = f"迭代 {iteration}: 最大误差 {max_err:.4f}, 平均误差 {mean_err:.4f}"
                    self.signals.progress.emit(pct, text)
                elif msg[0] == 'done':
                    _, acc, dt, name = msg
                    result = EQSignal(np.asarray(acc), dt, name=name)
                    result.a2vd()
                    logger.info("[%s] GeneratorWorker child done name=%s len=%s", self._job_id, name, len(acc))
                    parent_conn.close()
                    return result
                elif msg[0] == 'error':
                    logger.error("[%s] GeneratorWorker child error: %s", self._job_id, msg[1])
                    parent_conn.close()
                    raise RuntimeError(msg[1])

        logger.warning("[%s] GeneratorWorker child exited without done message, using in-process fallback", self._job_id)
        parent_conn.close()
        return self._generate_inprocess()


class MultiTrialGeneratorWorker(BaseWorker):
    """多 trial 人工波生成 Worker，自动取最优结果。

    每个 trial 独立生成一条人工波，最终选取均方根误差最小的。
    finished 信号返回 dict: {'best': EQSignal, 'all_results': [...], 'best_index': int}
    """

    def __init__(self, target_spectrum, periods, n=4096, dt=0.02,
                 zeta=0.05, pga=1.0, tol=0.05, max_iter=50,
                 n_trials=3, fm=0, parent=None, job_id=None):
        super().__init__(parent, job_id=job_id)
        self._target = np.asarray(target_spectrum, dtype=np.float64)
        self._periods = np.asarray(periods, dtype=np.float64)
        self._n = n
        self._dt = dt
        self._zeta = zeta
        self._pga = pga
        self._tol = tol
        self._max_iter = max_iter
        self._n_trials = n_trials
        self._fm = fm
        self._process = None

    def cancel(self):
        super().cancel()
        if self._process and self._process.is_alive():
            self._process.terminate()

    def _run_single_trial(self, trial_idx):
        from seiswave.core.signal import EQSignal

        parent_conn, child_conn = mp.Pipe()
        logger.info("[%s] MultiTrial start trial=%s/%s algo=%s", self._job_id, trial_idx + 1, self._n_trials, _algo_name(self._fm))
        self._process = mp.Process(
            target=_generator_subprocess,
            args=(child_conn, self._target, self._periods,
                  self._n, self._dt, self._zeta, self._pga,
                  self._tol, self._max_iter, self._fm, self._job_id, trial_idx),
            daemon=True,
        )
        try:
            self._process.start()
            logger.info("[%s] MultiTrial child pid=%s started for trial=%s", self._job_id, getattr(self._process, 'pid', '?'), trial_idx + 1)
        except Exception:
            logger.exception("[%s] MultiTrial child start failed for trial=%s", self._job_id, trial_idx + 1)
            parent_conn.close()
            return self._generate_inprocess_trial(trial_idx)

        start_time = time.monotonic()
        timeout_seconds = max(120.0, float(self._max_iter) * 2.0)

        while self._process.is_alive() or parent_conn.poll():
            if self.is_cancelled:
                logger.warning("[%s] MultiTrial cancelled at trial=%s pid=%s", self._job_id, trial_idx + 1, getattr(self._process, 'pid', '?'))
                self._process.terminate()
                raise InterruptedError("用户取消")

            elapsed = time.monotonic() - start_time
            if elapsed > timeout_seconds:
                logger.warning("[%s] MultiTrial timeout trial=%s elapsed=%.2fs, switching to in-process", self._job_id, trial_idx + 1, elapsed)
                self._process.terminate()
                self._process.join(timeout=1.0)
                parent_conn.close()
                self.signals.progress.emit(
                    99,
                    f"Trial {trial_idx+1} 子进程超时 ({timeout_seconds:.0f}s)，切换兼容模式继续计算..."
                )
                return self._generate_inprocess_trial(trial_idx)

            if parent_conn.poll(timeout=0.1):
                msg = parent_conn.recv()
                logger.info("[%s] MultiTrial trial=%s received message type=%s", self._job_id, trial_idx + 1, msg[0])
                if msg[0] == 'progress':
                    _, iteration, max_err, mean_err = msg
                    base = int(trial_idx / self._n_trials * 100)
                    step = int(iteration / self._max_iter
                               / self._n_trials * 100)
                    pct = min(base + step, 99)
                    text = (f"Trial {trial_idx+1}/{self._n_trials} "
                            f"迭代 {iteration}: 最大误差 {max_err:.4f}, "
                            f"均值误差 {mean_err:.4f}")
                    self.signals.progress.emit(pct, text)
                elif msg[0] == 'done':
                    _, acc, dt, name = msg
                    result = EQSignal(np.asarray(acc), dt, name=name)
                    result.a2vd()
                    logger.info("[%s] MultiTrial trial=%s done name=%s len=%s", self._job_id, trial_idx + 1, name, len(acc))
                    parent_conn.close()
                    return result
                elif msg[0] == 'error':
                    logger.error("[%s] MultiTrial trial=%s child error: %s", self._job_id, trial_idx + 1, msg[1])
                    parent_conn.close()
                    raise RuntimeError(msg[1])

        logger.warning("[%s] MultiTrial trial=%s child exited without done message, using in-process fallback", self._job_id, trial_idx + 1)
        parent_conn.close()
        return self._generate_inprocess_trial(trial_idx)

    def _generate_inprocess_trial(self, trial_idx):
        from seiswave.core import WaveGenerator
        logger.info("[%s] MultiTrial fallback to in-process for trial=%s", self._job_id, trial_idx + 1)

        def progress_cb(iteration, max_err, mean_err):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            base = int(trial_idx / self._n_trials * 100)
            step = int(iteration / self._max_iter
                       / self._n_trials * 100)
            pct = min(base + step, 99)
            text = (f"Trial {trial_idx+1}/{self._n_trials} "
                    f"迭代 {iteration}: 最大误差 {max_err:.4f}, "
                    f"均值误差 {mean_err:.4f}")
            self.signals.progress.emit(pct, text)

        result = WaveGenerator.generate(
            self._target, self._periods,
            n=self._n, dt=self._dt, zeta=self._zeta,
            pga=self._pga, tol=self._tol, max_iter=self._max_iter,
            progress_callback=progress_cb,
            n_trials=1,
        )
        acc = getattr(result, 'acc', None)
        logger.info("[%s] MultiTrial in-process trial=%s done name=%s len=%s",
                    self._job_id, trial_idx + 1,
                    getattr(result, 'name', '<unknown>'),
                    len(acc) if acc is not None else 0)
        return result

    def execute(self):
        from seiswave.core import WaveGenerator, Spectra

        all_results = []
        errors = []
        logger.info("[%s] MultiTrial execute start trials=%s algo=%s n=%s dt=%.5f periods=%s pga=%.4f tol=%.4f max_iter=%s",
                    self._job_id, self._n_trials, _algo_name(self._fm), self._n, self._dt, len(self._periods), self._pga, self._tol, self._max_iter)

        for t in range(self._n_trials):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            sig = self._run_single_trial(t)
            all_results.append(sig)
            spec = Spectra.compute(sig.acc, sig.dt,
                                   self._periods, self._zeta)
            fit = WaveGenerator.fit_error(spec.sa, self._target)
            errors.append(fit['mean_error'])
            logger.info("[%s] MultiTrial trial=%s fit mean_error=%.6f max_error=%.6f",
                        self._job_id, t + 1, fit.get('mean_error', float('nan')), fit.get('max_error', float('nan')))

        best_idx = int(np.argmin(errors))
        logger.info("[%s] MultiTrial best trial=%s errors=%s", self._job_id, best_idx + 1, [round(x, 6) for x in errors])
        self.signals.progress.emit(100, f"完成: 最优 Trial {best_idx+1}")
        return {
            'best': all_results[best_idx],
            'all_results': all_results,
            'best_index': best_idx,
        }


# ──────────── 文件加载 Worker ────────────


class FileLoadWorker(BaseWorker):
    """批量文件加载 Worker（后台线程，避免阻塞 GUI）"""

    def __init__(self, files, fmt_idx, parent=None):
        super().__init__(parent)
        self._files = files
        self._fmt_idx = fmt_idx

    def execute(self):
        from seiswave.core import EQSignal

        signals = []
        total = len(self._files)
        for i, f in enumerate(self._files):
            if self.is_cancelled:
                break
            try:
                if self._fmt_idx == 0:  # AT2
                    sig = EQSignal.from_at2(f)
                else:
                    sig = EQSignal.from_txt(f, dt=0.02,
                                            single_col=(self._fmt_idx == 1))
                signals.append(sig)
            except Exception:
                continue
            pct = int((i + 1) / total * 100)
            self.signals.progress.emit(pct, f"加载 {i+1}/{total}: {os.path.basename(f)}")
        return signals


# ──────────── 特殊地震动生成 Worker ────────────

class SpecialGroundMotionWorker(BaseWorker):
    """特殊地震动生成 Worker（FF / NF / NFP）

    在独立线程中调用 create_ground_motion()，避免阻塞 GUI。
    由于底层仍可能走 Fortran 路径，Fortran GIL 问题通过
    子进程方式在 GeneratorWorker 中解决；此处直接用线程
    是因为 create_ground_motion 内部已封装了子进程隔离
    （通过 WaveGenerator._generate_fortran 路径时，Fortran
    调用在独立进程中执行，但当前架构下 create_ground_motion
    走的是 Python 回退路径，线程安全）。
    """

    def __init__(self, gm_type, Mw, R, Vs30=760.0,
                 fault_type="strike_slip", n=4096, dt=0.02,
                 zeta=0.05, tol=0.05, max_iter=50, fm=0,
                 parent=None, job_id=None):
        super().__init__(parent, job_id=job_id)
        self._gm_type = gm_type
        self._Mw = Mw
        self._R = R
        self._Vs30 = Vs30
        self._fault_type = fault_type
        self._n = n
        self._dt = dt
        self._zeta = zeta
        self._tol = tol
        self._max_iter = max_iter
        self._fm = fm

    def execute(self):
        from seiswave.core.generator import create_ground_motion
        logger.info("[%s] SpecialGroundMotionWorker execute type=%s Mw=%.3f R=%.3f Vs30=%.1f fault=%s algo=%s n=%s dt=%.5f tol=%.4f max_iter=%s",
                    self._job_id, self._gm_type, self._Mw, self._R, self._Vs30,
                    self._fault_type, _algo_name(self._fm), self._n, self._dt,
                    self._tol, self._max_iter)

        def progress_cb(iteration, max_err, mean_err):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            pct = int(min(iteration / self._max_iter, 1.0) * 100)
            text = (f"迭代 {iteration}/{self._max_iter}: "
                    f"最大误差 {max_err:.4f}, 平均误差 {mean_err:.4f}")
            self.signals.progress.emit(pct, text)
            logger.info("[%s] SpecialGroundMotionWorker progress iter=%s max_err=%.6f mean_err=%.6f",
                        self._job_id, iteration, max_err, mean_err)

        result = create_ground_motion(
            type=self._gm_type,
            Mw=self._Mw,
            R=self._R,
            Vs30=self._Vs30,
            fault_type=self._fault_type,
            n=self._n,
            dt=self._dt,
            zeta=self._zeta,
            tol=self._tol,
            max_iter=self._max_iter,
            fm=self._fm,
            progress_callback=progress_cb,
        )
        acc = getattr(result, 'acc', None)
        logger.info("[%s] SpecialGroundMotionWorker done name=%s len=%s",
                    self._job_id,
                    getattr(result, 'name', '<unknown>'),
                    len(acc) if acc is not None else 0)
        return result


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

        self.signals.progress.emit(10, "检查索引缓存...")
        if not db.load_index():
            self.signals.progress.emit(20, "构建索引...")
            db.build_index()

        n = len(db)
        self.signals.progress.emit(40, f"已索引 {n} 条记录")

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


# ──────────── 向导流程 Workers ────────────


class PeerIndexWorker(BaseWorker):
    """PEER 数据库索引构建 Worker（仅建索引，不计算反应谱）"""

    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self._data_dir = data_dir

    def execute(self):
        from seiswave.core.peer_db import PeerDatabase

        db = PeerDatabase(data_dir=self._data_dir)

        self.signals.progress.emit(5, "检查索引缓存...")
        if db.load_index():
            self.signals.progress.emit(100, f"从缓存加载 {len(db)} 条记录")
            return db

        self.signals.progress.emit(10, "扫描 AT2 文件...")

        def progress_cb(i, total):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            pct = 10 + int(i / max(total, 1) * 80)
            self.signals.progress.emit(pct, f"索引 {i}/{total}")

        db.build_index(progress_cb=progress_cb)
        db.save_index()
        self.signals.progress.emit(100, f"索引完成: {len(db)} 条记录")
        return db


class SpectraPrecomputeWorker(BaseWorker):
    """反应谱批量预计算 Worker（需已建立索引的 PeerDatabase）"""

    def __init__(self, database, periods=None, zeta=0.05, parent=None):
        super().__init__(parent)
        self._db = database
        self._periods = periods
        self._zeta = zeta

    def execute(self):
        db = self._db
        zeta = self._zeta

        self.signals.progress.emit(5, "检查反应谱缓存...")
        if db.load_spectra_cache(zeta):
            n_cached = sum(1 for r in db.records if r.sa is not None)
            self.signals.progress.emit(100, f"从缓存加载 {n_cached} 条反应谱")
            return db

        periods = self._periods
        if periods is None:
            periods = np.linspace(0.04, 6.0, 200)

        self.signals.progress.emit(10, "预计算反应谱...")

        def progress_cb(i, total):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            pct = 10 + int(i / max(total, 1) * 85)
            self.signals.progress.emit(pct, f"反应谱 {i}/{total}")

        db.precompute_spectra(periods, zeta, progress_cb=progress_cb)
        self.signals.progress.emit(100, "反应谱预计算完成")
        return db


class SelectorWorker(BaseWorker):
    """选波 Worker（基于 SelectionConfig + PeerDatabase）"""

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
            pct = int(i / max(total, 1) * 100)
            self.signals.progress.emit(pct, f"选波筛选 {i}/{total}")

        results = selector.select(self._db, progress_cb=progress_cb)
        self.signals.progress.emit(100, f"选波完成: {len(results)} 条")
        return results


class CombinerWorker(BaseWorker):
    """组合输出 Worker（天然波 + 人工波 → 导出包）"""

    def __init__(self, results, database, generated_waves,
                 output_dir, fmt='at2', target_sa=None,
                 periods=None, parent=None):
        super().__init__(parent)
        self._results = results          # list[SelectionResult]
        self._db = database              # PeerDatabase
        self._generated = generated_waves  # list[EQSignal]
        self._output_dir = output_dir
        self._fmt = fmt
        self._target_sa = target_sa
        self._periods = periods

    def execute(self):
        from seiswave.core.combiner import Combiner

        combiner = Combiner(output_dir=self._output_dir)
        total = len(self._results) + len(self._generated)
        done = 0

        # 添加天然波
        for r in self._results:
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            combiner.add_natural(r, self._db)
            done += 1
            pct = int(done / max(total, 1) * 60)
            self.signals.progress.emit(pct, f"添加天然波 {done}/{len(self._results)}")

        # 添加人工波
        for i, sig in enumerate(self._generated):
            if self.is_cancelled:
                raise InterruptedError("用户取消")
            combiner.add_artificial(sig, name="artificial", index=i)
            done += 1
            pct = 60 + int((i + 1) / max(len(self._generated), 1) * 20)
            self.signals.progress.emit(pct, f"添加人工波 {i + 1}/{len(self._generated)}")

        # 导出
        self.signals.progress.emit(85, "导出文件...")
        combiner.export(fmt=self._fmt)

        # 生成报告（如果有目标谱）
        report_path = None
        if self._target_sa is not None and self._periods is not None:
            self.signals.progress.emit(92, "生成报告...")
            report_path = combiner.generate_html_report(
                self._target_sa, self._periods)

        self.signals.progress.emit(100, "组合输出完成")
        return {
            'combiner': combiner,
            'output_dir': self._output_dir,
            'report_path': report_path,
        }
