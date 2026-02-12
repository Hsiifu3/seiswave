%% PEER地震波筛选
% *功能*：用于筛选PEER下载的地震波中符合规范要求的地震波。
% 
% *使用方法*：输入如下参数：
%% 
% # 场地特征周期;
% # 结构前三周期;
% # AT2文件位置（解压后无需删除DT2、VT2文件）;
% # 质量刚度信息。
%% 
% *计算结果*：1.地震波反应谱；
% 
% 2.符合条件的地震波反应谱及相关条件；
% 
% 3.符合条件的地震波将置于 “...\Result” 文件夹中

clc;clear;close;
%% 选波参数输入
% 场地特征周期
Tg = 0.65;             
% 前三周期模态
T1 = 3.36;         
T2 = 3.01;
T3 = 2.5;
% 质量和刚度信息
% m0 = [1043.7, 1010.0, 987.9, 980.9, 958.7, 958.7, 1067.6].*10^3;   
% k0 = [1010, 623, 723, 715, 641, 648, 638].*10^6;                      % X向刚度
% k0 = [ 938 568 636 615 563 567 544].*10^6;                            % Y向刚度
% Peer文件位置
Path = 'D:\SynologyDrive\PEER\';
% 需要进行底部剪力判断，输入1；不需要，输入0；
condition = 0;

%% 信号输入

FileName = {dir([Path,'*.AT2']).name};  %读取所在文件夹所有AT2文件
total = length(FileName); %统计文件数
for i = 1:total
    filepath = [Path,cell2mat( FileName(i) ) ]; %依次读取文件
    fileID = fopen(filepath);
    File.Signal = textscan(fileID,'%f','HeaderLines',4); %读取信号数据
    fileID = fopen(filepath);
    File.dt = textscan(fileID,'%s','delimiter','=','HeaderLines',3); %读取dt
    dtCell = File.dt{1};
    dt(i,1) = str2num( dtCell{3}(1:5) ); %转化为double类型
    fileID = fclose(fileID);
    Signal(1:length(File.Signal{1}),i) = File.Signal{1}; %读取cell中信号数据
    SignalName(:,i) = ( FileName(i) ); %读取cell中对应地震名称
end
%% 条件一：有效持时
% 输入的地震加速度时程曲线的有效持续时间，一般从首次到该时程曲线最大峰值的*10%*那一点算起，到最后一点达到大峰值的*10%*为止；不论是实际的强震记录还是人工模拟波形有效持续时间一般为结构基本周期的(5~10)倍，即结构顶的位移可按基本周期往复(5~10)次。

p = 1; %临时变量记录符合条件的波的编号
for i = 1:total
    j = 1; %临时变量记录>10%的时间点
    wave_PGA = max(Signal(:,i));
    wave_norm = Signal(:,i)./max(Signal(:,i));
    Signal_length = length(wave_norm);
    record_time = zeros(1);
    for n = 1:Signal_length
        if wave_norm(n) >= 0.1
            record_time(j) = n;
            j = j+1;
        end
    end
    if (record_time(end) - record_time(1))*dt(i) > 5*T1
        SelectSignalName1(p) = SignalName(i);
        Duration(p) = (record_time(end) - record_time(1))*dt(i);
        Signal1(1:length(Signal(:,i)),p) = Signal(:,i);
        dt1(p) = dt(i);
        p = p+1;        
    end
end
if p == 1
    disp('无满足条件的地震波')
end
total = length(SelectSignalName1);

%% 条件二：统计意义相符1
% 所谓“在统计意义上相符”指的是，多组时程波的平均地震影响系数曲线与振型分解反应谱法所用的地震影响系数曲线相比，在对应于结构主要振型的周期点上相差不大于20%

