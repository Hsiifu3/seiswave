import warnings

from pyparsing.warnings import PyparsingDeprecationWarning


# Matplotlib currently imports deprecated pyparsing compatibility helpers on
# Python 3.9. Re-apply the filter in pytest_configure because pytest's warning
# plugin can reorder filters after module import.
def _suppress_matplotlib_pyparsing_warnings() -> None:
    warnings.filterwarnings("ignore", category=PyparsingDeprecationWarning)


_suppress_matplotlib_pyparsing_warnings()


def pytest_configure(config):
    _suppress_matplotlib_pyparsing_warnings()
