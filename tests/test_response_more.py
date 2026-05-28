import numpy as np

from seiswave.core import EQSignal, Response


def _make_signal(dt=0.02, n=256):
    t = np.arange(n) * dt
    acc = 0.2 * np.sin(2 * np.pi * 1.5 * t)
    return EQSignal(acc, dt, name="resp")


class TestResponseMore:
    def test_calc_nonlinear_clough_and_takeda_private_models_run(self):
        sig = _make_signal()

        r1 = Response(sig, period=1.0)
        r1._calc_nonlinear(mu=2.0, model=1)
        assert np.any(r1.rd != 0)
        assert np.any(r1.rf != 0)

        r2 = Response(sig, period=1.0)
        r2._calc_nonlinear(mu=2.0, model=2)
        assert np.any(r2.rd != 0)
        assert np.any(r2.rf != 0)

    def test_plot_calls_matplotlib_pipeline(self, monkeypatch):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        r.calc()

        calls = []
        monkeypatch.setattr("seiswave.core.response.plt.figure", lambda *a, **k: calls.append(("figure", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.subplot", lambda *a, **k: calls.append(("subplot", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.plot", lambda *a, **k: calls.append(("plot", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.grid", lambda *a, **k: calls.append(("grid", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.ylabel", lambda *a, **k: calls.append(("ylabel", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.xlabel", lambda *a, **k: calls.append(("xlabel", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.title", lambda *a, **k: calls.append(("title", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.tight_layout", lambda *a, **k: calls.append(("tight_layout", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.show", lambda *a, **k: calls.append(("show", a, k)))

        r.plot(title="MyTitle")

        names = [c[0] for c in calls]
        assert names.count("subplot") == 4
        assert names.count("plot") == 4
        assert any(c[0] == "title" and c[1] == ("MyTitle",) for c in calls)
        assert names[-2:] == ["tight_layout", "show"]

    def test_plot_hysteresis_calls_axes_helpers(self, monkeypatch):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        r.calc(mu=2.0)

        calls = []
        monkeypatch.setattr("seiswave.core.response.plt.figure", lambda *a, **k: calls.append(("figure", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.plot", lambda *a, **k: calls.append(("plot", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.grid", lambda *a, **k: calls.append(("grid", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.xlabel", lambda *a, **k: calls.append(("xlabel", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.ylabel", lambda *a, **k: calls.append(("ylabel", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.title", lambda *a, **k: calls.append(("title", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.axhline", lambda *a, **k: calls.append(("axhline", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.axvline", lambda *a, **k: calls.append(("axvline", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.tight_layout", lambda *a, **k: calls.append(("tight_layout", a, k)))
        monkeypatch.setattr("seiswave.core.response.plt.show", lambda *a, **k: calls.append(("show", a, k)))

        r.plot_hysteresis()

        names = [c[0] for c in calls]
        assert "axhline" in names
        assert "axvline" in names
        assert any(c[0] == "title" and c[1] == ("滞回曲线",) for c in calls)
        assert names[-2:] == ["tight_layout", "show"]