% 计算地震波主要周期的反应谱值
T_main = [T1 T2 T3];
for n = 1:total
    %----------------地震波信息--------------------%  
    wave_RS = Signal1(:,n);    
    wave_RS = wave_RS./max(abs(wave_RS));   
    for Tn = 1:3
        %----------------结构基本信息输入--------------------%
        w = 2*pi/T_main(Tn);
        mass = 1;
        k = w^2*mass;
        h = 0.05;
        c = 2*h*mass*w;
        steps = length( wave_RS ) - 1;
        a1 = wave_RS ( 1 : steps );
        a2 = wave_RS ( 2 : steps+1 );
        da = (a2 - a1);
        dis_rec = zeros(1);
        vel_rec = zeros(1);
        acc_rec = zeros(1);
        acc_ab = zeros(1);
            %-------------------Newmark-β法--------------------%
        for i = 1:steps
            acc_ab(i) = acc_rec(i) + wave_RS(i);
            kxin  = ( k + 2*c/dt1(n) + mass*4/(dt1(n)^2));
            dpxin = (-mass*da(i)+(4/dt1(n))*mass*vel_rec(:,i)+2*mass*acc_rec(:,i)+2*c*vel_rec(:,i));
            ddis  = kxin\dpxin;
            dis_rec(i+1) = dis_rec(i) + ddis;
            dvel  = 2/dt1(n)*ddis-2*vel_rec(:,i);
            vel_rec(i+1)= vel_rec(i) + dvel;
            dacc  = 4/(dt1(n)^2)*ddis-(4/dt1(n)).*vel_rec(:,i)-2.*acc_rec(:,i);
            acc_rec(i+1) = acc_rec(i) + dacc;
        end
        acc_ab(steps) =acc_rec(steps) +wave_RS(steps);
        %-------------------记录反应谱数值--------------------%
        acc_T_RS(Tn,n) = max( abs( acc_ab) );
    end
end
% 计算标准反应谱
alpha_max = 0.45; %由于归一化计算，峰值不重要，不作为控制参数
% 隔震反应谱
for T = 0.01:0.01:6
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
% 抗震反应谱
% for T = 0.01:0.01:6
%     j = round(100*T);
%     h = 0.05;
%     r = 0.9 + (0.05 - h) / (0.3 + 6 * h);
%     n1 = 0.02 + (0.05 - h)/(4 + 32*h);
%     n2 = 1 + (0.05 - h) / (0.08 +1.6 * h);
%     if T < 0.1
%         alpha(j) = 0.45*alpha_max + (n2 * alpha_max - 0.45 * alpha_max) / 0.1 * T;
%     elseif 0.1 <= T  &&  T < Tg
%         alpha(j) = n2 * alpha_max;
%     elseif T >= Tg && T<5*Tg
%         alpha(j) = (Tg / T)^r * n2 * alpha_max;
%     else
%         alpha(j) = alpha_max * (n2 * 0.2^r -n1 * (T - 5 * Tg));
%     end
% end
alpha = alpha./0.45/alpha_max;
% 计算主要周期点差值
T1 = round(T1*100);
T2 = round(T2*100);
T3 = round(T3*100);
j = 1;
for n = 1:total
    if abs(alpha(T1)-acc_T_RS(1,n))/alpha(T1) <= 0.2 && ...
    abs(alpha(T2)-acc_T_RS(2,n))/alpha(T2) <= 0.2 && ...
    abs(alpha(T3)-acc_T_RS(3,n))/alpha(T3) <= 0.2
        SelectSignalName2(j) = SelectSignalName1(n); %记录符合条件的地震波名称及编号
        store_num(j) = n;
        Signal2(1:length(Signal1(:,n)),j) = Signal1(:,n);
        dt2(j)  = dt1(n);
        Duration2(j,1) = Duration(n);
        deviation_T1(j,1) = abs(alpha(T1)-acc_T_RS(1,n))/alpha(T1);
        deviation_T2(j,1) = abs(alpha(T2)-acc_T_RS(2,n))/alpha(T2);
        deviation_T3(j,1) = abs(alpha(T3)-acc_T_RS(3,n))/alpha(T3);
        j = j+1;
    end   
end
if j == 1
    disp('无满足条件的地震波')
