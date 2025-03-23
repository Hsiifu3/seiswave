"""
EQSignalPy库 - 地震信号处理工具包

这个库封装了EQSignal的功能，提供了一组用于地震信号处理的工具。
"""

from .signal import EQSignal
from .spectrum import EQSpectra
from .response import Response
from .filter import Filter
from .generator import EQGenerator

__version__ = "0.1.0" 