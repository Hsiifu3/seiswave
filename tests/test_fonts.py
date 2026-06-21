"""跨平台字体配置测试。"""

import matplotlib
import pytest

import seiswave.gui.fonts as fonts


class TestFonts:
    def test_cjk_font_returns_songti_on_darwin(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr(fonts, "_available_font_families", lambda: set())
        assert fonts.cjk_font() == "Songti SC"

    def test_cjk_font_returns_simsun_on_windows(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(fonts, "_available_font_families", lambda: set())
        assert fonts.cjk_font() == "SimSun"

    def test_cjk_font_returns_fallback_on_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(fonts, "_available_font_families", lambda: set())
        assert fonts.cjk_font() == "Noto Serif CJK SC"

    @pytest.mark.parametrize("platform_name", ["win32", "darwin"])
    def test_cjk_font_falls_back_to_noto_when_platform_font_missing(
        self,
        monkeypatch,
        platform_name,
    ):
        monkeypatch.setattr("sys.platform", platform_name)
        monkeypatch.setattr(
            fonts,
            "_available_font_families",
            lambda: {"Noto Serif CJK SC", "Times New Roman"},
        )

        assert fonts.cjk_font() == "Noto Serif CJK SC"

    def test_setup_matplotlib_fonts_sets_family(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr(
            fonts,
            "_available_font_families",
            lambda: {"Songti SC", "Times New Roman"},
        )

        fonts.setup_matplotlib_fonts()

        assert matplotlib.rcParams["font.family"] == [
            "Times New Roman",
            "Songti SC",
        ]
        assert matplotlib.rcParams["font.serif"] == [
            "Times New Roman",
            "Songti SC",
        ]
        assert matplotlib.rcParams["axes.unicode_minus"] is False

    def test_qt_font_uses_same_fallback_chain(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            fonts,
            "_available_font_families",
            lambda: {"Noto Serif CJK SC", "Times New Roman"},
        )

        font = fonts.qt_font()

        assert font.families()[:2] == ["Noto Serif CJK SC", "Times New Roman"]
        assert font.pointSize() == 12
