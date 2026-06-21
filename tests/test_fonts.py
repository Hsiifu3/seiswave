"""跨平台字体配置测试。"""

import matplotlib

from seiswave.gui.fonts import cjk_font, qt_font, setup_matplotlib_fonts


class TestFonts:
    def test_cjk_font_returns_songti_on_darwin(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        assert cjk_font() == "Songti SC"

    def test_cjk_font_returns_simsun_on_windows(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        assert cjk_font() == "SimSun"

    def test_cjk_font_returns_fallback_on_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        assert cjk_font() == "Noto Serif CJK SC"

    def test_setup_matplotlib_fonts_sets_family(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")

        setup_matplotlib_fonts()

        assert matplotlib.rcParams["font.family"] == [
            "Times New Roman",
            "Songti SC",
        ]
        assert matplotlib.rcParams["axes.unicode_minus"] is False

    def test_qt_font_uses_cjk_plus_times(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")

        font = qt_font()

        assert font.families()[:2] == ["SimSun", "Times New Roman"]
        assert font.pointSize() == 12
