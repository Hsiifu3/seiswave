import numpy as np

from seiswave.gui.workers import GeneratorWorker


def _target_spectrum():
    periods = np.linspace(0.04, 6.0, 80)
    target = np.ones_like(periods) * 0.2
    return target, periods


def test_generator_worker_fallback_when_process_start_fails(monkeypatch):
    """当 multiprocessing 子进程无法启动时，应自动回退并仍可生成人工波。"""
    target, periods = _target_spectrum()

    class BadProcess:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("spawn bootstrap failed")

        def is_alive(self):
            return False

        def terminate(self):
            pass

    import seiswave.gui.workers as workers_mod
    monkeypatch.setattr(workers_mod.mp, "Process", BadProcess)

    worker = GeneratorWorker(target, periods, n=1024, dt=0.02, pga=0.2, max_iter=6)
    result = worker.execute()

    assert result is not None
    assert len(result.acc) == 1024
    assert result.dt == 0.02
    assert np.isclose(result.pga, 0.2, atol=1e-2)
