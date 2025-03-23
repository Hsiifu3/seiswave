"""
地震动生成示例
"""

import numpy as np
import matplotlib.pyplot as plt
from eqsignalpy import EQGenerator, EQSignal

def main():
    """演示地震动生成功能"""
    
    print("演示人工地震动生成功能")
    
    # 1. 生成白噪声信号
    print("\n1. 生成白噪声信号")
    noise_eq = EQGenerator.generate_white_noise(n=2048, dt=0.01)
    noise_eq.acc2vd()
    noise_eq.plot(title="白噪声信号")
    
    # 2. 生成具有包络形状的人工地震波
    print("\n2. 生成具有包络形状的人工地震波")
    artificial_eq = EQGenerator.generate_artificial_eq(
        n=4096, 
        dt=0.01, 
        t_rise=2.0, 
        t_strong=5.0, 
        t_total=20.0,
        freq_range=(0.5, 15.0),
        amplitude=0.3
    )
    artificial_eq.acc2vd()
    
    # 绘制生成的人工地震波
    EQGenerator.plot_artificial_eq(artificial_eq, title="人工地震波")
    
    # 3. 生成设计反应谱并据此生成地震波
    print("\n3. 根据设计反应谱生成地震波")
    periods = np.logspace(-1, 1, 100)  # 0.1s - 10s
    
    # 生成设计反应谱 (基于中国规范)
    design_spectrum = EQGenerator.generate_design_spectrum(
        periods, 
        site_class='II', 
        pga=0.2,  # 0.2g
        damping=0.05
    )
    
    # 绘制设计反应谱
    plt.figure(figsize=(10, 6))
    plt.plot(design_spectrum[0], design_spectrum[1], 'r-', linewidth=2)
    plt.xscale('log')
    plt.grid(True)
    plt.xlabel('周期 (s)')
    plt.ylabel('加速度 (g)')
    plt.title('设计反应谱')
    plt.show()
    
    # 根据设计反应谱生成地震波
    spectrum_matched_eq = EQGenerator.generate_from_spectrum(
        design_spectrum,
        n=4096,
        dt=0.01,
        zeta=0.05
    )
    spectrum_matched_eq.acc2vd()
    
    # 绘制根据反应谱生成的地震波
    EQGenerator.plot_artificial_eq(spectrum_matched_eq, title="反应谱匹配的人工地震波")
    
    # 比较目标反应谱和生成地震波的反应谱
    actual_spectrum = spectrum_matched_eq.compute_response_spectrum(periods=periods)
    
    plt.figure(figsize=(10, 6))
    plt.plot(design_spectrum[0], design_spectrum[1], 'r-', linewidth=2, label='目标谱')
    plt.plot(periods, actual_spectrum.SPA, 'b--', linewidth=1.5, label='实际谱')
    plt.xscale('log')
    plt.grid(True)
    plt.xlabel('周期 (s)')
    plt.ylabel('加速度 (g)')
    plt.title('反应谱比较')
    plt.legend()
    plt.show()
    
    print("\n示例完成，成功演示了地震动生成功能！")

if __name__ == "__main__":
    main() 