# ImmiDock 快速开始

只需 3 步即可完成迁移：

## 第一步：在源服务器创建迁移包

```bash
immidock pack --output backup.dsh
```

说明：该命令会收集容器配置、镜像、数据卷和网络信息，并生成 `backup.dsh` 迁移包。

## 第二步：传输迁移包到新服务器

```bash
scp backup.dsh root@新服务器IP:/root/
```

说明：将迁移包复制到新服务器的 `/root/` 目录。把 `新服务器IP` 替换为真实 IP。

## 第三步：在新服务器恢复

```bash
immidock restore backup.dsh
```

说明：该命令会导入镜像、恢复数据卷、创建网络并重建容器，最终启动所有容器。
