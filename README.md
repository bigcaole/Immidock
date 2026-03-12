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

重要说明：

- 不支持 Docker 镜像部署（不提供容器化运行）
- 仅支持直接部署到宿主机

## 安装方式

### 方式1：一键安装（小白推荐）

```bash
curl -sSL https://raw.githubusercontent.com/bigcaole/Immidock/main/install.sh | bash
```

### 方式2：下载 Release（二进制）

到 GitHub Releases 下载：

- `immidock-linux-amd64`

然后：

```bash
chmod +x immidock
sudo mv immidock /usr/local/bin/
```

### 方式3：pip 安装（适合有 Python 环境）

```bash
pip install immidock
```

### 方式4：源码安装（适合进阶用户）

```bash
git clone https://github.com/bigcaole/Immidock.git
cd ImmiDock
pip install -r requirements.txt
python -m dockshifter.cli.main doctor
```

## 使用示例

```bash
immidock doctor
immidock pack --output backup.dsh
immidock restore backup.dsh
immidock migrate root@server
```

## 最简使用流程（中文注释）

```bash
# 1. 在源服务器生成迁移包
immidock pack --output backup.dsh

# 2. 传输迁移包到新服务器
scp backup.dsh root@新服务器IP:/root/

# 3. 在新服务器恢复环境
immidock restore backup.dsh
```

提示：所有命令支持中文输出，例如：

```bash
immidock doctor --lang zh
immidock pack --lang zh --output backup.dsh
immidock restore --lang zh backup.dsh
```

小白模式（更详细中文提示）：

```bash
immidock pack --beginner --lang zh --output backup.dsh
immidock restore --beginner --lang zh backup.dsh
immidock migrate --beginner --lang zh root@server
```

## 发布说明（维护者）

使用 tag 触发 Release 构建：

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions 会自动构建二进制并发布到 Releases。

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
