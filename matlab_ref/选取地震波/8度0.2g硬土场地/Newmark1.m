function [y,dy,ddy,ddy_ab,time] = Newmark(K,M,C,wave,dt,E)
%利用Newmarkβ结构的时程分析法函数
L=length(wave);
time=0:dt:(L-1)*dt;
[dof,~]=size(K);%自由度数
y(:,1)=zeros(dof,1);
dy(:,1)=zeros(dof,1);
ddy(:,1)=zeros(dof,1);

for i=1:L-1
    ddy_ab(:,i)=ddy(:,i)+wave(i);
    zacc=wave(i+1)-wave(i);
    zy(:,i)=(K+2*C/dt+M*4/(dt^2))\(-M*zacc*E+(4/dt)*M*dy(:,i)+2*M*ddy(:,i)+2*C*dy(:,i));
    y(:,i+1)=y(:,i)+zy(:,i);
    zdy(:,i)=2/dt*zy(:,i)-2*dy(:,i);
    dy(:,i+1)=dy(:,i)+zdy(:,i);
    zddy(:,i)=4/(dt^2)*zy(:,i)-(4/dt).*dy(:,i)-2.*ddy(:,i);
    ddy(:,i+1)=ddy(:,i)+zddy(:,i);
end
ddy_ab(:,L)=ddy(:,L)+wave(L);
end

