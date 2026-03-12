# ImmiDock 新手迁移教程

## 1 ImmiDock 是什么

ImmiDock 是一个用于迁移 Docker 和 1Panel 环境的工具，可以帮助你把一台服务器上的 Docker 容器、数据卷、镜像和网络配置完整迁移到另一台服务器。

适用场景：

- 服务器升级
- 更换云服务器
- 数据迁移
- 服务器备份

## 2 迁移流程概览

迁移流程很简单：

1. 在源服务器创建迁移包
2. 将迁移包传输到新服务器
3. 在新服务器恢复环境

流程示意：

源服务器 → 创建 backup.dsh → 传输文件 → 新服务器恢复

## 3 源服务器准备

源服务器需要满足：

- 已安装 Docker
- 可以使用 SSH 登录
- 已安装 ImmiDock

运行环境检查：

```bash
immidock doctor
```

该命令会检查：

- Docker
- tar
- zstd
- rsync
- ssh

## 4 创建迁移包

在源服务器执行：

```bash
immidock pack --output backup.dsh
```

说明：

该命令会自动收集：

- Docker 容器配置
- Docker 镜像
- 数据卷（Volumes）
- Docker 网络配置

最终生成一个文件：

`backup.dsh`

这是源服务器 Docker 环境的完整备份。

## 5 传输迁移包

使用 scp 传输文件：

```bash
scp backup.dsh root@新服务器IP:/root/
```

示例：

```bash
scp backup.dsh root@192.168.1.10:/root/
```

说明：

`192.168.1.10` 是新服务器 IP 地址。

## 6 新服务器准备

登录新服务器：

```bash
ssh root@新服务器IP
```

运行环境检查：

```bash
immidock doctor
```

如果缺少依赖，可以安装：

- Docker
- zstd
- rsync

## 7 恢复迁移包

在新服务器运行：

```bash
immidock restore backup.dsh
```

ImmiDock 会自动完成：

- 导入 Docker 镜像
- 恢复数据卷
- 创建 Docker 网络
- 重建容器
- 启动容器
- 同步 1Panel 应用（如存在）

恢复完成后，新服务器将拥有与源服务器相同的 Docker 环境。

## 8 验证迁移

检查容器：

```bash
docker ps
```

检查网络：

```bash
docker network ls
```

检查数据卷：

```bash
docker volume ls
```

若容器正常运行，说明迁移成功。

## 9 一键迁移命令

ImmiDock 支持一条命令直接迁移：

```bash
immidock migrate root@新服务器IP
```

该命令会自动完成：

- 创建迁移包
- 通过 SSH 传输数据
- 在新服务器恢复环境

用户无需手动复制 `backup.dsh`。

## 10 常见问题

- Docker 未安装
- 端口冲突
- 磁盘空间不足

建议先运行：

```bash
immidock doctor
```

检查系统环境并按提示处理。
