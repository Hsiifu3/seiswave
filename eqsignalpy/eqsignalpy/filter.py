"""
信号滤波模块
"""

import numpy as np
from scipy import signal


class Filter:
    """信号滤波类，提供多种滤波方法"""
    
    @staticmethod
    def butterworth(acc, dt, ftype='bandpass', order=4, freqs=(0.1, 25.0)):
        """
        巴特沃斯滤波器
        
        参数:
            acc: 加速度数组
            dt: 时间步长
            ftype: 滤波类型，'lowpass', 'highpass', 或 'bandpass'
            order: 滤波器阶数
            freqs: 截止频率，对于带通滤波器是一个元组(low, high)
            
        返回:
            过滤后的加速度数组
        """
        nyq = 1.0 / (2.0 * dt)  # 奈奎斯特频率
        
        if ftype == 'bandpass':
            low, high = freqs
            low_norm = low / nyq
            high_norm = high / nyq
            b, a = signal.butter(order, [low_norm, high_norm], btype=ftype)
        else:
            freq_norm = freqs / nyq
            b, a = signal.butter(order, freq_norm, btype=ftype)
        
        # 使用零相位滤波
        filtered_acc = signal.filtfilt(b, a, acc)
        
        return filtered_acc
        
    @staticmethod
    def chebyshev(acc, dt, ftype='bandpass', order=4, freqs=(0.1, 25.0), rp=3):
        """
        切比雪夫I型滤波器
        
        参数:
            acc: 加速度数组
            dt: 时间步长
            ftype: 滤波类型，'lowpass', 'highpass', 或 'bandpass'
            order: 滤波器阶数
            freqs: 截止频率，对于带通滤波器是一个元组(low, high)
            rp: 通带纹波，单位dB
            
        返回:
            过滤后的加速度数组
        """
        nyq = 1.0 / (2.0 * dt)  # 奈奎斯特频率
        
        if ftype == 'bandpass':
            low, high = freqs
            low_norm = low / nyq
            high_norm = high / nyq
            b, a = signal.cheby1(order, rp, [low_norm, high_norm], btype=ftype)
        else:
            freq_norm = freqs / nyq
            b, a = signal.cheby1(order, rp, freq_norm, btype=ftype)
        
        # 使用零相位滤波
        filtered_acc = signal.filtfilt(b, a, acc)
        
        return filtered_acc
    
    @staticmethod
    def elliptic(acc, dt, ftype='bandpass', order=4, freqs=(0.1, 25.0), rp=3, rs=40):
        """
        椭圆滤波器
        
        参数:
            acc: 加速度数组
            dt: 时间步长
            ftype: 滤波类型，'lowpass', 'highpass', 或 'bandpass'
            order: 滤波器阶数
            freqs: 截止频率，对于带通滤波器是一个元组(low, high)
            rp: 通带纹波，单位dB
            rs: 阻带衰减，单位dB
            
        返回:
            过滤后的加速度数组
        """
        nyq = 1.0 / (2.0 * dt)  # 奈奎斯特频率
        
        if ftype == 'bandpass':
            low, high = freqs
            low_norm = low / nyq
            high_norm = high / nyq
            b, a = signal.ellip(order, rp, rs, [low_norm, high_norm], btype=ftype)
        else:
            freq_norm = freqs / nyq
            b, a = signal.ellip(order, rp, rs, freq_norm, btype=ftype)
        
        # 使用零相位滤波
        filtered_acc = signal.filtfilt(b, a, acc)
        
        return filtered_acc
    
    @staticmethod
    def baseline_correction(acc, dt, order_high=3, order_low=1):
        """
        基线校正
        
        参数:
            acc: 加速度数组
            dt: 时间步长
            order_high: 高阶多项式校正阶数
            order_low: 低阶多项式校正阶数
            
        返回:
            校正后的加速度数组
        """
        n = len(acc)
        t = np.arange(n) * dt
        
        # 拟合多项式
        poly_coeffs = np.polyfit(t, acc, order_high)
        
        # 移除低频趋势
        trend = np.polyval(poly_coeffs[:order_low+1], t)
        corrected_acc = acc - trend
        
        return corrected_acc
    
    @staticmethod
    def moving_average(acc, window_size=5):
        """
        移动平均滤波
        
        参数:
            acc: 加速度数组
            window_size: 窗口大小
            
        返回:
            平滑后的加速度数组
        """
        return np.convolve(acc, np.ones(window_size)/window_size, mode='same')
    
    @staticmethod
    def fft_filter(acc, dt, cutoff_low=0.1, cutoff_high=25.0):
        """
        基于FFT的频域滤波
        
        参数:
            acc: 加速度数组
            dt: 时间步长
            cutoff_low: 低截止频率
            cutoff_high: 高截止频率
            
        返回:
            过滤后的加速度数组
        """
        n = len(acc)
        
        # 执行FFT
        fft_result = np.fft.fft(acc)
        freqs = np.fft.fftfreq(n, dt)
        
        # 创建频域滤波器
        fft_filter = np.ones(n)
        fft_filter[np.abs(freqs) < cutoff_low] = 0
        fft_filter[np.abs(freqs) > cutoff_high] = 0
        
        # 应用滤波器
        filtered_fft = fft_result * fft_filter
        
        # 反变换回时域
        filtered_acc = np.real(np.fft.ifft(filtered_fft))
        
        return filtered_acc 