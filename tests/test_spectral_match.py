"""Spectral-match extraction regression tests."""

from __future__ import annotations

import base64
import zlib

import numpy as np

from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.generator import WaveGenerator, create_ground_motion
from seiswave.core.signal_pool import SignalRecord
from seiswave.core.spectral_match import match_to_target
from seiswave.core.spectrum import Spectra


_GOLDEN = {
    "general": {
        "dt": 0.02,
        "n": 128,
        "b64": (
            "eNoBAAT/+zfbMG7ph6s/fNdEw3swpD/peHJ7Z/+hP6qNBHkp4o2/fAZ/32J/lz8y"
            "qAWgW+2jP8eW+P/caqM/ly9mGQ46rj/MCqvL4sitP7rwv5pWTKk/ts+nuge4pT+2"
            "wDw2GvaCP4A/PeMzjVw/4DHseSfeUD8mWWOF31mTv6HaD+KDbJ+/dzm0LhDIlD9C"
            "wb0+RW2kP+c9WQ0MpqE/byPQWCkdrz8cFCHBgLy4P8EQmN3TRLE/d4oIGi1ktD/1"
            "sQyzxziuP5BD60xjxV+/77RPjGUvf78sn51Xlv6hv8mKxN1KEZ2/ibgO4xB/kD9A"
            "IOldjSKkP6p8ljssuZY/pu4W8Qvosb8mRTmhcF+Qv4Rtm+DNFog/aLRbzYpliT9c"
            "Bam6BHSIv57PzDe1HpQ/sOlZ+mEEWz8oTxZ44VpXvz2Ai9ac75g/XOmNHG7Ab7/L"
            "g34Zz/mdP6w9o433cqY/EnWn7IK8oz8ylGi80hGrP5oGs/q7waE/kMlQ2AiqtD8K"
            "taOzDMqkP1RD/YmZl4i/F2cnohhvgz9WW9w7ofyHP+6EWQzJKpI/LqVgFnKGpD/M"
            "RHYd/sKwP0bFzgOZU5c/VqtjGCLIpj8sM+57xctUP4jJc8F06ac/FK3XeLG9oT9B"
            "2yw497ugvzc8nmKPM6i/v0Gcv+8ygb+glaCAZHNSv5DftnHUIZu/weEvk60hqL/i"
            "eRp0nLymv8AyPUXMR2W/UkH90RZ7nj9uJ1D2PjeBPyFffMFDhY+/rQQW1kNGmL94"
            "DzllD4CTv7YIFGiOrJm/OGxEj8REkb8Q6JY6r/tmvzAFAGE/EU8/JtuuMnB3gD9o"
            "2JS0zuuVP0uMy0jziZo/FpQDTxhflj+HvBUO09qIP764wNlEmHw/6dmIym/4ej/L"
            "Qxnrnq2DP97vfLQpaIY/bOLbgcqXjT9rIYCM9Kh+P6CNoSQH/mk/+B0EUCsxcb+n"
            "bD6JBeGQvwhOGrneoaC/3qUtahE6qb8mu5DtGQCqv1IZkpK13aW/XScuJS8Kn7/K"
            "u0EVs0GUv4RuyMYEJ2W/nnM8S2uUiT9G2QX15TucPxNPuL3sL6I/pYaJyPwooz+M"
            "fQP6AEmjP9Z2Cntp26E///V7xdEInj+RB9zcMFyWP7i+YlJ2Z40/dF810Dc5eT+d"
            "+jzLuwhwvzvRSAR/zIy/Vpui/u94mb9916I8bWSgv3dm8fTY1KK/HUOMHJwKo78B"
            "cfYNfzGfv6I0qBaeRZS/6KiO0j4Lfb/2jyRqY5pxP+h/4lYk1Yw/CSvIkeaslD/F"
            "4wbtVzqTPy9bnCryHIk/zN5gi3QnYD+WTpL0J3aEvyzJafRkYpW/mE7kWL2fnr/8"
            "ePJlUA2iv/GLzF3xHaO/GILBFItvo7/BfP2K"
        ),
    },
    "ff": {
        "dt": 0.02,
        "n": 128,
        "b64": (
            "eNoBAAT/+ydijtnJcZM/iLx/e2lZlj+ufJas4QCUP8A1ViMvgIg/SJbvLtInNz/N"
            "oesHs1OKv6Ec5tTJ9Zi/Y9PElHsqoL/Hq2u93kOgv+G+8/T0Y5m/qAqiXwf+h782"
            "HNFVvENuP13FdVXqZ5M/1mzDglahnj8dlvCoH/igP3eY5VVJTp0/VN7mfkrnkz99"
            "5yC//+B2PzDCS5VV1YK/SAkGGiYUlL+NNETXIseYv7rkJx1J+Jm/+R3T4RkAlL/w"
            "yW/odpiHv3AyPw9uznC/UEp2F+8+cz/0ePF6oWmCP54aRWqjAYo/nXz+5cJSlD+8"
            "35kxepmTPyHuadgWZI4/b6F9zo/WgT+Og6Am3xJ/PwQfHhs5wnk/TdRYKv6dYT/v"
            "BXNVTr1YP+4Q7JJrP3K/CrkU3TIVjr9+eY4E7zWKv2i1e+ir2H6/jL2ip33yY78r"
            "XcXs40ltP3bgN8sJ9ZA/AqxjQmwJlD85xNVaZF6GP2ji4IVLKI8/RveJJSe+hD96"
            "NN7RcVKHP2Az2nV1UoU/8jBC82Cshj8oQFjGyttLP/eZkVKhaW8/rpUHnkNXcT82"
            "lyeC372KP8YJV3RNrJM/Nfbp3MyNjz+KAGwH/DeUPyDcnyva+JQ/CFGbCbKVgj+b"
            "D6dQzHmFPwVzdCD6ZJA/wbnJoDOChD/vYagXp+B+P34t2vQ3YXi/rhV1A80blr+z"
            "zo3nFnecv6+R4g2ALJq/a9SJ0w0AoL8od3GqOKipvwCLbK38Aqu/cLX1SzIsrr96"
            "CqR7rJmuv2D9AUQCMrK/GBOtTJWHsr+rGokVzJWuv7s9tlxV8qe/fus95aaSl7/N"
            "NO3kl/6BP/i8kH3gzJg/3qEQxBQpmT+zpQX0np1+P4cI+TVb9Xq/hymHa61Iir/E"
            "yYxStm98vw4Ye3Dp7FW/v3D+ZpECij8kwF9v5ulpvwrIH2yfvHU/QRUPWJrPiz+S"
            "8uXsfxiNPyDxEU2bv5K/QT/AVTjrsb/BjUYJHZCwv8xpf/dytqK/VExzQRtpdL+h"
            "NFrY79Cfv9Pf+vOPRJe/ixpGNP1fmL9S8pzaariDP9P1ApTyl5c/bbg11U4ejD+W"
            "/FtigQCQP2I4Bd8bnIg/xAIXKdhBY78OrYGsrIOdv9Jk/1kzYqa/PFsSWFiJqL+o"
            "a9LdtI6rvz/fMRDLtaS/AYORssGYpb89Ax0Aq8iJv58KUhID4o2/OrRxxpcqo7/8"
            "Mn2XMluYv2rM9iL6gJO/AEBRvkHePD/Ei3bGOISbv2rCc63b+oa/4oJ7wniUrD90"
            "SqqEDi97P3NynBZo7oS/LUj+vg/4iL+VIeRCftKCvxKGNRy1FaI/I6ooNb+FqT/L"
            "wjAf72SyPwOW612Bcpo/wLl2dyelWD9bTAa7"
        ),
    },
    "nf": {
        "dt": 0.01,
        "n": 128,
        "b64": (
            "eNoBAAT/+7GcVCP5pKK/tRzN+oM5oj/uEbcbjFWoP+Ir8me55aE/tMSmG9Waoj+t"
            "veK6i4+rPwjJMYqvy7E/H+hQeVxusD9P9RNLnRKdP6DCjZdIjJe/Eaa9nq7crL/T"
            "sZP+ABusv4VBiMk0VaW/EHigx9y2pb9gTgjhkgWlv51fx+uoQJe/9CpalkqIZ7/c"
            "oUiEwst7P7ltIf0YjI8/DK7JfYOlnz9zXsva+JSmP2w4Fn8gQqQ/B3HTYS0ilD9i"
            "MNEm7JN2v1oXXCZ8Epu/QECnnhpzo78UhMnQzyGlv8XuN3n+UqK/uKUkAd+cl7+m"
            "3DHaaweHv/5r0Y3Qima/somSWPgXRD/OHQfjye9aP0jQKrCQjxk/Vgvb7sT4ar+/"
            "P2kiTZ9yv8XMvi0qnXu/1J5qHOBJhL+moDdRpb19v9AoLfh4h2u/j+Tqm79vPj8n"
            "2HCmtc5yP6Ey9lRh+og/d85mUnUejj/rchapB8SFPyGIg4/T0Ys/EtJx6IEchT8Q"
            "WhtDQ0GFP9Piixc+QIA/RucpxxIoeD/UK5yVR5pxv2AssrJnBX2/ScJDoT2Tir9i"
            "hpxMakCLv29srap9642/wrQ+e1Vhlr8gtVSDY+iWv2SQ6DkGEZi/SMq5t7QCoL/n"
            "GuFtcqycv+abycEe3pS/CoY7kSOrlL9c9Rd0BYaPv8vqHMLJcpK/OvnIw10ylr/d"
            "z5WuQeCSvxj2Mpgt8oG/DySfpwZxdb9wj+ZpGyGNv8mhXYwHBYm/4bfLfLMlkr8H"
            "1NT/qb2Uv0PSHHVWaKG/qC7Yn+NbpL8Xzln7ueCgv6/R/QgfU5m/iFPR+72Gd7/1"
            "r/goZCqUP8zZZOMaZ5w/38ZdZ8Lllj+3rk345JdjPzGfkJdHSYa/g7Rsto8wjr/X"
            "d7gQM0mAv6TtVykRtHG/W1DSsvBKij8FThJrWM9ZvwHSixu/5GI/gZdGHjWJaj81"
            "vR2RZzl8vyVwBNr2+p+/gRWAvbsitL8rTQZEIMOyv4xB3k3B3am/T15Z61tkob/s"
            "yxTqQ++wv6aVF32IC6+/s9sQ+DESsr+fnJtcraynvwBtx3Otqqi/6uNT0XMGsr8R"
            "xDvCe+qxv72hh/lG07K/b8+NBKVttr/I+PuLRu68v770FK5HKb+/SsZv/mtbv7/W"
            "qMYzZa3BvyqqwhcyQsG/zORMkQjJw7/5GoV1Da+9v+WV/RBcCLm/o190Ni81t79E"
            "QTgBH7CWv3rvI7VMyJQ/9tib2Egzpz/fqPas1XSVP7uKdRPLM5Y/g86+iT40pD9S"
            "QHVmOXKXv2CrKYP3DqM/SJKrpuFMsj83tsjQxGxmP7GsjAVaDbA/uRpb4XN+vT/J"
            "pIMPsvu8P/feL7ThfcE/YRpctgqgzj/IhhqR"
        ),
    },
}


