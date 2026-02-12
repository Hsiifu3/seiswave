
clc;clear;
Tg = 0.4;     
alpha_max = 0.45; %由于归一化计算，峰值不重要，不作为控制参数
% 隔震反应谱
for T = 0.01 :0.01:6
    j = round(100*T);
    h = 0.05;
    r = 0.9 + (0.05 - h) / (0.3 + 6 * h);
    n1 = 1 + (0.05 - h) / (0.08 +1.6 * h);
    if T < 0.1
        alpha(j) = 0.45*alpha_max + (n1 * alpha_max - 0.45 * alpha_max) / 0.1 * T;
    elseif 0.1 <= T  &&  T < Tg
        alpha(j) = n1 * alpha_max;
    else
        alpha(j) = (Tg / T)^r * n1 * alpha_max;
    end
end
alpha = alpha./0.45/alpha_max;
plot(0.01:0.01:6,alpha,'k','LineWidth',2)