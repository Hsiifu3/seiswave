"""
地震反应谱模块
"""

import numpy as np
import matplotlib.pyplot as plt


class EQSpectra:
    """地震反应谱类，用于计算和分析反应谱"""
    
    def __init__(self, eqsignal, zeta=0.05, periods=None, pseudo=False):
        """
        初始化反应谱对象
        
        参数:
            eqsignal: EQSignal对象
            zeta: 阻尼比，默认5%
            periods: 周期数组，默认使用对数分布的周期
            pseudo: 是否计算伪反应谱，默认False
        """
        self.acc = eqsignal.acc
        self.n = eqsignal.n
        self.dt = eqsignal.dt
        self.zeta = zeta
        
        if periods is None:
            # 默认使用对数分布的周期
            self.periods = np.logspace(-1.3, 1, 30)
        else:
            self.periods = np.asarray(periods)
            
        self.nP = len(self.periods)
        self.pseudo = pseudo
        
        # 初始化反应谱结果数组
        self.SPA = np.zeros(self.nP)  # 加速度反应谱
        self.SPV = np.zeros(self.nP)  # 速度反应谱
        self.SPD = np.zeros(self.nP)  # 位移反应谱
        self.SPE = np.zeros(self.nP)  # 能量反应谱
        
    def calc(self):
        """
        计算反应谱
        """
        # 对每个周期计算SDOF系统响应
        for i, period in enumerate(self.periods):
            ra, rv, rd = self._calculate_response(period)
            
            # 存储最大响应值
            if self.pseudo:
                # 伪反应谱
                omega = 2.0 * np.pi / period
                self.SPA[i] = omega**2 * np.max(np.abs(rd))
                self.SPV[i] = omega * np.max(np.abs(rd))
                self.SPD[i] = np.max(np.abs(rd))
            else:
                # 绝对反应谱
                self.SPA[i] = np.max(np.abs(ra))
                self.SPV[i] = np.max(np.abs(rv))
                self.SPD[i] = np.max(np.abs(rd))
                
            # 计算能量反应谱
            omega = 2.0 * np.pi / period
            k = omega**2
            Ek = 0.5 * k * rd**2  # 弹性势能
            self.SPE[i] = np.max(Ek)
            
        return self.SPA, self.SPV, self.SPD
        
    def _calculate_response(self, period):
        """
        计算单个周期下的SDOF响应
        
        参数:
            period: 周期
            
        返回:
            ra, rv, rd: 加速度、速度和位移响应
        """
        omega = 2.0 * np.pi / period
        k = omega**2
        c = 2.0 * self.zeta * omega
        
        # 初始化响应数组
        ra = np.zeros(self.n)
        rv = np.zeros(self.n)
        rd = np.zeros(self.n)
        
        # 初始条件
        rd[0] = 0.0
        rv[0] = 0.0
        
        # 实现Newmark-beta方法（平均加速度法）
        gamma = 0.5
        beta = 0.25
        
        # 有效质量矩阵系数
        a1 = 1.0 / (beta * self.dt**2)
        a2 = 1.0 / (beta * self.dt)
        a3 = (1.0 - 2.0 * beta) / (2.0 * beta)
        
        # 有效阻尼矩阵系数
        a4 = gamma / (beta * self.dt)
        a5 = 1.0 - gamma / beta
        a6 = (1.0 - gamma / (2.0 * beta)) * self.dt
        
        # 有效刚度
        keff = k + a1 + c * a4
        
        for i in range(1, self.n):
            # 有效荷载
            p_eff = -self.acc[i] + a1 * rd[i-1] + a2 * rv[i-1] + a3 * ra[i-1]
            p_eff += c * (a4 * rd[i-1] + a5 * rv[i-1] + a6 * ra[i-1])
            
            # 计算位移
            rd[i] = p_eff / keff
            
            # 计算速度和加速度
            ra[i] = a1 * (rd[i] - rd[i-1]) - a2 * rv[i-1] - a3 * ra[i-1]
            rv[i] = a4 * (rd[i] - rd[i-1]) + a5 * rv[i-1] + a6 * ra[i-1]
        
        return ra, rv, rd
        
    def plot(self, xs="log", show=True):
        """
        绘制反应谱
        
        参数:
            xs: x轴缩放类型，'log'或'linear'
            show: 是否显示图像
        """
        plt.figure(figsize=(12, 9))
        
        # 加速度反应谱
        plt.subplot(2, 2, 1)
        plt.plot(self.periods, self.SPA, 'r-', linewidth=2)
        plt.xscale(xs)
        plt.grid(True)
        plt.xlabel('周期 (s)')
        plt.ylabel('加速度反应谱 (m/s²)')
        plt.title(f'加速度反应谱 (ζ = {self.zeta:.2f})')
        
        # 速度反应谱
        plt.subplot(2, 2, 2)
        plt.plot(self.periods, self.SPV, 'g-', linewidth=2)
        plt.xscale(xs)
        plt.grid(True)
        plt.xlabel('周期 (s)')
        plt.ylabel('速度反应谱 (m/s)')
        plt.title(f'速度反应谱 (ζ = {self.zeta:.2f})')
        
        # 位移反应谱
        plt.subplot(2, 2, 3)
        plt.plot(self.periods, self.SPD, 'b-', linewidth=2)
        plt.xscale(xs)
        plt.grid(True)
        plt.xlabel('周期 (s)')
        plt.ylabel('位移反应谱 (m)')
        plt.title(f'位移反应谱 (ζ = {self.zeta:.2f})')
        
        # 能量反应谱
        plt.subplot(2, 2, 4)
        plt.plot(self.periods, self.SPE, 'm-', linewidth=2)
        plt.xscale(xs)
        plt.grid(True)
        plt.xlabel('周期 (s)')
        plt.ylabel('能量反应谱 (J)')
        plt.title(f'能量反应谱 (ζ = {self.zeta:.2f})')
        
        plt.tight_layout()
        
        if show:
            plt.show()
            
    def to_design_spectrum(self, factor=1.0):
        """
        转换为设计反应谱
        
        参数:
            factor: 缩放因子
            
        返回:
            设计反应谱（新的EQSpectra对象）
        """
        design_spectra = EQSpectra(None, self.zeta, self.periods)
        design_spectra.SPA = self.SPA * factor
        design_spectra.SPV = self.SPV * factor
        design_spectra.SPD = self.SPD * factor
        design_spectra.SPE = self.SPE * factor
        
        return design_spectra
        
    def save(self, filename):
        """
        保存反应谱数据到文件
        
        参数:
            filename: 文件名
        """
        data = np.column_stack((self.periods, self.SPA, self.SPV, self.SPD, self.SPE))
        header = "Period, Acceleration, Velocity, Displacement, Energy"
        np.savetxt(filename, data, header=header, delimiter=",")
        
    def __str__(self):
        """字符串表示"""
        return f"EQSpectra(periods={self.nP}, zeta={self.zeta:.2f})"
        
    def __repr__(self):
        """表示方法"""
        return self.__str__() 