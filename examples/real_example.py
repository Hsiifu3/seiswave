"""
使用EQSignalPy处理实际地震记录的示例
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from eqsignalpy import EQSignal, EQSpectra, Filter, Response

def main():
    # 从文件加载地震记录
    # 注意：您需要替换为实际的地震记录文件路径
    # 假设数据是单列文本格式
    try:
        # 尝试加载文件
        filename = "earthquake_data.txt"  # 替换为实际文件
        
        # 如果找不到文件，创建一个示例数据文件
        if not os.path.exists(filename):
            print(f"找不到文件 {filename}，创建示例数据...")
            # 创建一个示例数据
            t = np.arange(0, 20, 0.01)
            acc = np.sin(2 * np.pi * 2 * t) * np.exp(-0.1 * t)
            np.savetxt(filename, acc)
            print(f"已创建示例数据文件 {filename}")
        
        # 加载地震记录
        eq = EQSignal.from_file(filename, dt=0.01)
        print(f"成功加载地震记录，共 {eq.n} 个数据点，总时长 {eq.n*eq.dt:.2f} 秒")
        
        # 基线校正
        eq_corrected = eq.baseline_correction(order_high=3, order_low=1)
        
        # 滤波
        filtered_acc = Filter.butterworth(eq_corrected.acc, eq_corrected.dt, 
                                          ftype='bandpass', order=4, freqs=(0.1, 25.0))
        eq_filtered = EQSignal(filtered_acc, dt=eq_corrected.dt)
        
        # 计算速度和位移
        eq_filtered.acc2vd()
        
        # 显示处理结果
        plt.figure(figsize=(12, 8))
        
        # 原始加速度
        plt.subplot(3, 1, 1)
        plt.plot(eq.t, eq.acc, 'k-', label="原始")
        plt.plot(eq_corrected.t, eq_corrected.acc, 'r-', label="基线校正")
        plt.plot(eq_filtered.t, eq_filtered.acc, 'b-', label="滤波后")
        plt.grid(True)
        plt.legend()
        plt.ylabel("加速度")
        plt.title("地震记录处理")
        
        # 速度
        plt.subplot(3, 1, 2)
        plt.plot(eq_filtered.t, eq_filtered.vel, 'g-')
        plt.grid(True)
        plt.ylabel("速度")
        
        # 位移
        plt.subplot(3, 1, 3)
        plt.plot(eq_filtered.t, eq_filtered.dsp, 'm-')
        plt.grid(True)
        plt.xlabel("时间(s)")
        plt.ylabel("位移")
        
        plt.tight_layout()
        plt.show()
        
        # 计算多个阻尼比的反应谱
        zetas = [0.02, 0.05, 0.10]
        periods = np.logspace(-1, 1, 100)
        
        plt.figure(figsize=(10, 6))
        
        for zeta in zetas:
            spectra = EQSpectra(eq_filtered, zeta, periods)
            spectra.calc()
            plt.plot(spectra.periods, spectra.SPA, label=f"$\\zeta$ = {zeta:.2f}")
        
        plt.xscale('log')
        plt.grid(True)
        plt.xlabel("周期 (s)")
        plt.ylabel("加速度反应谱 (m/s²)")
        plt.title("不同阻尼比的加速度反应谱")
        plt.legend()
        plt.tight_layout()
        plt.show()
        
        # 计算不同周期的响应
        T_values = [0.2, 0.5, 1.0, 2.0]
        
        plt.figure(figsize=(12, 8))
        
        for i, period in enumerate(T_values):
            resp = Response(eq_filtered, zeta=0.05, period=period)
            resp.calc()
            
            plt.subplot(2, 2, i+1)
            plt.plot(resp.rd, resp.rf)
            plt.grid(True)
            plt.xlabel("位移")
            plt.ylabel("恢复力")
            plt.title(f"T = {period:.1f}s")
        
        plt.tight_layout()
        plt.show()
        
        # 非线性响应分析
        period = 1.0
        mu_values = [1.0, 2.0, 4.0, 8.0]
        
        plt.figure(figsize=(12, 8))
        
        for i, mu in enumerate(mu_values):
            resp = Response(eq_filtered, zeta=0.05, period=period)
            if mu == 1.0:
                resp.calc()  # 线性分析
            else:
                resp.calc(mu=mu)  # 非线性分析
            
            plt.subplot(2, 2, i+1)
            plt.plot(resp.rd, resp.rf)
            plt.grid(True)
            plt.xlabel("位移")
            plt.ylabel("恢复力")
            plt.title(f"$\\mu$ = {mu:.1f}")
        
        plt.tight_layout()
        plt.show()
        
    except Exception as e:
        print(f"处理过程中发生错误: {e}")

if __name__ == "__main__":
    main() 