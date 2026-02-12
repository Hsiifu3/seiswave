function alpha_KangZhen=alpha_standspectrum(Tg,alpha_max,dT,aksai)
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
       alpha_KangZhen=zeros(1,N);                                          % 预先给alpha_GeZhen分配内存
       for  i=1:N
           % 地震影响系数曲线第一段                      
           if(T(i)<=T1)
               alpha_KangZhen(i)=0.45*alpha_max+(T(i)/T1)*(ait2*alpha_max-0.45*alpha_max);  
           end
           % 地震影响系数曲线第二段
           if (T(i)>T1) && (T(i)<=Tg)
               alpha_KangZhen(i)=alpha_max*ait2;           
           end
           % 地震影响系数曲线第三段
           if (T(i)>Tg) && (T(i)<=5*Tg)
               alpha_KangZhen(i)=((Tg/T(i))^gama)*alpha_max*ait2;
           end
           % 地震影响系数曲线第四段
           if (T(i)>5*Tg) && (T(i)<=(6.0))
               alpha_KangZhen(i)=(ait2*0.2^gama-ait1*(T(i)-5*Tg))*alpha_max;
           end
           alpha_KangZhen=alpha_KangZhen(:);
       end
end