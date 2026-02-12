%% 地震波及其平均反应谱
clear ;
clc;
%% 单自由度体系参数
T_alpha = 0.01: 0.01: 6;                                                      % 地震影响系数曲线周期值，即单自由度体系周期值
m = 1;
w =2 * pi ./ T_alpha;
xi = 0.05;
k = w.^2 .* m;
c = 2 * xi .* sqrt(m .* k);
%% % 计算标准反应谱
T_len = length(T_alpha);
Tg = 0.4;                                                                  % 二类土，第二组 
alpha_max=0.16;                                                            % 多遇地震下水平地震影响系数最大值
aksai=0.05;                                                                % 阻尼比
dT=0.01;                                                                   % 地震影响系数曲线周期间隔值
alpha_KangZhen=alpha_standspectrum(Tg,alpha_max,dT,aksai);
T_alpha1=0: 0.01: 6;
figure(1)
alpha_KangZhen=alpha_KangZhen./(0.45 * alpha_max);
plot(T_alpha1, alpha_KangZhen, '-k', 'linewidth', 2);
grid on
hold on;

%% 读入波
wave_name={'RSN9_BORREGO_B-ELC000-Acc','RSN15_KERN_TAF021-Acc','RSN40_BORREGO_A-SON033-Acc','RSN67_SFERN_ISD014-Acc','RSN86_SFERN_SON033-Acc',...
    'Artificial_wave1-0.01-Acc', 'Artificial_wave2-0.01-Acc'};
dt = [0.02 0.02 0.02 0.02 0.02 0.01 0.01];%s
E=1;
for i=1:7
    wave = textread([wave_name{i}, '.txt'], '' , 'headerlines', 0);    
    wave = wave./max(abs(wave));     
    disp(max(abs(wave)));
    len = length(wave);                                                    % 波中数据长度
    for j = 1: T_len
        [y,dy,ddy,ddy_ab,y_inter] = Newmark(k(j),m,c(j),wave,dt(i));
        SA(i,j)=max(abs(ddy_ab));
    end
    plot(T_alpha,SA(i,:), '-');
    hold on;
end
set(legend('RSN9_BORREGO_B-ELC000-Acc','RSN15_KERN_TAF021-Acc','RSN40_BORREGO_A-SON033-Acc','RSN67_SFERN_ISD014-Acc','RSN86_SFERN_SON033-Acc',...
    'Artificial_wave1-0.01-Acc', 'Artificial_wave2-0.01-Acc'),'FontSize',14,'Box','off','location','NorthEast')
set(xlabel('T(s)'),'FontSize',14)
set(ylabel('Sa(m/s^2)'),'FontSize',14)
grid on
set(gca,'box','on')
set(gca,'GridLineStyle','--','GridColor','k')
set(gca,'FontSize',14,'linewidth',1)