end 
total = length(SelectSignalName2);
% %% 条件三：统计意义相符2
% % 计算结果在结构主方向的平均底部剪力一般不会小于振型分解反应谱法计算结果的80%，每条地震波输入的计算结果不会小于65%。从工程角度考虑,这样可以保证时程分析结果满足最低安全要求。但计算结果也不能太大,每条地震波输入计算不大于135%,平均不大于120%
% 
% if condition == 1
%     % 时程分析                                                                        
%     cn=length(m0);                                                                              % DOF
%     m=diag(m0);                                                                                 % 生成质量矩阵
%     kxi1=0.05; kxi2=0.05;                                                                       % 阻尼比
%     for j = 1:total                                                                              
%         wave_THA = Signal2(:,j);    
%         wave_THA = 2*wave_THA./max(abs(wave_THA));        %假设8度中震         %归一化地震波
%         steps = length(wave_THA)-1;                                                             % 计算次数
%         ag    = wave_THA;                                                                       % 调幅最大值为70cm/s^2
%         ag1   = ag(1:steps);                                   
%         ag2   = ag(2:steps+1);                                 
%         dag   = (ag2-ag1);                                                                      % i+1时刻地震波加速度-i时刻地震波加速度
%         chsh=zeros(cn,1);                                                                       % 定义初始0矩阵
%         dis_cj=chsh;vel_cj=chsh;acc_cj=chsh;fv_inter=chsh;                                      % 层间位移、速度、加速度、剪力
%         dis_inter_rec=chsh;vel_inter_rec=chsh;acc_inter_rec=chsh;fv_inter_rec=chsh;             % 储存层间位移、速度、加速度、剪力
%         dis=chsh;vel=chsh;acc=chsh;                                                             % 绝对位移、速度、加速度、剪力（相对地面）
%         dis_abs_rec=chsh;vel_abs_rec=chsh;acc_abs_rec=chsh;                                     % 储存绝对位移、速度、加速度、剪力
%         unit=ones(cn,1);                                                                        % 定义 1列向量
%         for i = 1:steps                                                                         % 计算一条地震波
%             [k_mat]   = Form_k_mat(k0',cn);                                                     % 形成刚度矩
%             [C_mat]   = Form_C_mat(m,k_mat,kxi1,kxi2,cn);                                       % 形成阻尼矩阵
%             [dis_tem] = inter_to_abs(dis_cj,cn);                                                % 层间位移 --> 绝对位移
%             [vel_tem] = inter_to_abs(vel_cj,cn);                                                % 层间速度 --> 绝对速度
%             [acc_tem] = inter_to_abs(acc_cj,cn);                                                % 层间加速度 --> 绝对加速度
%             %--------------------------数值方法Newmark-β法--------------------------%
%             kxin  = ( k_mat + 2*C_mat/dt2(j) + m*4/(dt2(j)^2));
%             dpxin = (-m*unit*dag(i)+(4/dt2(j))*m*vel_abs_rec(:,i)+2*m*acc_abs_rec(:,i)+2*C_mat*vel_abs_rec(:,i));
%             ddis  = kxin\dpxin;
%             dis   = dis_tem + ddis;
%             dvel  = 2/dt2(j)*ddis-2*vel_abs_rec(:,i);
%             vel   = vel_tem + dvel;
%             dacc  = 4/(dt2(j)^2)*ddis-(4/dt2(j)).*vel_abs_rec(:,i)-2.*acc_abs_rec(:,i);
%             acc   = acc_tem + dacc;
%             %-----------------------------------------------------------------------%
%             [dis_cj] = abs_to_inter(dis,cn);                                                % 绝对位移 转化 层间位移
%             [vel_cj] = abs_to_inter(vel,cn);                                                % 绝对速度 转化 层间速度
%             [acc_cj] = abs_to_inter(acc,cn);                                                % 绝对加速度 转化 层间加速度
%             fv_inter = k0'.*dis_cj;                                                         % 计算层间剪力
%             dis_inter_rec = [dis_inter_rec dis_cj];                                         % 储存层间位移
%             vel_inter_rec = [vel_inter_rec vel_cj];                                         % 储存层间速度
%             acc_inter_rec = [acc_inter_rec acc_cj];                                         % 储存层间加速度
%             fv_inter_rec  = [fv_inter_rec fv_inter];                                        % 储存层间剪力
%             dis_abs_rec = [dis_abs_rec dis*1000];                                           % 储存绝对位移
%             vel_abs_rec = [vel_abs_rec vel];                                                % 储存绝对速度
%             acc_abs_rec = [acc_abs_rec acc];                                                % 储存绝对加速度
%         end                                                                                 % 一条波计算完成
%         for q = 1:cn                                                                        % 计算每一条波的层间剪力、层间位移角最大值
%                 Fv_THA(q,j) = max( abs( fv_inter_rec(q,:) ) )./1000;                        % 储存最大层间剪力
%         end    
%     end
%     % 振型分解反应谱法
%     [v , w] = eig(m\k_mat);       
%     [Period,order] = sort( 2*pi./diag(sqrt(w)), 'descend');
%     v(:,[1:cn]') = v(:,order); %振型排序
%     for i = 1:cn
%         vibration(:,i) = v(:,i)./v(cn,i); %振型归一化
%     end
%     G = m0' * 10; %重力
%     for i = 1:cn
%         coef1 = vibration(:,i).*G;
%         coef2 = (vibration(:,i).^2).*G;
%         gama(i,:) = sum(coef1)./sum(coef2); % 质量参与系数
%     end
%     alpha_max = 0.45; %假设8度中震
%     for i = 1:cn
%         if Period(i) < 0.1
%                alpha1 = 0.45*alpha_max + (n1 * alpha_max - 0.45 * alpha_max) / 0.1 * Period(i);
%            elseif 0.1 <= Period(i)  &&  Period(i) < Tg
%                alpha1 = n1 * alpha_max;
%            elseif Period(i) >= Tg && Period(i)<5*Tg
%                alpha1 = (Tg / Period(i))^r * n1 * alpha_max;
%            end
%         S(:,i) = sum(alpha1*gama(i).*vibration(:,i).*G);                   % 计算第i个振型的底部剪力
%     end
%     Fv_RS = sqrt(sum(S.^2))./1000;                                         % SRSS
%     j = 1; %临时变量存储符合条件的地震波数量
%     for i = 1:total
%         if 0.65 < Fv_THA(1,i)/Fv_RS && Fv_THA(1,i)/Fv_RS < 1.2
%             SelectSignalName3(j) = SelectSignalName2(i);
%             Signal3(1:length(Signal2(:,i)),j) = Signal2(:,i);
%             store_num3(j) =  store_num(i);
%             dt3(j)  = dt2(i);
%             Duration3(j,1) = Duration2(i);
%             deviation_RStoTHA(j,1) = Fv_THA(1,i)/Fv_RS;
%             deviation3_T1(j,1) = deviation_T1(i);
%             deviation3_T2(j,1) = deviation_T2(i);
%             deviation3_T3(j,1) = deviation_T3(i);
%             j = j+1;
%         end    
%     end
%     if j == 1
%         disp('无满足条件的地震波')
%     end
%     total = length(SelectSignalName3);
% 
% else
%     SelectSignalName3 = SelectSignalName2;
%     Signal3 = Signal2;
%     store_num3 =  store_num;
%     dt3 = dt2;
%     Duration3 = Duration2;
%     deviation3_T1 = deviation_T1;
%     deviation3_T2 = deviation_T2;
%     deviation3_T3 = deviation_T3;
%     j = j+1;    
% end

%% 绘制符合条件地震波的反应谱

% for n = 1:total
%     %----------------地震波信息--------------------%  
%     wave_RS = Signal3(:,n);    
%     wave_RS = wave_RS./max(abs(wave_RS));   
%     for T = 0.01:0.01:6
%         %----------------结构基本信息输入--------------------%
%         w = 2*pi/T;
%         mass = 1;
%         k = w^2*mass;
%         h = 0.05;
%         c = 2*h*mass*w;
%         steps = length( wave_RS ) - 1;
%         a1 = wave_RS ( 1 : steps );
%         a2 = wave_RS ( 2 : steps+1 );
%         da = (a2 - a1);
%         dis_rec = zeros(1);
%         vel_rec = zeros(1);
%         acc_rec = zeros(1);
%         acc_ab = zeros(1);
%         %-------------------Newmark-β法--------------------%
%         for i = 1:steps
%             acc_ab(i) = acc_rec(i) + wave_RS(i);
%             kxin  = ( k + 2*c/dt3(n) + mass*4/(dt3(n)^2));
%             dpxin = (-mass*da(i)+(4/dt3(n))*mass*vel_rec(:,i)+2*mass*acc_rec(:,i)+2*c*vel_rec(:,i));
%             ddis  = kxin\dpxin;
%             dis_rec(i+1) = dis_rec(i) + ddis;
%             dvel  = 2/dt3(n)*ddis-2*vel_rec(:,i);
%             vel_rec(i+1)= vel_rec(i) + dvel;
%             dacc  = 4/(dt3(n)^2)*ddis-(4/dt3(n)).*vel_rec(:,i)-2.*acc_rec(:,i);
%             acc_rec(i+1) = acc_rec(i) + dacc;
%         end
%         acc_ab(steps) = acc_rec(steps) + wave_RS(steps);
%         %-------------------记录反应谱数值--------------------%
%         j = round(100*T);
%         acc_RS(j,n) = max( abs( acc_ab) );
%         %记录速度、位移伪谱，需要可plot
%         vel_RS(j,n) = max( vel_rec );
%         dis_RS(j,n) = max( dis_rec );
%     end
% end
% for i = 1:600
%     acc_mean(i,1) = mean(acc_RS(i,:));
% end
%% 结果输出

close
disp(['符合条件的波有',num2str(length(SelectSignalName3)),'条,分别为'])
mkdir ([Path,'\Result']) % 创建文件夹
cd (Path) %更改路径
plot(0.01:0.01:6,alpha,'k','LineWidth',2)
hold on
plot(0.01:0.01:6,acc_mean,'b','LineWidth',2)
legend('归一化标准反应谱','待选地震波平均反应谱')
xlabel('周期');title('反应谱')
for i = 1:length(SelectSignalName3)
    disp(cell2mat(SelectSignalName3(i)))
    plot(0.01:0.01:6,acc_RS(:,i),'--','LineWidth',0.1,'HandleVisibility','off')
    copyfile( cell2mat(SelectSignalName3(i)) , [Path,'\result'])  %复制文件到Result文件夹        
end
hold off
grid on
if condition == 1
    s1 = {'Deviation_T1','Deviation_T2','Deviation_T3','Effective Duration','Deviation_RStoTHA'};
    table(deviation3_T1,deviation3_T2,deviation3_T3,Duration3,deviation_RStoTHA,...
        'RowNames',SelectSignalName3,'VariableNames',s1)
else
    s1 = {'Deviation_T1','Deviation_T2','Deviation_T3','Effective Duration'};
        table(deviation3_T1,deviation3_T2,deviation3_T3,Duration3,...
            'RowNames',SelectSignalName3,'VariableNames',s1)
end
%% 函数

function [avd] = inter_to_abs(inavd,cn) 
% 层间响应->绝对响应 
    avd(1) = inavd(1); 
    for i = 2:cn 
        avd(i) = avd(i-1)+inavd(i); 
    end 
    avd=avd'; 
end

function [inavd] = abs_to_inter(avd,cn) 
% 绝对响应->层间响应 
    inavd(1) = avd(1); 
    for i = 2:cn 
        inavd(i) = avd(i)-avd(i-1); 
    end 
    inavd = inavd'; 
end

function [k_mat] = Form_k_mat(korc,cn)                % structural stiffness matrix 
% 生成刚度矩阵 
    k_mat = zeros(cn);                                % matrix of 0
    for i = 1:cn-1
       k_mat(i,i) = korc(i)+korc(i+1);                % Ki,i=ki+k(i+1)
       k_mat(i,i+1) = -korc(i+1);                     % Ki,(i+1)=-k(i+1)
       k_mat(i+1,i) = -korc(i+1);                     % K(i+1),i=-k(i+1) 
    end
    k_mat(cn,cn) = korc(cn);                          % Kcn,cn=kcn  
end

function [C_mat] = Form_C_mat(m,k_mat,kxi1,kxi2,cn) 
% 生成瑞利阻尼矩阵 
    [~,www] = eig(m\k_mat); 
    www = sqrt(www); 
    w = sort(diag(www));   % vibration frequency 
    a = 2*w(1)*w(2)*(kxi1*w(2)-kxi2*w(1))/(w(2)^2-w(1)^2); 
    b = 2*(kxi2*w(2)-kxi1*w(1))/(w(2)^2-w(1)^2); 
    C_mat = a*m+b*k_mat;   
end