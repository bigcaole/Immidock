# ImmiDock 工作原理

## 系统架构

ImmiDock 采用模块化结构，主要包括：

- CLI：负责解析命令行参数，调用核心逻辑
- core：核心迁移能力（审计、打包、恢复、网络处理、远程迁移）
- adapters：适配特定平台（如 1Panel）
- utils：工具模块（日志、校验、系统检测、多语言）
- schemas：清单文件（manifest）规范

整体调用链：

CLI → core → adapters/utils → 输出迁移结果

## 迁移包结构

ImmiDock 生成的迁移包为 `backup.dsh`，它是一个 tar 包，包含：

- `manifest.json`：记录容器、网络、卷、镜像等元数据
- `images/`：导出的 Docker 镜像
- `volumes/`：数据卷归档（zstd 压缩）
- `networks`：网络信息包含在 manifest 中

示意结构：

```
backup.dsh
├── manifest.json
├── images/
│   ├── mysql.tar
│   └── redis.tar
└── volumes/
    ├── volume_1.tar.zst
    └── volume_2.tar.zst
```

## 恢复流程

恢复时主要步骤如下：

1. 解压迁移包
2. 恢复数据卷
3. 导入镜像
4. 创建网络
5. 重建容器
6. 启动容器

这样可以保证容器在恢复前就拥有完整的镜像和数据。

## 网络冲突处理

当目标服务器已有 Docker 网络时，可能出现子网冲突。

ImmiDock 会自动检测目标主机已占用的子网，并为冲突网络选择可用的新子网，例如：

- 已占用：172.18.0.0/16
- 冲突时自动改为：172.19.0.0/16

这样可以避免创建网络失败，并保证容器可以正常连接网络。