def _decode(payload: dict[str, object]) -> np.ndarray:
    raw = zlib.decompress(base64.b64decode(payload["b64"]))
    arr = np.frombuffer(raw, dtype=np.float64).copy()
    assert len(arr) == payload["n"]
    return arr


def _target():
    periods = Spectra.default_periods(0.04, 3.0, 60, mode="mixed")
    params = CodeSpectrum.get_params(
        intensity=8,
        group=2,
        site_class="II",
        level="frequent",
    )
    target_sa = CodeSpectrum.gb50011(
        periods,
        params["Tg"],
        params["alpha_max"],
        zeta=0.05,
    )
    return periods, target_sa


def test_match_to_target_general_regression_matches_pre_extract_golden():
    periods, target_sa = _target()
    sig = WaveGenerator.generate(
        target_spectrum=target_sa,
        periods=periods,
        n=128,
        dt=0.02,
        zeta=0.05,
        pga=float(np.max(target_sa)),
        tol=0.05,
        max_iter=6,
        fm=1,
        n_trials=1,
    )
    np.testing.assert_allclose(sig.acc, _decode(_GOLDEN["general"]))


def test_match_to_target_ff_regression_matches_pre_extract_golden():
    periods, target_sa = _target()
    sig = create_ground_motion(
        "FF",
        Mw=7.0,
        R=50.0,
        n=128,
        dt=0.02,
        max_iter=4,
        spectrum_source="code",
        code_periods=periods,
        code_sa=target_sa,
    )
    np.testing.assert_allclose(sig.acc, _decode(_GOLDEN["ff"]))


