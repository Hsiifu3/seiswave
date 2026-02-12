function [M,K,w,T,phi,gamma,M_par] = eigenvalue(m,k) 
%  M,K,w,T,phi,phi分别为结构质量矩阵、刚度矩阵以及各阶的自振频率，自振周期，模态，振型参与系数，振型参与质量
% 此函数通过求解K和M的广义特征值和特征向量，获得结构各阶的自振频率，自振周期，模态
dof=length(m);                               % 自由度
E=ones(dof,1);                               % 单位向量
M=diag(m);                                   % 质量矩阵
K=diag(k)+diag([k(2:end) 0])+diag(-k(2:end),1)+diag(-k(2:end),-1);         % 刚度矩阵
[phi,Lambda]=eig(K,M);                       % 返回广义特征值的对角矩阵 Omega 和满矩阵 phi，其列是对应的右特征向量，使得 K*phi = M*phi*Lambda
lambda=diag(Lambda);                         % 从对角矩阵 Omega提取广义特征值，广义特征值=w^2               
w=sqrt(lambda);                              % 圆频率w=广义特征值的平方根
T=2*pi./w;                                   % 周期
for j=1:dof
    M_gen=phi(:,j)'*M*phi(:,j);              % j振型广义质量
    gamma(j)=(phi(:,j)'*M*E)/M_gen;          % 求解j振型参与系数
    M_par(j)=M_gen*(gamma(j))^2;             % 振型参与质量
    M_par(j)=M_par(j)/sum(m);                % 质量参与系数
    [~,a]=max(abs(phi(:,j)));                % a为j振型向量中最大变形所在的序号
    phi(:,j)=phi(:,j)./phi(a,j);             % 对振型向量进行归一化
end
end
