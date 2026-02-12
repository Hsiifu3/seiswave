clear;clc;close;
%% 绘制归一化隔震反应谱
% *功能*：绘制筛选后的多条地震波的归一化隔震反应谱
%% 输入
% 地震波txt文件位置;
Path_txt='C:\Users\303\Desktop\硕士论文\MATLAB\选取地震波\8度0.2g硬土场地\步骤三：绘制归一化加速度时程反应谱\10\';
%% 
T = 0.01: 0.01: 6;                                                         % 地震波加速度反应谱—地震波影响系数曲线横轴，避免分母为零，从非零开始
T_len = length(T);                                                         % 地震波加速度反应谱横轴数据点个数
%% 单自由度体系设计参数
m = 1;                                                                     % 单自由度质点质量
w = 2 * pi ./ T;                                                            % 圆频率
aksai= 0.05;                                                               % 阻尼比
k = w.^2 .* m;                                                             % 体系刚度  
c = 2 * aksai .* sqrt(m .* k);                                             % 体系阻尼
%% 隔震设计归一化标准反应谱
Tg = 0.4;                                                                  % 第二组，场地类别II
alpha_max = 0.45;                                                          % 8度中震水平地震影响系数最大值
T_n = 0: 0.01: 6;                                                          % 隔震结构自振周期—地震影响系数曲线横轴
Tn_len = length(T_n);                                                      % 地震影响系数曲线横轴数据点个数
stand_alpha_isolation=zeros(1,Tn_len);                                     % 创建集合用于存放地震影响系数数值
dT = 0.01;                                                                 % 单自由度体系隔震结构自振周期增量
for i = 1: Tn_len
    stand_alpha_isolation = alpha_standspectrum_isolation(Tg,alpha_max,dT,aksai); % 不同单自由度体系不同周期下计算相应的隔震alpha谱数值
end
stand_alpha_isolation = stand_alpha_isolation./stand_alpha_isolation(1);   % beta谱
plot(T_n, stand_alpha_isolation, '-r', 'linewidth', 2);                    % 绘制归一化后的隔震设计标准反应谱（地震影响系数曲线）
grid on
hold on;
% plot(T_n, 0.65*stand_alpha_isolation, '--r', 'linewidth', 2);               % 绘制归一化后的隔震设计标准反应谱（地震影响系数曲线）
% hold on;
% plot(T_n, 1.35*stand_alpha_isolation, '--r', 'linewidth', 2);               % 绘制归一化后的隔震设计标准反应谱（地震影响系数曲线）

%% txt加速度数据提取
FileName={dir([Path_txt,'*.txt']).name};                                   % 读取所在文件夹所有AT2文件
wave_number=length(FileName);                                              % 统计地震波txt文件数
dt = [0.01 0.01 0.02 0.005 0.01 0.005 0.005];                               % 地震波步长(s)
SignalName=cell(1,wave_number);                                            % 地震动加速度名称
for i = 1:wave_number
    filepath = [Path_txt,cell2mat( FileName(i) ) ];                        % 依次读取文件，cell2mat将元胞数组转换为基础数据类型的普通数组
    fileID = fopen(filepath);
    File.Signal = textscan(fileID,'%f','HeaderLines',0);                   % 读取信号数据
    fileID = fopen(filepath);
    fileID = fclose(fileID);
    Signal(1:length(File.Signal{1}),i) = File.Signal{1};                   % 读取cell中信号数据
    SignalName{:,i} = ( FileName(i) );                                     % 读取cell中对应地震名称
end

%% 地震波归一化加速度反应谱
for i=1:wave_number
    wave_Newrmark = Signal(:,i);    
    wave_Newrmark = wave_Newrmark./max(abs(wave_Newrmark));                % 归一化地震波
    disp(max(abs(wave_Newrmark)));
%     len = length(wave_Newrmark);                                         % 波中数据长度
    for j = 1: T_len                                                       % 地震波加速度反应谱横轴数据点个数,除去非零 
        [~,~,~,ddy_ab,~] = Newmark(k(j),m,c(j),wave_Newrmark,dt(1));         % 返回地震波加速度作用下单自由度体系最大绝对加速度
        SA(i,j) = max(abs(ddy_ab));
    end
    plot(T,SA(i,:), '-');
    grid on
    hold on;
end
SA_Average = sum(SA,1)./7;                                                 % 地震波平均加速度反应谱
plot(T,SA_Average,'color',[0 0.45 0.74],'linewidth', 2);                   % 绘制地震波平均加速度反应谱

%% 添加图例
set(legend('Design response spectrum', 'AW1', 'AW2', 'NW138', 'NW162','NW169','NW179', 'NW55', 'Average respnse spectrum'),...
    'FontSize',10,'Box','off','location','NorthEast')
set(xlabel('Period(s)'),'FontSize',10)
set(ylabel('Normalization Acceeration Sprecturm'),'FontSize',10)                                              % 归一化反应谱
grid on
set(gca,'box','on')
set(gca,'GridLineStyle','--','GridColor','k')
set(gca,'FontSize',10,'linewidth',2)
% print(gcf, '-dpng', '归一化反应谱.png')
    
    
    