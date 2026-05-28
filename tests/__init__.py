import warnings

from pyparsing.warnings import PyparsingDeprecationWarning


warnings.filterwarnings(
    "ignore",
    category=PyparsingDeprecationWarning,
)
