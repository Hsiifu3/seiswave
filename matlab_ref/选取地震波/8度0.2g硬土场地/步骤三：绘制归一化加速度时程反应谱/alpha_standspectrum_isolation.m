%% 地震影响系数曲线（隔震）函数
% 输入：特征周期，水平地震影响系数最大值，隔震结构自振周期增量，阻尼系数
function alpha_GeZhen=alpha_standspectrum_isolation(Tg,alpha_max,dT,aksai)
       ait=1.0+(0.05-aksai)/(0.08+1.6*aksai);       % ait为阻尼调整系数，当小于0.55时应取0.55
       if(ait<=0.55)
           ait=0.55;
       end
       gama=0.9+(0.05-aksai)/(0.3 + 6*aksai);       % 曲线下降段的衰减指数
       T1=0.10;                                     % 地震影响系数曲线第一段（斜线段）结束标志
       N=floor(6.0/dT)+1;                           % N为隔震结构自振周期离散值个数；floor：朝负无穷大四舍五入
       T= 0:dT:6.0;                                 % 隔震结构自振周期离散值（地震影响系数曲线横坐标）
       alpha_GeZhen=zeros(1,N);                     % 预先给alpha_GeZhen分配内存
       for  i=1:N
       % 地震影响系数曲线第一段                      
       if(T(i)<=T1)
           alpha_GeZhen(i)=0.45*alpha_max + (T(i)/T1)*(ait*alpha_max-0.45*alpha_max);  
       end
       % 地震影响系数曲线第二段
       if (T(i)>T1) && (T(i)<=Tg)
           alpha_GeZhen(i)=alpha_max*ait;           
       end
       % 地震影响系数曲线第三段
       if (T(i)>Tg) && (T(i)<=(6.0))
           alpha_GeZhen(i)=((Tg/T(i))^gama)*alpha_max*ait;
       end
       alpha_GeZhen=alpha_GeZhen(:);
       end
end