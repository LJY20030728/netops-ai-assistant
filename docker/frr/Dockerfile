# FRR 容器镜像：frrouting/frr + openssh-server（供 Netmiko 走真实 SSH 到 vtysh）
# 说明：国内网络环境 Docker Hub(registry-1.docker.io) 直连超时，改用 quay.io 官方镜像源。
#       quay.io/frrouting/frr 基于 Alpine Linux，使用 apk 包管理（10.4.5）。
FROM quay.io/frrouting/frr:10.4.5

# 安装 SSH 服务端（FRR 官方镜像不带 sshd，Netmiko 需要 SSH 通道）
# 并启用 ospfd/bgpd 守护进程（镜像默认 bgpd=no/ospfd=no）
RUN apk add --no-cache openssh \
    && ssh-keygen -A \
    && mkdir -p /run/sshd \
    && adduser -D -s /bin/sh admin \
    && echo 'admin:admin123' | chpasswd \
    && (addgroup admin frr 2>/dev/null || true) \
    && (addgroup admin frrvty 2>/dev/null || true) \
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config \
    && sed -i 's/^bgpd=no/bgpd=yes/; s/^ospfd=no/ospfd=yes/' /etc/frr/daemons

EXPOSE 22

# sshd 后台监听 + FRR docker-start（watchfrr）前台守护协议进程
CMD ["sh", "-c", "/usr/sbin/sshd -D & /usr/lib/frr/docker-start"]
