clear;close;
T = 0.01: 0.01: 6;
T_len = length(T);
m = 1;
w =2 * pi ./ T;
xi = 0.05;
k = w.^2 .* m;
c = 2 * xi .* sqrt(m .* k);
% 计算标准反应谱
Tg = 0.4;
alpha=0.45;     % 设防烈度下水平地震影响系数最大值
r = 0.9 + (0.05 - xi) / (0.3 + 6 * xi);
n1 = 0.02 + (0.05 - xi) / (4 + 32 * xi);
n2 = 1 + (0.05 - xi) / (0.08 +1.6 * xi);
T_n = 0: 0.01: 6;
Tn_len = length(T_n);
for i = 1: Tn_len
    if T_n(i) < 0.1
        SA_n(i) = 0.45*alpha + (n2 * alpha - 0.45 * alpha) / 0.1 * T_n(i);
    elseif 0.1 <= T_n(i) &&  T_n(i) < Tg
        SA_n(i) = n2 * alpha;
    elseif Tg <= T_n(i) && T_n(i) < 5 * Tg
        SA_n(i) = (Tg / T_n(i))^r * n2 * alpha;
    else
        SA_n(i) = (n2 * 0.2^r - n1 * (T_n(i) - 5 *Tg)) *alpha;
    end
end
figure(1)
SA_n = SA_n ./ (0.45 * alpha);
SV_n = SA_n.*T_n/(2*pi);

plot(T_n, SV_n, '-k', 'linewidth', 2);
hold on;
% 读入波
wave_name={'RSN55_SFERN_BVP090_0005','RSN138_TABAS_BOS-L1_002',...
    'RSN162_IMPVALL.H_H-CXO315_0005','RSN169_IMPVALL.H_H-DLT262_001','RSN179_IMPVALL.H_H-E04140_0005',...
    'AW1-001', 'AW2-001'};
dt = [0.005 0.02 0.005 0.01 0.005 0.01 0.01];%s
E=1;
for i=1:7
    wave = textread([wave_name{i}, '.txt'], '' , 'headerlines', 0);    
    wave = wave./max(abs(wave));     
    disp(max(abs(wave)));
    len = length(wave);        %波中数据长度
    for j = 1: T_len
        %SA(i, j) = max(abs(Newmark(k(j), m, c(j) ,wave, dt(i),E)));
        [~,dy,~,~,~]=Newmark(k(j),m,c(j),wave,dt(i));
        SV(i,j)=max(abs(dy));
    end
    plot(T,SV(i,:), '-');
    hold on;
end
set(legend('规范设计反应谱', 'RSN55', 'RSN138', 'RSN162', 'RSN169','RSN179','AW1', 'AW2'),'FontSize',10,'Box','off','location','NorthEast')
set(xlabel('周期/s'),'FontSize',14)
set(ylabel('归一化速度反应谱'),'FontSize',14)
grid on
set(gca,'box','on')
set(gca,'GridLineStyle','--','GrdColor','k')
set(gca,'FontSize',14,'linewidth',1)
print(gcf, '-dpng', '归一化速度反应谱.png')
