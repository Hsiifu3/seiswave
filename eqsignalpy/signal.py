"""
地震信号处理模块
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate
from .spectrum import EQSpectra
from .response import Response


class EQSignal:
    """地震信号类，用于处理地震加速度记录"""
    
    def __init__(self, acc=None, dt=0.02):
        """
        初始化地震信号对象
        
        参数:
            acc: 加速度数组
            dt: 时间步长，默认0.02秒
        """
        if acc is None:
            acc = np.zeros(1024)
        
        self.acc = np.asarray(acc)
        self.dt = dt
        self.n = len(self.acc)
        self.t = np.linspace(0.0, self.dt*self.n-self.dt, self.n)
        self.vel = np.zeros(self.n)
        self.dsp = np.zeros(self.n)
        
        # 初始条件
        self.v0 = 0.0
        self.d0 = 0.0

    @classmethod
    def from_file(cls, filename, dt=0.02):
        """
        从文件加载地震记录
        
        参数:
            filename: 文件名
            dt: 时间步长，默认0.02秒
        
        返回:
            EQSignal对象
        """
        try:
            acc = np.loadtxt(filename)
            return cls(acc, dt)
        except Exception as e:
            print(f"无法加载文件 {filename}: {e}")
            return cls()

    def acc2vd(self):
        """
        通过积分计算速度和位移
        """
        # 使用累积梯形积分计算速度
        self.vel = integrate.cumulative_trapezoid(self.acc, dx=self.dt, initial=self.v0)
        
        # 使用累积梯形积分计算位移
        self.dsp = integrate.cumulative_trapezoid(self.vel, dx=self.dt, initial=self.d0)
        
        return self.vel, self.dsp

    def compute_response_spectrum(self, zeta=0.05, periods=None):
        """
        计算反应谱
        
        参数:
            zeta: 阻尼比，默认5%
            periods: 周期数组，默认为None（使用对数分布的周期）
            
        返回:
            EQSpectra对象
        """
        if periods is None:
            periods = np.logspace(-1.3, 1, 30)  # 默认周期范围
        
        spectra = EQSpectra(self, zeta, periods)
        spectra.calc()
        return spectra

    def response(self, zeta=0.05, period=2.0, mu=None):
        """
        计算单自由度系统响应
        
        参数:
            zeta: 阻尼比，默认5%
            period: 周期，默认2.0秒
            mu: 屈服强度折减系数，默认None（线性响应）
            
        返回:
            Response对象
        """
        resp = Response(self, zeta, period)
        resp.calc(mu)
        return resp
        
    def filter(self, ftype='bandpass', order=4, freqs=(0.1, 25.0)):
        """
        使用巴特沃斯滤波器过滤信号
        
        参数:
            ftype: 滤波类型，'lowpass', 'highpass', 或 'bandpass'
            order: 滤波器阶数
            freqs: 截止频率，对于带通滤波器是一个元组(low, high)
            
        返回:
            过滤后的EQSignal对象
        """
        from scipy import signal
        
        nyq = 1.0 / (2.0 * self.dt)  # 奈奎斯特频率
        
        if ftype == 'bandpass':
            low, high = freqs
            low_norm = low / nyq
            high_norm = high / nyq
            b, a = signal.butter(order, [low_norm, high_norm], btype=ftype)
        else:
            freq_norm = freqs / nyq
            b, a = signal.butter(order, freq_norm, btype=ftype)
        
        filtered_acc = signal.filtfilt(b, a, self.acc)
        
        result = EQSignal(filtered_acc, self.dt)
        return result
    
    def baseline_correction(self, order_high=3, order_low=1):
        """
        基线校正
        
        参数:
            order_high: 高阶多项式校正阶数
            order_low: 低阶多项式校正阶数
            
        返回:
            校正后的EQSignal对象
        """
        # 创建时间向量
        t = np.arange(self.n) * self.dt
        
        # 拟合多项式
        poly_coeffs = np.polyfit(t, self.acc, order_high)
        
        # 移除低频趋势
        trend = np.polyval(poly_coeffs[:order_low+1], t)
        corrected_acc = self.acc - trend
        
        result = EQSignal(corrected_acc, self.dt)
        return result
    
    def resample(self, new_dt=None, new_n=None):
        """
        重采样信号
        
        参数:
            new_dt: 新的时间步长
            new_n: 新的采样点数
            
        返回:
            重采样后的EQSignal对象
        """
        from scipy import signal
        
        if new_dt is not None and new_n is None:
            # 计算新的采样点数
            new_n = int(self.n * self.dt / new_dt)
        
        if new_n is not None:
            # 使用信号重采样函数
            new_t = np.linspace(0, self.t[-1], new_n)
            new_acc = signal.resample(self.acc, new_n)
            
            if new_dt is None:
                new_dt = self.t[-1] / (new_n - 1)
            
            result = EQSignal(new_acc, new_dt)
            return result
        
        return self
    
    def plot(self, title="地震时程"):
        """
        绘制加速度、速度和位移时程
        
        参数:
            title: 图表标题
        """
        plt.figure(figsize=(10, 8))
        
        plt.subplot(3, 1, 1)
        plt.plot(self.t, self.acc)
        plt.grid(True)
        plt.ylabel('加速度')
        plt.title(title)
        
        plt.subplot(3, 1, 2)
        plt.plot(self.t, self.vel)
        plt.grid(True)
        plt.ylabel('速度')
        
        plt.subplot(3, 1, 3)
        plt.plot(self.t, self.dsp)
        plt.grid(True)
        plt.xlabel('时间(s)')
        plt.ylabel('位移')
        
        plt.tight_layout()
        plt.show()
        
    def normalize(self, peak_acc=1.0):
        """
        将加速度记录归一化到指定峰值
        
        参数:
            peak_acc: 目标峰值加速度
            
        返回:
            归一化后的EQSignal对象
        """
        current_peak = np.max(np.abs(self.acc))
        scale_factor = peak_acc / current_peak
        
        normalized_acc = self.acc * scale_factor
        
        result = EQSignal(normalized_acc, self.dt)
        return result
    
    def __len__(self):
        """返回信号长度"""
        return self.n
    
    def __str__(self):
        """字符串表示"""
        return f"EQSignal(n={self.n}, dt={self.dt}, duration={self.n*self.dt:.2f}s)"
    
    def __repr__(self):
        """表示方法"""
        return self.__str__() 