# Wezza MC 使用手册

这是 Wezza MC 私人模组服务器的完整管理文档。服务器运行在自己的 Windows 电脑上：需要玩时手动启动，不玩时安全关闭。

- 服务器信息页：<https://izumichan16.github.io/wezza-mc/>
- GitHub 仓库：<https://github.com/izumiChan16/wezza-mc>
- 项目目录：`/home/izumi/wezza_mc`

如果你只是来玩的，请直接阅读[玩家加入方法](#玩家加入方法)。如果你负责开服和修改模组，请从头阅读本文。

## 目录

- [先理解几个名词](#先理解几个名词)
- [整个系统如何工作](#整个系统如何工作)
- [当前服务器配置](#当前服务器配置)
- [修改本机配置](#修改本机配置)
- [第一次开服](#第一次开服)
- [玩家加入方法](#玩家加入方法)
- [日常开服和关服](#日常开服和关服)
- [玩家和管理员权限](#玩家和管理员权限)
- [添加、更新和删除模组](#添加更新和删除模组)
- [测试并发布模组变更](#测试并发布模组变更)
- [Git 和 GitHub 的日常使用](#git-和-github-的日常使用)
- [备份和恢复](#备份和恢复)
- [异地备份](#异地备份)
- [升级 Minecraft 大版本](#升级-minecraft-大版本)
- [换电脑或重新部署](#换电脑或重新部署)
- [目录和文件说明](#目录和文件说明)
- [故障排查](#故障排查)
- [命令速查](#命令速查)

## 先理解几个名词

不需要先学会这些工具才能开服。这里只说明它们各自负责什么。

### Minecraft 服务器

真正保存世界、计算生物和处理玩家联机的程序。这个项目使用 Minecraft Java 版服务器。

### 模组与 Fabric

模组是修改或扩展游戏的 `.jar` 文件。Fabric 是让 Minecraft 能加载这些模组的工具。

这里口语中说的“插件”实际应按 **Fabric 模组** 管理。本服务器不是 Paper/Spigot 服务端，不能直接安装 Bukkit、Spigot 或 Paper 插件。

服务器和玩家不一定安装完全相同的模组：

- **双方**：服务器和所有玩家都要安装，例如 Refined Storage。
- **仅服务端**：只改善服务器性能，玩家不需要安装，例如 ServerCore。
- **仅客户端**：只改善玩家画面或性能，服务器不需要安装，例如 Sodium。

### Docker Desktop

Docker 把服务器程序、Java 和运行环境放在容器中。这样不用在 WSL 中手动安装 Java，也不会把服务器依赖散落到 Windows 系统里。

### WSL

Windows 中的 Linux 环境。本项目放在 Arch Linux WSL 的 `/home/izumi/wezza_mc`，管理命令也在这里运行。

### PCL2 与 MRPACK

PCL2 是本项目面向玩家说明的启动器。服务器页面提供的是标准 Modrinth 整合包文件（`.mrpack`），PCL2 会在导入时读取其中的下载地址和哈希并取得客户端需要的模组。

`.mrpack` 是一个版本快照，不会让已经导入的游戏实例永久自动同步。后续如何更新取决于这次发布的类型：少量变更可以按更新页手动处理；大批变更或游戏版本升级需要导入新的 `.mrpack`。

### Packwiz

管理员使用的模组清单工具。它记录每个模组的下载位置、版本、安装侧和文件哈希。玩家不需要操作 Packwiz。

### GitHub Pages

一个公开静态地址，用来放基本服务器信息、更新说明和 `.mrpack` 下载。它不是 Minecraft 服务器，也不保存世界。

## 整个系统如何工作

```text
玩家电脑
  PCL2 ──导入标准 .mrpack 并下载客户端模组──> GitHub Pages / 模组源站
       │
       └────────使用服务器地址联机─────────────┐
                                              │
Windows 电脑                                  ▼
  内网穿透客户端 ──转发 127.0.0.1:25565──> Minecraft 容器
                                              │
Arch WSL                                      ├── runtime/data：世界
  ./mcctl ──管理 Docker Desktop───────────────└── runtime/backups：备份
```

需要记住的只有四点：

1. `./mcctl` 是管理员的统一入口。
2. `runtime/data` 是正式世界，不能随意删除。
3. 改模组后必须先测试，再发布给服务器和玩家。
4. `.mrpack` 代表一个确定版本；已有玩家不会在启动游戏时自动更新。

## 当前服务器配置

### 基本设置

| 设置 | 当前值 |
|---|---|
| Minecraft | Java 版 26.1.2 |
| Fabric Loader | 0.19.3 |
| Java | 25 |
| 游戏模式 | 生存 |
| 难度 | 困难 |
| 最大玩家数 | 10 |
| 白名单 | 开启 |
| 正版验证 | 开启 |
| PVP | 开启 |
| 命令方块 | 关闭 |
| 视距 | 10 |
| 模拟距离 | 8 |
| 默认服务端内存 | 5 GB |
| 正式服本机端口 | `127.0.0.1:25565` |
| 测试服本机端口 | `127.0.0.1:25566` |

### 当前模组

| 模组 | 版本 | 安装位置 | 用途 |
|---|---:|---|---|
| Fabric API | 0.155.2 | 双方 | Fabric 模组基础依赖 |
| Refined Storage | 3.2.1 | 双方 | 存储与自动化内容 |
| Time in a Bottle | 7.0.1 | 双方 | 时间积累与方块加速 |
| FerriteCore | 9.0.0 | 双方 | 降低内存占用 |
| Lithium | 0.24.7 | 服务端 | 游戏逻辑性能优化 |
| Krypton | 0.3.0 | 服务端 | 网络性能优化 |
| ServerCore | 1.5.19 | 服务端 | 服务端性能优化 |
| spark | 1.10.173 | 服务端 | 性能诊断 |
| Sodium | 0.9.1 | 客户端 | 渲染性能优化 |

## 修改本机配置

本机设置保存在 `.env`，不会上传 GitHub。编辑它：

```bash
nano .env
```

| 设置 | 默认值 | 说明 |
|---|---:|---|
| `EULA` | `FALSE` | 本人接受 Minecraft EULA 后改为 `TRUE` |
| `PACKWIZ_URL` | 已配置 | 正式模组清单地址，不要随意修改 |
| `MC_PORT` | `25565` | 正式服只在本机回环地址监听的端口 |
| `STAGING_PORT` | `25566` | 隔离测试服端口 |
| `MEMORY` | `5G` | 正式服 Java 最大内存 |
| `STAGING_MEMORY` | `5G` | 测试服 Java 最大内存 |
| `TZ` | `Asia/Taipei` | 日志和备份时间所用时区 |
| `MOTD` | `Wezza Fabric 26.1.2` | 多人游戏列表中显示的服务器名称 |
| `MAX_PLAYERS` | `10` | 最大同时在线人数 |
| `PUID` / `PGID` | `1000` | WSL 中生成 Packwiz 文件时使用的用户 ID |
| `ENABLE_REMOTE_BACKUP` | `false` | 是否在安全关服时执行 restic/S3 备份 |

修改端口后，Windows 内网穿透目标也必须改成相同端口。修改内存、MOTD 或人数后需要安全重启服务器才会生效。

不要把服务器内存设置得接近电脑全部可用内存。还要给 Windows、Docker Desktop、客户端和文件缓存保留空间。

`compose.yaml` 保存所有人都应一致的服务器规则，例如难度、视距和正版验证。需要修改这些规则时，应编辑 `compose.yaml`、验证配置、提交并推送：

```bash
docker compose config --quiet
git add compose.yaml
git commit -m "chore: update server settings"
git push
```

对于已经由 Compose 环境变量管理的设置，不要只修改 `runtime/data/server.properties`；下次创建容器时可能会再次由 Compose 值覆盖。

## 第一次开服

GitHub 仓库、Pages、Packwiz 地址和本地密钥已经配置完成。第一次正式启动前还需要完成以下操作。

### 1. 检查 Docker Desktop

启动 Windows 上的 Docker Desktop，并在设置中确认已经启用 Arch WSL integration。

在 Arch WSL 中执行：

```bash
cd /home/izumi/wezza_mc
docker info
docker compose version
```

两条命令都成功后再继续。项目应保留在 WSL 的 Linux 文件系统中，不要移动到 `/mnt/c`。

### 2. 接受 Minecraft EULA

阅读 [Minecraft EULA](https://aka.ms/MinecraftEULA)。只有在你本人接受后，才能编辑 `.env`：

```bash
nano .env
```

把：

```text
EULA=FALSE
```

改为：

```text
EULA=TRUE
```

不要修改已经配置好的 `PACKWIZ_URL`。

### 3. 启动正式服

```bash
./mcctl start
```

首次启动需要下载 Minecraft 服务端、Fabric 和模组，时间会比以后更长。命令会等待服务器通过健康检查。

另开一个 WSL 终端查看日志：

```bash
cd /home/izumi/wezza_mc
./mcctl logs
```

看到服务器完成启动后，用 `Ctrl+C` 退出日志查看不会关闭服务器。

### 4. 配置内网穿透

Windows 上现有的内网穿透客户端只转发：

```text
127.0.0.1:25565 TCP
```

不要转发以下内容：

- `25566`：隔离测试服端口。
- RCON：内部管理接口，没有对主机公开。
- Docker 或 WSL 的其他端口。

玩家实际填写的服务器地址由内网穿透服务提供，而不是 `127.0.0.1`。

### 5. 添加白名单

服务器运行后执行：

```bash
./mcctl whitelist add 玩家Java版名称
```

每位玩家都必须使用正版 Java 版名称并加入白名单。

## 玩家加入方法

管理员需要把以下三样东西告诉玩家：

1. 服务器信息页：<https://izumichan16.github.io/wezza-mc/>
2. 内网穿透提供的服务器地址。
3. 已经确认该玩家进入白名单。

玩家按以下步骤操作：

1. 安装并打开 PCL2。
2. 在服务器信息页点击“下载 MRPACK”，得到 `wezza-mc-latest.mrpack`。
3. 把 `.mrpack` 直接拖入 PCL2，或使用 PCL2 的导入整合包功能；不要先解压。
4. 等待 PCL2 在导入过程中下载模组并创建版本。
5. 确认该版本使用 Java 25，建议分配 6 GB 内存。
6. 启动游戏，在多人游戏中添加管理员提供的服务器地址。

服务器专用模组会在 `.mrpack` 中标为客户端不支持，PCL2 导入时不会安装它们。

以后能否继续使用原版本，以[更新说明页](https://izumichan16.github.io/wezza-mc/updates.html)为准：

- **小更新**：页面会列出要添加、替换或删除的准确文件。已有玩家可以手动修改该版本的 `mods` 目录，不必重新导入；新玩家直接导入当前 `.mrpack`。
- **完整更新**：页面会明确要求重新导入。通常用于 Minecraft/Fabric 升级、大批模组变化或依赖关系复杂的变更。建议创建新版本，确认存档和设置无误后再删除旧版本。

不要混用不同发布版本的模组，也不要看到某个模组有新版就自行更新；服务器和客户端版本可能因此不一致。

## 日常开服和关服

### 推荐开服顺序

1. 启动 Docker Desktop。
2. 启动 Windows 内网穿透客户端。
3. 打开 Arch WSL。
4. 进入项目并开服：

```bash
cd /home/izumi/wezza_mc
./mcctl start
```

5. 用下面的命令确认状态：

```bash
./mcctl status
```

6. 通知玩家服务器已经开放。

重复执行 `start` 不会启动第二份正式服务器，而是提示服务器已经运行。

### 推荐关服顺序

先通知玩家，然后执行：

```bash
./mcctl stop
```

该命令会：

1. 在游戏内广播 10 秒关服提示。
2. 保存世界并刷新磁盘数据。
3. 创建本机备份。
4. 如果已配置异地备份，再执行一次异地备份。
5. 优雅关闭服务器和定时备份容器。

确认命令完成后，才能关闭内网穿透、Docker Desktop、Windows 或让电脑睡眠。

如果异地备份暂时不可用，`stop` 会让服务器保持运行。确认本机备份存在后可以跳过本次异地备份：

```bash
./mcctl stop --skip-remote
```

### 查看状态和日志

```bash
./mcctl status
./mcctl logs
```

`logs` 会持续显示新日志。按 `Ctrl+C` 只退出日志查看，不会停服。

### 重启

```bash
./mcctl restart
```

该命令会完整执行安全关服流程，然后重新启动。不要用 Docker Desktop 的强制停止代替它。

## 玩家和管理员权限

### 白名单

```bash
./mcctl whitelist add 玩家名
./mcctl whitelist remove 玩家名
./mcctl whitelist list
```

### OP 管理员

授予或撤销游戏管理员权限：

```bash
./mcctl rcon "op 玩家名"
./mcctl rcon "deop 玩家名"
```

只给可信任的人 OP 权限。

### 发送其他 Minecraft 命令

```bash
./mcctl rcon "list"
./mcctl rcon "say 十分钟后关服"
./mcctl rcon "time set day"
```

命令中不要写游戏内使用的 `/` 前缀。

### 进入服务器控制台

```bash
./mcctl console
```

使用 `Ctrl+P`、`Ctrl+Q` 依次按下以分离控制台。不要按 `Ctrl+C` 强制终止服务器。

## 添加、更新和删除模组

### 修改前先检查

添加任何模组前确认：

- 明确支持 Minecraft 26.1.2。
- 明确提供 Fabric 版本，不是 NeoForge 或 Forge 文件。
- 所有前置依赖也支持相同版本。
- 知道它是客户端、服务端还是双方安装。
- 如果会增加世界生成内容，理解删除或回退时可能损坏世界。
- 如果不来自 Modrinth，确认作者允许对应的下载或再分发方式。

模组操作先改本地清单，不会立即影响正在运行的正式服或 GitHub Pages。

### 从 Modrinth 添加

可以使用项目 slug：

```bash
./mcctl mod add sodium
```

也可以粘贴完整地址：

```bash
./mcctl mod add https://modrinth.com/mod/sodium
```

不带网站的名称默认从 Modrinth 查找。

### 从 CurseForge 添加

粘贴项目地址：

```bash
./mcctl mod add https://www.curseforge.com/minecraft/mc-mods/example-mod
```

如果作者关闭第三方下载，自动安装可能无法工作。不要未经许可把作者的 JAR 上传到 GitHub Pages，也不要把“网站上可以下载”当作“允许放进整合包再分发”。

### 添加作者提供的直接下载地址

只使用作者控制的 HTTPS 地址，优先使用官方 GitHub Release：

```bash
./mcctl mod add https://github.com/author/project/releases/download/v1.0/example.jar
```

直接地址通常不能自动发现新版本。发布前必须核对来源、哈希和许可证。

### 非 Modrinth 文件的再分发确认

Modrinth 文件可以由标准 `.mrpack` 写入源站下载地址。CurseForge 或作者直链的许可条件并不统一，因此发布脚本默认拒绝它们。确认作者明确允许整合包再分发后，在 `pack/redistribution.toml` 为对应元数据登记：

```toml
[files."mods/example.pw.toml"]
approved = true
metadata-sha256 = "该 .pw.toml 文件当前的 SHA-256"
license-url = "https://作者给出的许可页面"
```

取得哈希：

```bash
sha256sum pack/mods/example.pw.toml
```

每次文件版本或下载信息变化，元数据哈希都会变化，旧批准会自动失效，必须重新核对许可。`pack/redistribution.toml` 只供发布检查，不会放进玩家整合包。

### 检查更新

只查看可能的更新，不改变正式清单：

```bash
./mcctl mod update-check
```

输出是当前清单和临时更新结果的差异。

### 应用更新

更新一个模组：

```bash
./mcctl mod update 模组名称
```

更新全部模组：

```bash
./mcctl mod update all
```

如果更新结果包含 alpha、beta 或 snapshot 文件，校验器会拒绝候选版本，正式清单不会改变。

### 删除模组

先查看 `pack/mods/` 中对应的元数据文件名，然后执行：

```bash
./mcctl mod remove metadata-slug
```

被删除的元数据会移到 `runtime/removed-mods/时间戳/`，不会立即永久删除。

删除内容模组前必须先研究它对世界存档的影响。含方块、物品、实体或世界生成内容的模组不能当成普通性能模组随意删除。

### 修正安装位置

```bash
./mcctl mod side metadata-slug client
./mcctl mod side metadata-slug server
./mcctl mod side metadata-slug both
```

- `client`：仅玩家客户端。
- `server`：仅服务器。
- `both`：服务器和玩家都要安装。

修改后执行：

```bash
./mcctl mod check
```

## 测试并发布模组变更

不要添加完模组就直接让玩家更新。使用以下完整流程。

### 1. 建立候选变更

使用上一节的 `mod add`、`mod update`、`mod remove` 或 `mod side` 命令。

### 2. 启动隔离测试服

```bash
./mcctl stage start
./mcctl stage logs
```

测试服：

- 使用独立的 `runtime/staging/data`，不会直接写正式世界。
- 尽可能从最近一次正式备份恢复。
- 只监听 `127.0.0.1:25566`。
- 不应通过公网内网穿透开放。

检查日志没有缺少依赖、版本冲突或注册表错误，然后在本机连接 `127.0.0.1:25566` 测试：

- 能否进入世界。
- 原有方块、物品和机器是否正常。
- 新模组的核心功能是否能使用。
- 服务器停止并重新启动后是否仍然正常。

### 3. 接受测试结果

只有测试服处于健康状态时才能执行：

```bash
./mcctl stage accept
./mcctl stage stop
```

如果接受后又修改了模组清单，之前的接受记录自动失效，必须重新测试。

### 4. 选择发布时间

双方必装模组变化时，最好先关闭正式服，避免玩家已经更新而服务器仍运行旧版本：

```bash
./mcctl stop
```

### 5. 判断是小更新还是完整更新

发布命令必须明确选择一种类型：

| 类型 | 适用情况 | 已有玩家怎么做 |
|---|---|---|
| `small` | 少量、关系简单的模组添加、替换或删除 | 按更新页逐项手动处理，不重新导入 |
| `full` | Minecraft/Fabric 升级、大批模组变更、依赖关系复杂或管理员认为手动操作风险较高 | 下载并重新导入当前 `.mrpack` |

Minecraft 或 Fabric Loader 有变化时，工具会拒绝 `small`。模组数量的界线不写死，由管理员根据实际复杂度决定；拿不准时使用 `full`。

每次发布无论类型，Pages 都会生成一份包含当前完整清单的 `.mrpack`，供新玩家或需要重装的人使用。

### 6. 发布

少量变更：

```bash
./mcctl mod publish small
```

完整更新：

```bash
./mcctl mod publish full
```

命令会验证测试记录和再分发许可，自动生成下一个整合包版本、更新说明，验证标准 `.mrpack`，提交 `pack/` 与 `site/release.json`，然后推送到 GitHub。GitHub Actions 随后生成下载文件并更新 Pages。

发布必须从 `main` 分支执行。为防止漏提交服务器配置，命令发现 `pack/` 和 `site/release.json` 以外还有未提交文件时会停止；先单独检查并提交那些文件，再发布模组清单。

整合包版本使用 `Minecraft版本-r序号`，例如 `26.1.2-r1`、`26.1.2-r2`。同一 Minecraft 版本内每发布一次就增加序号；Minecraft 版本变化后从 `r1` 开始。

在下面的页面确认工作流成功：

<https://github.com/izumiChan16/wezza-mc/actions>

紧急情况下可以跳过测试记录：

```bash
./mcctl mod publish small --force
./mcctl mod publish full --force
```

除非你已经用其他方式完成等价测试，否则不要使用 `--force`。

### 7. 重启正式服并通知玩家

Pages 部署成功后：

```bash
./mcctl start
./mcctl logs
```

确认服务器健康并且 Pages 工作流完成后，把更新说明页发给玩家：

<https://izumichan16.github.io/wezza-mc/updates.html>

影响如下：

| 变更范围 | 服务器 | 玩家 |
|---|---|---|
| 仅服务端 | 下次开服安装 | 无需处理；更新页不会列为玩家操作 |
| 仅客户端 | 无需安装 | 小更新时手动处理，完整更新时重新导入 |
| 双方 | 下次开服安装 | 小更新时手动处理，完整更新时重新导入 |

## Git 和 GitHub 的日常使用

### 查看当前状态

```bash
git status
git log --oneline -5
```

### 修改文档、页面或部署脚本

例如修改 README 和 Pages 页面后：

```bash
git add README.md site/index.html
git diff --cached
git commit -m "docs: update usage guide and server page"
git push
```

推送 `site/`、`pack/` 或 Pages 工作流变更会自动重新部署网站。

### 模组变更

完成隔离测试后，根据变更规模选择：

```bash
./mcctl mod publish small
./mcctl mod publish full
```

该命令本身会提交并推送发布内容，不要随后再手动提交一半的 `pack/` 文件。`pack.toml`、`index.toml` 和 `.pw.toml` 的哈希必须保持一致。

### 查看 GitHub Actions

```bash
gh run list --limit 10
gh run watch <运行编号> --exit-status
gh run view <运行编号> --log-failed
```

仓库远端为：

```text
git@github.com:izumiChan16/wezza-mc.git
```

### 不会提交的私人内容

以下内容已经写入 `.gitignore`：

- `.env`
- RCON、restic 和 S3 密钥
- `runtime/` 中的世界与备份
- `dist/` 中的本地构建文件

提交前仍应使用 `git status` 检查一次。

## 备份和恢复

### 自动备份时机

- 每次开服前：服务器停止状态下保存一份快照。
- 服务器运行期间：每 2 小时保存一次。
- 每次执行 `./mcctl stop`：保存世界后立即备份。
- 启动隔离测试服前：先取得可恢复的正式服数据。

本机备份默认保留 14 天，并限制为最近 20 份。

### 手动备份

```bash
./mcctl backup
```

服务器运行时会通过 RCON 协调保存；服务器停止时会创建离线压缩包。

### 查看备份

```bash
./mcctl backup-list
```

记下输出中的完整文件名。

### 测试备份是否能解压

```bash
./mcctl restore-test 备份文件名
```

内容会解压到 `runtime/restore-test/时间戳/`，不会覆盖正式世界。确认其中存在 `level.dat`、`region/` 等世界文件。

### 正式恢复

1. 确认服务器已经停止：

```bash
./mcctl status
```

2. 恢复指定备份：

```bash
./mcctl restore 备份文件名 --confirm
```

原来的 `runtime/data` 会改名为 `runtime/data.pre-restore.时间戳`，不会直接删除。如果恢复失败，脚本会尝试把原数据放回。

3. 启动并检查日志：

```bash
./mcctl start
./mcctl logs
```

在确认恢复后的世界完全正常前，不要删除 `data.pre-restore.*`。

## 异地备份

异地备份是可选功能，使用 restic 加密并保存到 S3-compatible 存储。

### 配置

编辑 `.env`：

```text
ENABLE_REMOTE_BACKUP=true
RESTIC_REPOSITORY=s3:https://你的S3地址/存储桶/wezza-mc
RESTIC_HOSTNAME=wezza-home-pc
AWS_DEFAULT_REGION=区域
```

编辑 `secrets/aws_credentials`：

```ini
[default]
aws_access_key_id = 你的AccessKey
aws_secret_access_key = 你的SecretKey
```

`secrets/restic_password.txt` 是备份加密密码。丢失后无法恢复远端备份，必须额外保存在可靠的密码管理器中。

远端保留策略：

- 最近 14 个日备份。
- 最近 8 个周备份。
- 最近 12 个月备份。

正式启用前，先使用一个没有重要数据的测试存储桶验证备份和恢复流程。

## 升级 Minecraft 大版本

大版本升级不会自动完成。即使 Fabric 本身已有新版本，也必须等待每个重要模组明确兼容。

### 升级原则

- 永远保留可恢复的旧世界备份。
- 不在正式世界上直接试新版本。
- 不使用“忽略依赖”或强行修改兼容版本范围的方式启动。
- 含世界内容的模组缺失时，不升级正式世界。
- Minecraft 世界一旦被新版成功保存，通常不能安全降级。

### 推荐流程

1. 安全停服并创建备份：

```bash
./mcctl stop
./mcctl backup-list
```

2. 建立升级分支：

```bash
git switch -c upgrade/minecraft-新版本
```

3. 逐项确认 Fabric Loader、Fabric API、Refined Storage、Time in a Bottle 和所有性能模组都支持新版本。

4. 更新这些位置中的版本：

- `pack/pack.toml`
- `compose.yaml` 中的 Minecraft、Fabric Loader、Java 镜像和镜像摘要
- `tools/validate_pack.py` 中的版本校验
- `.env.example`、`site/index.html` 和本文档中的展示值

可以先搜索所有旧版本引用：

```bash
rg '26\.1\.2|0\.19\.3|java25' .
```

5. 更新模组并重新生成清单：

```bash
./mcctl mod update all
./mcctl mod check
```

6. 使用隔离测试服恢复正式世界副本，完整检查启动、进入世界、区块、物品和机器。

7. 至少再做一次停止和重新启动测试。

8. 所有检查通过后，先把测试结果保存为分支提交：

```bash
git add -A
git commit -m "test: validate Minecraft 新版本 upgrade"
```

9. 回到 `main`，把升级变更合并为尚未提交的工作区内容：

```bash
git switch main
git merge --squash upgrade/minecraft-新版本
git restore --staged .
```

10. 先提交除模组清单和发布记录之外的配套变更：

```bash
git add -A -- . ':(exclude)pack' ':(exclude)site/release.json'
git commit -m "chore: prepare Minecraft 新版本"
```

11. 保持 `pack/` 为待发布变更，以完整更新发布：

```bash
./mcctl mod publish full
```

正式服第一次升级启动前再次确认备份可用，并通知所有玩家重新导入新 `.mrpack`。

如果任何核心模组尚未支持新版本，就继续运行当前版本，不要为了升级 Minecraft 而删除核心内容。

## 换电脑或重新部署

GitHub 仓库可以恢复服务器程序和模组清单，但不能恢复私人世界。换电脑前必须另外复制最新世界备份、`.env` 和需要保留的密钥。

### 1. 在新电脑准备环境

- 安装 Docker Desktop。
- 安装并启用 Arch WSL。
- 在 Docker Desktop 中启用该 WSL 发行版的 integration。
- 配置 Git 和 GitHub CLI。

### 2. 克隆仓库

在 WSL 的 Linux 主目录中执行：

```bash
cd /home/你的用户名
git clone git@github.com:izumiChan16/wezza-mc.git wezza_mc
cd wezza_mc
```

不要把运行目录放到 `/mnt/c`。

### 3. 创建本机文件

```bash
./mcctl init
```

这会创建 `.env`、随机 RCON 密钥、restic 密码文件以及空的运行目录。然后：

- 编辑 `.env`，接受 EULA 并确认正式 Packwiz 地址。
- 如果要继续使用原异地备份，放回原来的 `restic_password.txt` 和 S3 凭据，不能使用新随机密码代替。
- 不要把旧 RCON 密钥或 S3 密钥提交到 GitHub。

### 4. 恢复世界

把备份压缩包复制到：

```text
runtime/backups/offline/
```

先执行：

```bash
./mcctl backup-list
./mcctl restore-test 备份文件名
./mcctl restore 备份文件名 --confirm
```

确认恢复后再启动服务器。内网穿透客户端仍需在新 Windows 电脑上单独安装和配置。

## 目录和文件说明

```text
wezza_mc/
├── .github/workflows/     GitHub 自动校验和 Pages 发布
├── pack/                  模组清单、版本与再分发批准
│   └── mods/              每个模组的 Packwiz 元数据
├── runtime/               世界、备份、测试服数据，不提交
├── secrets/               RCON 和备份密钥，不提交真实值
├── site/                  GitHub Pages 基本信息和更新数据
├── tools/                 清单、发布记录和 MRPACK 校验工具
├── .env                   本机设置，不提交
├── compose.yaml           Docker 服务定义
├── mcctl                  管理命令入口
└── README.md              本文档
```

重要数据：

- `runtime/data/`：正式服务器全部数据。
- `runtime/backups/local/`：运行期间的本机备份。
- `runtime/backups/offline/`：停服状态快照。
- `runtime/staging/`：隔离测试服，可以重建，但不要与正式数据混淆。

## 故障排查

### Docker Desktop 无法连接

现象：

```text
Docker Desktop is not reachable from this WSL distribution.
```

处理：

1. 确认 Docker Desktop 正在运行。
2. 打开 Docker Desktop 的 WSL integration。
3. 确认已勾选 Arch 发行版。
4. 在 WSL 中重新执行 `docker info`。

### 提示没有接受 EULA

阅读 EULA 后把 `.env` 中的 `EULA=FALSE` 改为 `EULA=TRUE`。

### 启动超过三分钟仍不健康

```bash
docker compose logs --tail 200 minecraft
```

重点查找：

- 某个模组不支持当前 Minecraft 或 Fabric。
- 缺少依赖。
- 模组只应安装在客户端，却进入了服务器。
- 世界数据或配置文件解析失败。

不要反复强制重启。先保留日志和最近备份。

### 玩家提示模组不一致

按顺序检查：

1. GitHub Pages 工作流是否成功。
2. 玩家使用的整合包版本是否与更新说明页一致。
3. 如果是小更新，玩家是否逐项完成了页面列出的添加、替换或删除操作。
4. 如果是完整更新，玩家是否重新导入了新 `.mrpack`，而不是继续启动旧版本。
5. 正式服是否在 Pages 发布后重新启动过。
6. 模组的安装位置是否正确标为 `client`、`server` 或 `both`。

### PCL2 导入后没有模组

先确认导入的是扩展名为 `.mrpack` 的当前文件，并且没有手动解压。正常情况下，PCL2 会在**导入过程**中下载客户端需要的模组；导入后的 `mods` 目录不应为空。

如果失败，删除这次创建的不完整版本，重新从服务器信息页下载并导入，再检查 PCL2 下载日志中是否有网络、源站或哈希错误。不要用手工复制服务端 `mods` 目录代替，因为其中含有客户端不应安装的服务端专用模组。

### Pages 没有更新

```bash
gh run list --limit 5
gh run view 运行编号 --log-failed
```

本地先执行：

```bash
./mcctl mod check
git status
```

Packwiz 校验失败时不要手动修改 `index.toml` 哈希，应让 `./mcctl mod check` 重新生成。

### 无法加入服务器

依次检查：

1. `./mcctl status` 是否显示正式服运行。
2. 玩家是否已经进入白名单。
3. 内网穿透客户端是否运行。
4. 穿透目标是否为 `127.0.0.1:25565 TCP`。
5. 玩家使用的是穿透服务提供的公网地址，而不是本机地址。

### 服务器卡顿

先查看在线人数和 spark 健康报告：

```bash
./mcctl rcon "list"
./mcctl rcon "spark healthreport"
```

不要一遇到卡顿就增加内存。先区分是区块生成、实体过多、机器逻辑、网络还是垃圾回收问题。

### Windows 即将关机但服务器还在运行

优先执行：

```bash
./mcctl stop
```

等待命令完成。不要直接结束 Docker Desktop 进程或强制关闭 Windows。

## 命令速查

### 服务器

| 命令 | 作用 |
|---|---|
| `./mcctl start` | 备份已有数据并启动正式服 |
| `./mcctl stop` | 保存、备份并关闭正式服 |
| `./mcctl stop --skip-remote` | 本机备份后关服，跳过本次异地备份 |
| `./mcctl restart` | 安全重启 |
| `./mcctl status` | 查看容器和本机端口 |
| `./mcctl logs` | 持续查看正式服日志 |
| `./mcctl console` | 连接服务器控制台 |
| `./mcctl rcon "命令"` | 执行 Minecraft 管理命令 |

### 玩家

| 命令 | 作用 |
|---|---|
| `./mcctl whitelist add 玩家名` | 加入白名单 |
| `./mcctl whitelist remove 玩家名` | 移出白名单 |
| `./mcctl whitelist list` | 查看白名单 |

### 模组

| 命令 | 作用 |
|---|---|
| `./mcctl mod add <slug或URL>` | 添加本地候选模组 |
| `./mcctl mod update-check` | 在临时副本中检查更新 |
| `./mcctl mod update <名称>` | 更新一个候选模组 |
| `./mcctl mod update all` | 更新全部候选模组 |
| `./mcctl mod remove <slug>` | 可恢复地删除元数据 |
| `./mcctl mod side <slug> <side>` | 修改安装位置 |
| `./mcctl mod check` | 刷新并验证清单 |
| `./mcctl mod publish small` | 发布小更新，已有玩家按页面手动处理 |
| `./mcctl mod publish full` | 发布完整更新，要求已有玩家重新导入 |

### 测试服

| 命令 | 作用 |
|---|---|
| `./mcctl stage start` | 从备份启动隔离测试服 |
| `./mcctl stage logs` | 查看测试服日志 |
| `./mcctl stage accept` | 接受当前测试过的清单 |
| `./mcctl stage stop` | 关闭测试服 |

### 备份

| 命令 | 作用 |
|---|---|
| `./mcctl backup` | 创建一次本机备份 |
| `./mcctl backup-list` | 列出备份 |
| `./mcctl restore-test <文件名>` | 安全解压检查备份 |
| `./mcctl restore <文件名> --confirm` | 停服状态下正式恢复 |

### 客户端构建

| 命令 | 作用 |
|---|---|
| `./mcctl client build` | 本地生成当前标准 `.mrpack` 到 `dist/` |

该本地构建也会执行再分发与内容校验。线上文件由 GitHub Pages 工作流在每次发布后重新生成；不要手动上传一个未经校验的 JAR 或整合包。
