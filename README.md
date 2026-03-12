# ImmiDock

Docker & 1Panel Migration Tool

ImmiDock is a DevOps tool for migrating Docker environments between hosts.

---

## Features

- Docker container migration
- Volume and image backup
- Network conflict resolution
- SSH remote migration
- 1Panel application synchronization
- Bundle checksum verification
- System diagnostics

---

## Installation

Download the binary from the Releases page.

Or run with Python:

```
python -m immidock.cli.main doctor
```

---

## Usage

```
immidock doctor
immidock pack --output backup.dsh
immidock restore backup.dsh
immidock migrate root@server
```

---

# 中文说明

ImmiDock 是一个用于迁移 Docker 和 1Panel 环境的 DevOps 工具。

可以实现：

- Docker 容器迁移
- 数据卷和镜像备份
- 网络冲突自动修复
- SSH 远程迁移
- 1Panel 应用自动同步
- 迁移包校验
- 系统环境检查

示例：

```
immidock doctor
immidock pack --output backup.dsh
immidock restore backup.dsh
immidock migrate root@server
```
