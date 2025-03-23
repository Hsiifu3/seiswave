"""
人工地震动生成模块
"""

import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from .signal import EQSignal


class EQGenerator:
    """人工地震动生成类"""
    
    @staticmethod
    def generate_white_noise(n=1024, dt=0.02):
        """
        生成白噪声信号
        
        参数:
            n: 数据点数
            dt: 时间步长
            
        返回:
            EQSignal对象
        """
        # 生成随机白噪声
        noise = np.random.normal(0, 1, n)
        
        # 创建EQSignal对象
        eq = EQSignal(noise, dt)
        
        return eq
    
    @staticmethod
    def generate_from_spectrum(target_spectrum, n=1024, dt=0.02, zeta=0.05):
        """
        根据目标反应谱生成人工地震波
        
        参数:
            target_spectrum: 目标反应谱，格式为(periods, accelerations)的元组
            n: 数据点数
            dt: 时间步长
            zeta: 阻尼比
            
        返回:
            EQSignal对象
        """
        periods, accelerations = target_spectrum
        
        # 生成白噪声作为初始波形
        eq_noise = EQGenerator.generate_white_noise(n, dt)
        
        # 频域分析和调整
        acc = EQGenerator._adjust_spectrum(eq_noise.acc, dt, zeta, periods, accelerations, n)
        
        # 创建新的EQSignal对象
        eq = EQSignal(acc, dt)
        
        return eq
    
    @staticmethod
    def _adjust_spectrum(noise, dt, zeta, periods, target_spectrum, n):
        """
        调整信号以匹配目标反应谱
        
        参数:
            noise: 初始噪声信号
            dt: 时间步长
            zeta: 阻尼比
            periods: 周期数组
            target_spectrum: 目标加速度反应谱
            n: 数据点数
            
        返回:
            调整后的加速度时程
        """
        # 计算FFT
        n_fft = 2 ** int(np.ceil(np.log2(n)))
        noise_fft = np.fft.fft(noise, n_fft)
        
        # 频率数组
        freqs = np.fft.fftfreq(n_fft, dt)
        
        # 周期对应的频率
        freq_periods = 1.0 / periods
        
        # 计算传递函数并调整频谱
        for i in range(1, n_fft // 2):
            freq = freqs[i]
            if freq > 0:
                # 找到最接近的目标谱值
                idx = np.abs(freq_periods - freq).argmin()
                target_sa = target_spectrum[idx]
                
                # 计算传递函数
                omega = 2.0 * np.pi * freq
                h_squared = 1.0 / ((1.0 - (omega ** 2) * (periods[idx] ** 2) / (4.0 * np.pi ** 2)) ** 2 + 
                                   (2.0 * zeta * omega * periods[idx] / (2.0 * np.pi)) ** 2)
                
                # 调整幅值
                amplitude = np.abs(noise_fft[i])
                if amplitude > 0:
                    scaling = target_sa / (amplitude * np.sqrt(h_squared))
                    noise_fft[i] *= scaling
                    noise_fft[n_fft - i] = np.conj(noise_fft[i])  # 保持共轭对称
        
        # 逆FFT回时域
        adjusted_acc = np.real(np.fft.ifft(noise_fft))[:n]
        
        return adjusted_acc
    
    @staticmethod
    def generate_artificial_eq(n=1024, dt=0.02, t_rise=5.0, t_strong=10.0, t_total=30.0, 
                              freq_range=(0.5, 10.0), amplitude=1.0):
        """
        生成具有典型包络形状的人工地震波
        
        参数:
            n: 数据点数
            dt: 时间步长
            t_rise: 上升段时间
            t_strong: 强震段时间
            t_total: 总时长
            freq_range: 频率范围 (min_freq, max_freq)
            amplitude: 峰值加速度
            
        返回:
            EQSignal对象
        """
        # 检查参数
        if t_total < t_rise + t_strong:
            t_total = t_rise + t_strong + 5.0
        
        # 设置实际的数据点数
        actual_n = int(t_total / dt)
        if actual_n > n:
            actual_n = n
        
        # 时间数组
        t = np.arange(actual_n) * dt
        
        # 生成带通滤波的白噪声
        nyq = 0.5 / dt
        low, high = freq_range
        low_norm = low / nyq
        high_norm = high / nyq
        
        b, a = signal.butter(4, [low_norm, high_norm], btype='bandpass')
        white_noise = np.random.normal(0, 1, actual_n)
        filtered_noise = signal.filtfilt(b, a, white_noise)
        
        # 创建地震波包络函数
        envelope = np.zeros(actual_n)
        t_decay = t_total - t_rise - t_strong
        
        for i in range(actual_n):
            time = t[i]
            if time <= t_rise:
                # 上升段 - 使用二次函数
                envelope[i] = (time / t_rise) ** 2
            elif time <= t_rise + t_strong:
                # 强震段 - 维持最大值
                envelope[i] = 1.0
            else:
                # 衰减段 - 使用指数衰减
                decay_time = time - t_rise - t_strong
                envelope[i] = np.exp(-3.0 * decay_time / t_decay)
        
        # 应用包络
        artificial_eq = filtered_noise * envelope
        
        # 归一化到指定幅值
        peak = np.max(np.abs(artificial_eq))
        if peak > 0:
            artificial_eq *= amplitude / peak
        
        # 创建EQSignal对象
        eq = EQSignal(artificial_eq, dt)
        
        return eq
    
    @staticmethod
    def plot_artificial_eq(eq, title="人工生成的地震波"):
        """
        绘制人工地震波
        
        参数:
            eq: EQSignal对象
            title: 图表标题
        """
        plt.figure(figsize=(12, 9))
        
        # 加速度时程
        plt.subplot(3, 1, 1)
        plt.plot(eq.t, eq.acc)
        plt.grid(True)
        plt.ylabel('加速度')
        plt.title(title)
        
        # 频谱
        plt.subplot(3, 1, 2)
        n_fft = 2 ** int(np.ceil(np.log2(eq.n)))
        acc_fft = np.fft.fft(eq.acc, n_fft)
        freqs = np.fft.fftfreq(n_fft, eq.dt)
        plt.plot(freqs[:n_fft//2], np.abs(acc_fft[:n_fft//2]))
        plt.grid(True)
        plt.xlabel('频率 (Hz)')
        plt.ylabel('幅值')
        plt.title('频谱')
        plt.xlim(0, 25)
        
        # 反应谱
        plt.subplot(3, 1, 3)
        periods = np.logspace(-1.3, 1, 50)
        spectra = eq.compute_response_spectrum(periods=periods)
        plt.plot(periods, spectra.SPA)
        plt.grid(True)
        plt.xscale('log')
        plt.xlabel('周期 (s)')
        plt.ylabel('加速度反应谱')
        plt.title('加速度反应谱')
        
        plt.tight_layout()
        plt.show()
        
    @staticmethod
    def generate_design_spectrum(periods, site_class='II', pga=0.1, damping=0.05):
        """
        生成设计反应谱 (基于中国规范)
        
        参数:
            periods: 周期数组
            site_class: 场地类别 ('I', 'II', 'III', 'IV')
            pga: 峰值加速度 (g)
            damping: 阻尼比
            
        返回:
            设计反应谱 (periods, spectrum)
        """
        # 场地参数 (基于中国规范)
        site_params = {
            'I': {'Tg': 0.25, 'gamma': 0.9},
            'II': {'Tg': 0.35, 'gamma': 0.9},
            'III': {'Tg': 0.45, 'gamma': 0.8},
            'IV': {'Tg': 0.65, 'gamma': 0.7}
        }
        
        if site_class not in site_params:
            site_class = 'II'
            
        Tg = site_params[site_class]['Tg']
        gamma = site_params[site_class]['gamma']
        
        # 阻尼修正系数
        eta_factor = 1.0
        if damping != 0.05:
            eta_factor = np.sqrt(0.05 / damping) if damping > 0.01 else 1.0
            if eta_factor > 1.5:
                eta_factor = 1.5
                
        # 初始化反应谱数组
        spectrum = np.zeros_like(periods)
        
        for i, T in enumerate(periods):
            # 根据周期范围计算反应谱值
            if T < 0.1:
                alpha = (0.45 * gamma + 2.5 * T) * pga
            elif T <= Tg:
                alpha = gamma * 2.25 * pga
            else:  # T > Tg
                alpha = gamma * 2.25 * pga * (Tg / T) ** 0.9
                
            # 应用阻尼修正
            spectrum[i] = alpha * eta_factor
            
        return periods, spectrum 