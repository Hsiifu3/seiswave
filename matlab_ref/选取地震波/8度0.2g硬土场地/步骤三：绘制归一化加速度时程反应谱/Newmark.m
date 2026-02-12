%% 利用Newmarkβ结构的时程分析法函数
function [y,dy,ddy,ddy_ab,y_inter] = Newmark(k_mat,m_mat,c_mat,wave,dt)
% 返回体系相对位移、相对速度、相对加速度、绝对加速度，层间位移
L=length(wave);                                                            % 地震波离散点数                                                          
[dof,~]=size(k_mat);                                                       % 总自由度数
y(:,1)=zeros(dof,1);                                                       % 初始位移
dy(:,1)=zeros(dof,1);                                                      % 初始速度
ddy(:,1)=zeros(dof,1);                                                     % 初始加速度
E=ones(dof,1);                                                             % 单位向量
for i=1:L-1
    ddy_ab(:,i)=ddy(:,i)+wave(i);                                          % 体系绝对加速度 
    zacc=wave(i+1)-wave(i);                                                % 地震波加速度增量
    zy(:,i)=(k_mat+2*c_mat/dt+m_mat*4/(dt^2))\(-m_mat*zacc*E+(4/dt)*m_mat*dy(:,i)+2*m_mat*ddy(:,i)+2*c_mat*dy(:,i)); % 体系相对位移响应增量
    y(:,i+1)=y(:,i)+zy(:,i);                                               % 体系相对位移响应
    zdy(:,i)=2/dt*zy(:,i)-2*dy(:,i);                                       % 体系相对速度响应增量
    dy(:,i+1)=dy(:,i)+zdy(:,i);                                            % 体系相对速度响应
    zddy(:,i)=4/(dt^2)*zy(:,i)-(4/dt).*dy(:,i)-2.*ddy(:,i);                % 体系相对加速度响应增量
    ddy(:,i+1)=ddy(:,i)+zddy(:,i);                                         % 体系相对加速度响应
end
ddy_ab(:,L)=ddy(:,L)+wave(L);                                              % 体系绝对加速度最后一个增量步
y_inter(1,:)=y(1,:);                                                       % 第一层层间加速度
for j=2:dof
    y_inter(j,:)=y(j,:)-y(j-1,:);
end