def test_match_to_target_nf_regression_matches_pre_extract_golden():
    periods, target_sa = _target()
    sig = create_ground_motion(
        "NF",
        Mw=7.0,
        R=8.0,
        n=128,
        dt=0.01,
        max_iter=4,
        spectrum_source="code",
        code_periods=periods,
        code_sa=target_sa,
    )
    np.testing.assert_allclose(sig.acc, _decode(_GOLDEN["nf"]))


def test_match_to_target_improves_natural_wave_rmse():
    periods, target_sa = _target()
    time = np.linspace(0.0, 8.0, 801)
    acc = 0.18 * np.sin(2.0 * np.pi * 1.0 * time) + 0.06 * np.sin(
        2.0 * np.pi * 3.0 * time + 0.3
    )
    record = SignalRecord(acc=acc, dt=float(time[1] - time[0]), name="natural", kind="natural")

    before = WaveGenerator.fit_error(
        record.spectrum(periods, zeta=0.05).sa,
        target_sa,
    )["mean_error"]
    matched = match_to_target(
        record.acc,
        record.dt,
        periods,
        target_sa,
        zeta=0.05,
        tol=0.05,
        max_iter=20,
    )
    after = WaveGenerator.fit_error(
        Spectra.compute(matched, record.dt, periods, zeta=0.05).sa,
        target_sa,
    )["mean_error"]

    assert after < before
    assert after < 0.10
