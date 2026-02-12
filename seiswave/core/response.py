"""
结构响应分析模块
"""

import numpy as np
import matplotlib.pyplot as plt


class Response:
    """结构响应分析类，用于计算单自由度系统响应"""
    
    def __init__(self, eqsignal, zeta=0.05, period=2.0):
        """
        初始化响应分析对象
        
        参数:
            eqsignal: EQSignal对象
            zeta: 阻尼比，默认5%
            period: 周期，默认2.0秒
        """
        self.acc = eqsignal.acc
        self.t = eqsignal.t
        self.dt = eqsignal.dt
        self.n = eqsignal.n
        self.zeta = zeta
        self.period = period
        
        # 计算系统参数
        self.omega = 2.0 * np.pi / self.period
        self.k = self.omega ** 2
        self.c = 2.0 * self.zeta * self.omega
        
        # 初始化响应数组
        self.ra = np.zeros(self.n)  # 相对加速度
        self.rv = np.zeros(self.n)  # 相对速度
        self.rd = np.zeros(self.n)  # 相对位移
        self.rf = np.zeros(self.n)  # 恢复力
        
    def calc(self, mu=None):
        """
        计算响应
        
        参数:
            mu: 屈服强度折减系数，默认None（线性分析）
            
        返回:
            ra, rv, rd, rf: 加速度、速度、位移和恢复力响应
        """
        if mu is None:
            # 线性分析
            self._calc_linear()
        else:
            # 非线性分析
            self._calc_nonlinear(mu)
            
        # 计算恢复力
        self.rf = -self.ra - self.c * self.rv
            
        return self.ra, self.rv, self.rd, self.rf
        
    def _calc_linear(self):
        """线性响应计算（Newmark-beta方法）"""
        # 初始条件
        self.rd[0] = 0.0
        self.rv[0] = 0.0
        self.ra[0] = -self.acc[0]
        
        # Newmark-beta参数（平均加速度法）
        gamma = 0.5
        beta = 0.25
        
        # 有效系数
        a1 = 1.0 / (beta * self.dt**2)
        a2 = 1.0 / (beta * self.dt)
        a3 = (1.0 - 2.0 * beta) / (2.0 * beta)
        
        a4 = gamma / (beta * self.dt)
        a5 = 1.0 - gamma / beta
        a6 = (1.0 - gamma / (2.0 * beta)) * self.dt
        
        # 有效刚度
        keff = self.k + a1 + self.c * a4
        
        for i in range(1, self.n):
            # 有效荷载
            p_eff = -self.acc[i] + a1 * self.rd[i-1] + a2 * self.rv[i-1] + a3 * self.ra[i-1]
            p_eff += self.c * (a4 * self.rd[i-1] + a5 * self.rv[i-1] + a6 * self.ra[i-1])
            
            # 计算位移
            self.rd[i] = p_eff / keff
            
            # 计算速度和加速度
            self.ra[i] = a1 * (self.rd[i] - self.rd[i-1]) - a2 * self.rv[i-1] - a3 * self.ra[i-1]
            self.rv[i] = a4 * (self.rd[i] - self.rd[i-1]) + a5 * self.rv[i-1] + a6 * self.ra[i-1]
            
    def _calc_nonlinear(self, mu, model=0):
        """
        非线性响应计算
        
        参数:
            mu: 屈服强度折减系数
            model: 滞回模型类型（0=双线性，1=Clough，2=Takeda）
        """
        # 计算屈服位移
        f_y = self.k / mu
        d_y = f_y / self.k
        
        # 初始化状态变量
        d_prev = 0.0
        v_prev = 0.0
        a_prev = -self.acc[0]
        f_prev = 0.0
        k_cur = self.k
        
        # 初始条件
        self.rd[0] = 0.0
        self.rv[0] = 0.0
        self.ra[0] = -self.acc[0]
        self.rf[0] = 0.0
        
        # 设置硬化率（刚度比）
        alpha = 0.05  # 双线性模型的硬化率
        
        # Newmark-beta参数
        gamma = 0.5
        beta = 0.25
        
        for i in range(1, self.n):
            # 预测步骤
            d_pred = d_prev + self.dt * v_prev + 0.5 * self.dt**2 * a_prev
            v_pred = v_prev + self.dt * a_prev
            
            # 计算试算恢复力
            if model == 0:
                # 双线性模型
                if abs(d_pred) <= d_y:
                    # 弹性区域
                    f_pred = self.k * d_pred
                    k_cur = self.k
                else:
                    # 屈服后区域
                    if d_pred > 0:
                        f_pred = f_y + alpha * self.k * (d_pred - d_y)
                    else:
                        f_pred = -f_y + alpha * self.k * (d_pred + d_y)
                    k_cur = alpha * self.k
            else:
                # 简化的Clough或Takeda模型 - 这里仅实现一个基本版本
                if abs(d_pred) <= d_y:
                    # 弹性区域
                    f_pred = self.k * d_pred
                    k_cur = self.k
                else:
                    # 屈服后区域
                    if d_pred > 0:
                        f_pred = f_y + alpha * self.k * (d_pred - d_y)
                    else:
                        f_pred = -f_y + alpha * self.k * (d_pred + d_y)
                    
                    # 修改刚度（根据模型类型）
                    if model == 1:  # Clough
                        k_cur = f_pred / d_pred  # 指向原点的刚度
                    else:  # Takeda
                        k_cur = alpha * self.k
            
            # 计算有效质量和阻尼
            c_eff = self.c
            m_eff = 1.0
            
            # 计算有效荷载
            p_eff = -self.acc[i] - f_pred - c_eff * v_pred
            
            # 修正步骤
            a_cur = p_eff / m_eff
            v_cur = v_pred + 0.5 * self.dt * (a_prev + a_cur)
            d_cur = d_pred + 0.5 * self.dt * (v_prev + v_cur)
            
            # 更新恢复力
            if model == 0:
                # 双线性模型
                if abs(d_cur) <= d_y:
                    f_cur = self.k * d_cur
                else:
                    if d_cur > 0:
                        f_cur = f_y + alpha * self.k * (d_cur - d_y)
                    else:
                        f_cur = -f_y + alpha * self.k * (d_cur + d_y)
            else:
                # 简化的Clough或Takeda模型
                if abs(d_cur) <= d_y:
                    f_cur = self.k * d_cur
                else:
                    if d_cur > 0:
                        f_cur = f_y + alpha * self.k * (d_cur - d_y)
                    else:
                        f_cur = -f_y + alpha * self.k * (d_cur + d_y)
            
            # 存储当前步的结果
            self.rd[i] = d_cur
            self.rv[i] = v_cur
            self.ra[i] = a_cur
            self.rf[i] = f_cur
            
            # 更新上一步的值
            d_prev = d_cur
            v_prev = v_cur
            a_prev = a_cur
            f_prev = f_cur
    
    def plot(self, title="结构响应时程"):
        """
        绘制响应时程图
        
        参数:
            title: 图表标题
        """
        plt.figure(figsize=(12, 9))
        
        # 加速度响应
        plt.subplot(4, 1, 1)
        plt.plot(self.t, self.ra, 'r-')
        plt.grid(True)
        plt.ylabel('相对加速度')
        plt.title(title)
        
        # 速度响应
        plt.subplot(4, 1, 2)
        plt.plot(self.t, self.rv, 'g-')
        plt.grid(True)
        plt.ylabel('相对速度')
        
        # 位移响应
        plt.subplot(4, 1, 3)
        plt.plot(self.t, self.rd, 'b-')
        plt.grid(True)
        plt.ylabel('相对位移')
        
        # 恢复力
        plt.subplot(4, 1, 4)
        plt.plot(self.t, self.rf, 'm-')
        plt.grid(True)
        plt.xlabel('时间(s)')
        plt.ylabel('恢复力')
        
        plt.tight_layout()
        plt.show()
        
    def plot_hysteresis(self):
        """绘制滞回曲线"""
        plt.figure(figsize=(8, 8))
        plt.plot(self.rd, self.rf, 'b-')
        plt.grid(True)
        plt.xlabel('位移')
        plt.ylabel('恢复力')
        plt.title('滞回曲线')
        
        # 添加原点
        plt.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        plt.axvline(x=0, color='k', linestyle='-', alpha=0.3)
        
        plt.tight_layout()
        plt.show()
        
    def energy(self):
        """
        计算能量响应
        
        返回:
            各种能量分量的时程
        """
        # 弹性应变能
        Es = 0.5 * self.k * self.rd**2
        
        # 动能
        Ek = 0.5 * self.rv**2
        
        # 阻尼耗能
        Ed = np.zeros(self.n)
        for i in range(1, self.n):
            Ed[i] = Ed[i-1] + self.c * self.rv[i-1] * (self.rd[i] - self.rd[i-1])
        
        # 滞回耗能 (简化计算)
        Eh = np.zeros(self.n)
        for i in range(1, self.n):
            Eh[i] = Eh[i-1] + 0.5 * (self.rf[i] + self.rf[i-1]) * (self.rd[i] - self.rd[i-1])
        Eh = Eh - Es - Ed  # 近似值
        
        # 输入能量 (地震输入的总能量)
        Ein = Ek + Es + Ed + Eh
        
        return Ek, Es, Ed, Eh, Ein
        
    def __str__(self):
        """字符串表示"""
        return f"Response(period={self.period:.2f}s, zeta={self.zeta:.2f})"
        
    def __repr__(self):
        """表示方法"""
        return self.__str__() 