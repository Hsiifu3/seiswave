%% 绘制2条人工波和5条天然地震波加速度、速度、位移时程曲线
clc;clear;close all;
% 2条人工波和5条天然地震波文件位置
Path = 'C:\Users\303\Desktop\硕士论文\MATLAB\选取地震波\8度0.2g硬土场地\步骤三：绘制归一化加速度时程反应谱\Result\';
% % 天然波输入【AT2文件】
FileName_NW = {dir([Path,'*.AT2']).name};  % 读取所在文件夹所有天然波AT2文件
total_NW = length(FileName_NW); % 统计文件数
for i = 1:total_NW
    filepath = [Path,'\',cell2mat( FileName_NW(i) ) ];   % 依次读取文件
    fileID = fopen(filepath);
    File.Signal = textscan(fileID,'%f','HeaderLines',4); % 读取信号数据
    fileID = fopen(filepath);
    File.dt = textscan(fileID,'%s','delimiter','=','HeaderLines',3); % 读取dt
    dtCell = File.dt{1};
    dt(i,1) = str2double( dtCell{3}(1:5) );              % 转化为double类型
    fileID = fclose(fileID);
    Signal(1:length(File.Signal{1}),i) = File.Signal{1}; % 读取cell中信号数据
    SignalName(:,i) = ( FileName_NW(i) );                % 读取cell中对应地震名称
end

total_NW = 0;
% 人工波输入【txt文件】
FileName_AW = {dir([Path,'*.txt']).name};    % 读取所在文件夹所有人工波txt文件
total_AW = length(FileName_AW); % 统计文件数
for i = 1:total_AW
    filepath = [Path,'\',cell2mat( FileName_AW(i) ) ];   % 依次读取文件
    fileID = fopen(filepath);
    File.Signal = textscan(fileID,'%f','HeaderLines',0); % 读取信号数据
    fileID = fopen(filepath);
    dt(total_NW+i,1) = 0.01;                             % 人工波的时间间隔
    fileID = fclose(fileID);
    Signal(1:length(File.Signal{1}),total_NW+i) = File.Signal{1};% 读取cell中信号数据
    SignalName(:,total_NW+i) = ( FileName_AW(i) );       % 读取cell中对应地震名称
end



% Matlab去除矩阵内的0元素
for j = 1:(total_NW+total_AW)
    a = Signal(:,j);
    a = a(:,end)/max(abs(a(:,end)));                      % 对地震动的加速度调幅，单位：m/s^2
    a(a==0) = [];
    disp(max(abs(a))) 
    Signal_0{j}(:,1) = a;
end

%% 绘图
Figure_Names = {'RSN75_0005_accel'};
% —————— 绘制加速度时程曲线 ——————
for j = 1:(total_NW+total_AW)
    h = figure(1);
    h.Units = 'normalized';
    h.Position = [0.05, 0.2, 0.6, 0.4];
    plot(0:dt(j):dt(j)*(length(Signal_0{j}(:,1))-1),Signal_0{j}(:,1),'-','LineWidth',1)
    xlabel('Time (s)');
    ylabel('加速度 (g)');
    grid on
    print(Figure_Names{j},'-djpeg','-r300');
end

Figure_Names_vel = {'RSN75_0005_vel'};
% —————— 绘制速度时程曲线 ——————
for j = 1:(total_NW+total_AW)
    h = figure(2);
    h.Units = 'normalized';
    h.Position = [0.05, 0.2, 0.6, 0.4];
    Time = 0:dt(j):dt(j)*(length(Signal_0{j}(:,1))-1);
    vel = cumtrapz(Time,Signal_0{j});   % cumtrapz：累积梯形数值积分
    vel = vel - repmat(mean(vel), size(vel,1), 1);
    plot(Time, vel,'-','LineWidth',1)
    xlabel('时间 (s)');
    ylabel('速度 (m/s)');
    grid on
    print(Figure_Names_vel{j},'-djpeg','-r300');
end

Figure_Names_dis = {'RSN75_0005_dis'};
% —————— 绘制位移时程曲线 ——————
for j = 1:(total_NW+total_AW)
    h = figure(3);
    h.Units = 'normalized';
    h.Position = [0.05, 0.2, 0.6, 0.4];
    Time = 0:dt(j):dt(j)*(length(Signal_0{j}(:,1))-1);
    vel = cumtrapz(Time,Signal_0{j});   % cumtrapz：累积梯形数值积分
    vel = vel - repmat(mean(vel), size(vel,1), 1);
    dis = cumtrapz(Time,vel);           % cumtrapz：累积梯形数值积分
    plot(Time, dis,'-','LineWidth',1)
    xlabel('时间 (s)');
    ylabel('位移 (m)');
    grid on
    print(Figure_Names_dis{j},'-djpeg','-r300');
end


