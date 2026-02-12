%% 绘制隔震规范谱丨归一化地震影响系数曲线
% 提取0S到6S隔震结构标准反应谱对应的alpha值，步距一般为0.02S
% 阻尼比:                 0.05
% 烈度：                  8度（0.2g）
% 场地类别：              
% 特征周期：              由场地类别决定
clear;close;clc;
aksai = 0.05;             % 阻尼比
alpha_max = 0.45;         % 水平地震影响系数最大值【常遇地震】
Tg = 0.4;                 % 第二组，II类特征周期
T = 0:0.02:6;             % 隔震结构自振周期离散值（地震影响系数曲线横坐标）
dT = 0.02;                % 隔震结构自振周期增量，一般为0.02S
alpha_GeZhen = alpha_standspectrum_isolation(Tg,alpha_max,dT,aksai);       % 生成规范隔震反应谱——即地震影响系数曲线（alpha谱）
% alpha_GeZhen = alpha_GeZhen ./ (0.45 * alpha_max);                         % 归一化后的隔震规范设计反应谱
plot(T,alpha_GeZhen,'color',[1 0 0],'linewidth', 1.5)                      % 绘制隔震设计反应谱
grid on                   % 添加网格
xlabel('Period(s)','color','k','fontsize',10);                             % 添加x轴标签
ylabel('Normalized Design Spectrum','color','k','fontsize',10);            % 添加y轴标签
print(gcf, '-dpng', '隔震规范谱丨归一化.png')


%% 地震影响系数曲线（隔震）函数
% 输入：特征周期，水平地震影响系数最大值，隔震结构自振周期增量，阻尼系数
function alpha_GeZhen=alpha_standspectrum_isolation(Tg,alpha_max,dT,aksai)
       ait1=0.02+(0.05-aksai)/(4+32*aksai);                                % ait1为直线段的下降斜率调整系数，小于0时取0
       if(ait1<0)
           ait1=0;
       end
       ait2=1.0+(0.05-aksai)/(0.08+1.6*aksai);                             % ait2为阻尼调整系数，当小于0.55时应取0.55
       if(ait2<=0.55)
           ait2=0.55;
       end
       gama=0.9+(0.05-aksai)/(0.3+6*aksai);                                % 曲线下降段的衰减指数
       T1=0.10;                                                            % 地震影响系数曲线第一段（斜线段）结束标志
       N=floor(6.0/dT)+1;                                                  % N为隔震结构自振周期离散值个数；floor：朝负无穷大四舍五入
       T=0:dT:6.0;                                                         % 隔震结构自振周期离散值（地震影响系数曲线横坐标）
       alpha_GeZhen=zeros(1,N);                                            % 预先给alpha_GeZhen分配内存
       for  i=1:N
           % 隔震丨地震影响系数曲线第一段                      
           if(T(i)<=T1)
               alpha_GeZhen(i)=0.45*alpha_max+(T(i)/T1)*(ait2*alpha_max-0.45*alpha_max);  
           end
           % 隔震丨地震影响系数曲线第二段
           if (T(i)>T1) && (T(i)<=Tg)
               alpha_GeZhen(i)=alpha_max*ait2;           
           end
           % 隔震丨地震影响系数曲线第三段
           if (T(i)>Tg) && (T(i)<=(6.0))
               alpha_GeZhen(i)=((Tg/T(i))^gama)*alpha_max*ait2;
           end
           alpha_GeZhen=alpha_GeZhen(:);
       end
end




