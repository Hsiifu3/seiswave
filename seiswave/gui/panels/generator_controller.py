"""生成逻辑编排"""

import logging
import uuid

from PySide6.QtCore import QObject, Signal

from seiswave.gui.workers import MultiTrialGeneratorWorker, SpecialGroundMotionWorker

logger = logging.getLogger(__name__)


class GeneratorController(QObject):
    """根据类型分发到正确 Worker，连接信号"""

    progress = Signal(int, str)
    finished = Signal(object, str)   # (result, type_label)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._job_id = None

    # ── 一般人工波 ──

    def run_general(self, param_form, code_periods, code_sa):
        """一般人工波生成（多 trial）"""
        params = param_form.get_params()
        self._job_id = uuid.uuid4().hex[:8]
        # 一般人工波的目标 PGA 必须与当前规范谱一致，不能依赖手填值。
        target_pga = float(max(code_sa)) if code_sa is not None and len(code_sa) > 0 else params['pga']
        logger.info("[%s] Controller run_general params=%s target_points=%s target_pga=%.4f",
                    self._job_id,
                    {
                        'n': params['n'], 'dt': params['dt'], 'zeta': params['zeta'],
                        'tol': params['tol'], 'max_iter': params['max_iter'],
                        'n_trials': params['n_trials'], 'fm': params.get('fm', 0),
                    },
                    0 if code_periods is None else len(code_periods),
                    target_pga)
        self._worker = MultiTrialGeneratorWorker(
            code_sa, code_periods,
            n=params['n'],
            dt=params['dt'],
            zeta=params['zeta'],
            pga=target_pga,
            tol=params['tol'],
            max_iter=params['max_iter'],
            n_trials=params['n_trials'],
            fm=params.get('fm', 0),
            parent=self,
            job_id=self._job_id,
        )
        self._worker.signals.progress.connect(self.progress.emit)
        self._worker.signals.finished.connect(
            lambda r: self._log_finished(r, "一般人工波") or self.finished.emit(r, "一般人工波"))
        self._worker.signals.error.connect(self.error.emit)
        logger.info("[%s] Controller starting worker=%s", self._job_id, self._worker.__class__.__name__)
        self._worker.start()

    def _log_finished(self, result, label):
        """记录 Worker 返回结果的关键指标"""
        try:
            if isinstance(result, dict) and 'best' in result:
                best = result['best']
                best_sa = result.get('best_sa')
                target_sa = result.get('target_sa')
                err_info = ""
                if best_sa is not None and target_sa is not None:
                    err = (np.abs(best_sa) - np.abs(target_sa)) / np.maximum(np.abs(target_sa), 1e-30)
                    err_info = f" mean_err={float(np.sqrt(np.mean(err**2)))*100:.1f}% max_err={float(np.max(np.abs(err)))*100:.1f}%"
                logger.info("[%s] Controller finished label=%s PGA=%.4f trials=%s%s",
                            self._job_id, label,
                            float(np.max(np.abs(best.acc))) if hasattr(best, 'acc') else 0,
                            result.get('n_trials', 1), err_info)
            else:
                # 特殊地震动（EQSignal）或单结果
                pga = 0.0
                err_info = ""
                if hasattr(result, 'acc'):
                    pga = float(np.max(np.abs(result.acc)))
                if hasattr(result, 'total_spectrum') and hasattr(result, 'spectrum_periods') and result.total_spectrum is not None:
                    from seiswave.core.generator import WaveGenerator
                    from seiswave.core.spectrum import Spectra
                    spec = Spectra.compute(result.acc, result.dt, result.spectrum_periods, 0.05, method='mixed')
                    fit = WaveGenerator.fit_error(spec.sa, result.total_spectrum)
                    err_info = f" mean_err={fit['mean_error']*100:.2f}% max_err={fit['max_error']*100:.2f}%"
                logger.info("[%s] Controller finished label=%s PGA=%.4f result_type=%s%s",
                            self._job_id, label, pga, type(result).__name__, err_info)
        except Exception:
            pass
        return None

    # ── 特殊地震动 ──

    def run_special(self, param_form, code_periods, code_sa):
        """特殊地震动生成（FF / NF / NFP）"""
        params = param_form.get_params()
        self._job_id = uuid.uuid4().hex[:8]
        gm_type = params['type_code']
        label = params['type_label']
        # 特殊地震动使用用户选择的算法（默认频域法 fm=0）
        fm = params.get('fm', 0)

        logger.info("[%s] Controller run_special label=%s gm_type=%s params=%s",
                    self._job_id, label, gm_type,
                    {
                        'Mw': params['Mw'], 'R': params['R'], 'Vs30': params['Vs30'],
                        'fault_type': params['fault_type'], 'n': params['n'], 'dt': params['dt'],
                        'zeta': params['zeta'], 'tol': params['tol'], 'max_iter': params['max_iter'],
                        'fm': fm, 'spectrum_source': params.get('spectrum_source', 'code'),
                    })
        self._worker = SpecialGroundMotionWorker(
            gm_type=gm_type,
            Mw=params['Mw'],
            R=params['R'],
            Vs30=params['Vs30'],
            fault_type=params['fault_type'],
            n=params['n'],
            dt=params['dt'],
            zeta=params['zeta'],
            tol=params['tol'],
            max_iter=params['max_iter'],
            fm=fm,
            spectrum_source=params.get('spectrum_source', 'code'),
            code_periods=code_periods,
            code_sa=code_sa,
            region=params.get('region', '东部强震区'),
            axis=params.get('axis', '长轴'),
            parent=self,
            job_id=self._job_id,
        )
        self._worker.signals.progress.connect(self.progress.emit)
        self._worker.signals.finished.connect(
            lambda r: self._log_finished(r, label) or self.finished.emit(r, label))
        self._worker.signals.error.connect(self.error.emit)
        logger.info("[%s] Controller starting worker=%s", self._job_id, self._worker.__class__.__name__)
        self._worker.start()

    def cancel(self):
        """取消当前运行中的 Worker"""
        if self._worker is not None:
            logger.info("[%s] Controller cancel worker=%s", self._job_id, self._worker.__class__.__name__)
            self._worker.cancel()
