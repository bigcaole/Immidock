# ImmiDock

Docker 环境迁移工具

## 项目简介

ImmiDock 是一个用于迁移 Docker 与 1Panel 应用环境的工具。

支持：

- Docker 容器迁移
- Docker 数据卷迁移
- Docker 网络恢复
- SSH 跨服务器迁移
- 1Panel 应用同步

## 安装方式

### 方式1：一键安装

```bash
curl -sSL https://raw.githubusercontent.com/bigcaole/Immidock/main/install.sh | bash
```

### 方式2：下载 Release

到 GitHub Releases 下载：

- `immidock-linux-amd64`

然后：

```bash
chmod +x immidock
sudo mv immidock /usr/local/bin/
```

### 方式3：pip 安装

```bash
pip install immidock
```

## 使用示例

```bash
immidock doctor
immidock pack --output backup.dsh
immidock restore backup.dsh
immidock migrate root@server
```

# 小白迁移教程（一步一步）

下面是最简单的迁移流程，适合新手用户。

## Step 1 源服务器安装 ImmiDock

在源服务器执行：

```bash
immidock doctor
```

这个命令会检查 Docker、tar、zstd、rsync、ssh 是否可用。

## Step 2 创建迁移包

```bash
immidock pack --output backup.dsh
```

该命令会自动收集容器配置、镜像、数据卷和网络信息，并生成 `backup.dsh`。

## Step 3 传输迁移包

```bash
scp backup.dsh root@新服务器IP:/root/
```

示例：

```bash
scp backup.dsh root@192.168.1.10:/root/
```

## Step 4 新服务器恢复

登录新服务器后执行：

```bash
immidock restore backup.dsh
```

ImmiDock 会自动导入镜像、恢复数据卷、创建网络并启动容器。
