# Wezza MC 管理员手册

本文是 Wezza MC 服务器管理员的操作手册，适用于当前仓库中的 Fabric 26.1.2、Docker Compose、Packwiz、标准 Modrinth `.mrpack` 和 GitHub Pages 发布流程。

文档基线：2026-08-30。整合包版本和模组数量以仓库中的 `pack/` 为准。

项目位置：

```text
/home/izumi/wezza_mc
```

公开地址：

- 服务器信息：<https://izumichan16.github.io/wezza-mc/>
- 玩家更新说明：<https://izumichan16.github.io/wezza-mc/updates.html>
- GitHub 仓库：<https://github.com/izumiChan16/wezza-mc>
- GitHub Actions：<https://github.com/izumiChan16/wezza-mc/actions>

除非特别说明，所有命令都在 Arch WSL 中从项目根目录执行：

```bash
cd /home/izumi/wezza_mc
```

## 快速导航

- [交互式管理面板](#交互式管理面板)
- [首次部署](#3-首次部署)
- [本机配置](#4-本机配置说明)
- [日常开服与关服](#5-日常开服与关服)
- [世界状态与重置](#世界状态与重置)
- [白名单和 OP](#6-玩家白名单和-op)
- [添加、更新、删除模组](#7-模组变更的完整生命周期)
- [隔离测试服](#8-隔离测试服)
- [选择小更新或完整更新](#9-选择小更新或完整更新)
- [非 Modrinth 许可](#10-非-modrinth-文件许可登记)
- [发布整合包](#11-发布流程)
- [发布后操作](#12-发布后操作)
- [Git 和 GitHub](#13-git-与-github-管理)
- [备份与正式恢复](#14-本机备份)
- [异地备份](#15-异地备份)
- [修改服务器规则](#16-修改服务器规则)
- [升级 Minecraft/Fabric/Java](#17-升级-minecraftfabric-或-java)
- [换电脑与灾难恢复](#18-换电脑与灾难恢复)
- [故障排查](#19-故障排查)
- [管理员检查清单](#20-管理员检查清单)
- [命令速查](#21-命令速查)

## 1. 管理员首先要记住的规则

1. **正式世界在 `runtime/data/`。** 不要手工清空、覆盖或与测试服目录混用。
2. **世界状态和重置使用 `./mcctl` 面板或 `./mcctl world`。** 重置会先备份并归档旧世界。
3. **通过 `./mcctl` 面板或对应命令安全开关服。** 不要用 Docker Desktop 的强制停止代替正常关服。
4. **任何模组变化先进入隔离测试服。** 在面板中选择“测试没有问题：完成并清理”后才能发布。
5. **`.mrpack` 是版本快照，不是自动同步器。** 小更新由已有玩家按更新页手动操作；完整更新要求重新导入。
6. **正式发布只从 `main` 分支执行。** `mod publish` 会生成版本号、更新记录、提交并推送。
7. **非 Modrinth 文件默认禁止发布。** 必须先核对作者许可并登记准确的元数据哈希。
8. **服务器只应暴露游戏端口。** 不要向公网转发 RCON、测试服端口、Docker API 或 WSL 的其他服务。
9. **Git 不能代替世界备份。** 仓库保存程序和模组清单，世界、`.env` 和密钥不在 Git 中。
10. **Minecraft 新版本保存过的世界通常不能安全降级。** 大版本升级前必须验证可恢复备份。
11. **这里所谓的“插件”应当是 Fabric 模组。** Bukkit、Spigot、Paper 插件不能直接装进这个服务器。

### 交互式管理面板

日常管理的首选入口是在项目根目录直接运行：

```bash
./mcctl
```

交互终端中无参数调用会打开中文状态总览。首页只保留五个任务入口：正式服启停、玩家管理、整合包维护、备份与恢复、更多工具。总览显示正式服、整合包维护阶段、本机备份总占用、可回收的测试服数据以及运行环境。

默认使用 `fzf` 菜单：方向键移动，输入文字搜索，`Enter` 选择，`Esc` 返回。短操作成功后直接留在当前层级并显示一条完成提示；需要阅读的状态、列表、日志和诊断才会暂停。正式服启停或测试会话状态变化后返回总览；失败时保留输出并留在当前任务中。若 `fzf` 缺失会自动降级为编号菜单；也可以显式运行：

```bash
./mcctl menu
./mcctl menu --plain
```

五个任务入口是：

- **启动/安全停止正式服**：首页根据当前状态直接切换，不再先进入服务器子菜单；启动不重复确认，安全停止需要确认。
- **管理玩家**：在线玩家、白名单、OP 和撤销 OP。
- **维护整合包**：根据候选变更和测试会话状态，只显示当前可做的修改、测试、验收、清理或发布动作。
- **备份与恢复**：世界状态与重置、创建和选择备份、测试恢复、正式恢复和删除。
- **更多工具**：详细状态、日志、控制台、RCON、重启、设置、诊断和高级帮助。

只有关服、权限撤销、批量或删除操作、发布以及会覆盖正式数据的高风险动作需要确认。交互菜单删除备份使用 `[y/N]`，大小写均可，直接按 Enter 默认为 N；测试通过时删除“本次测试专用备份”使用 `[Y/n]`，默认删除。世界重置和正式恢复仍要求完整确认短语；发布只需一次 `[y/N]`。菜单不提供绕过测试接受的强制发布。

首次配置仍以 `.env` 为唯一数据源。菜单可以执行 `init`、使用 `${VISUAL:-${EDITOR:-nano}}` 打开文件并在保存后校验，但不会替管理员接受 Minecraft EULA。运行以下只读诊断可检查依赖、配置、密钥权限、Docker、Compose 和发布元数据：

```bash
./mcctl doctor
```

现有非交互命令继续可用于脚本和精确排错，但不需要日常记忆。执行 `./mcctl help --all` 查看完整参考。

## 2. 系统由哪些部分组成

```text
管理员修改 pack/
       │
       ▼
隔离测试服 127.0.0.1:25566
       │ 测试通过、停止并清理测试副本
       ▼
./mcctl mod publish small|full
       │
       ├──生成整合包版本和玩家更新记录
       ├──构建并校验标准 .mrpack
       ├──提交并推送 main
       ▼
GitHub Pages
       ├──pack.toml：正式服务器下次启动时读取
       ├──.mrpack：新玩家或完整更新使用
       └──updates.html：已有玩家查看更新方式
```

### 2.1 Docker 服务

| 服务 | 用途 | 是否长期运行 | 主机端口 |
|---|---|---|---|
| `minecraft` | 正式 Fabric 服务器 | 只在游玩时运行 | `${MC_BIND_IP}:25565`，默认仅本机 |
| `backup-local` | 正式服运行期间每两小时本机备份 | 跟随正式服 | 无 |
| `packwiz` | 管理员执行清单命令的临时工具 | 命令结束即删除 | 无 |
| `pack-server` | 向隔离测试服提供当前本地 Packwiz 清单 | 测试期间 | 仅 Compose 内部 |
| `minecraft-staging` | 使用世界副本测试候选变更 | 测试期间 | `127.0.0.1:25566` |
| `backup-remote` | 执行一次 restic/S3 异地备份 | 仅按需临时运行 | 无 |

正式服和测试服可以同时运行，但默认各分配 5 GB Java 内存。还要计算 Windows、Docker Desktop、客户端和系统缓存占用；内存不足时不要同时启动两套服务器。

### 2.2 两种发布文件

| 文件 | 使用者 | 作用 |
|---|---|---|
| `pack.toml`、`index.toml`、`mods/*.pw.toml` | 正式服务器 | 服务器启动时由 Packwiz 安装服务端需要的模组 |
| `wezza-mc-<版本>.mrpack` | 玩家 | PCL2 导入时下载客户端需要的模组 |

两者来自同一份 `pack/` 清单，但用途不同。不要把服务器 `mods` 目录直接复制给玩家，因为里面含有仅服务端模组。

### 2.3 重要目录

| 路径 | 内容 | 是否提交 Git |
|---|---|---|
| `pack/` | Packwiz 清单、模组元数据、再分发批准 | 是 |
| `site/` | Pages 首页、更新页和当前发布记录 | 是 |
| `tools/` | 清单、MRPACK 和发布校验工具 | 是 |
| `runtime/data/` | 正式服务器数据和世界 | 否 |
| `runtime/backups/local/` | 运行期间生成的本机备份 | 否 |
| `runtime/backups/offline/` | 停服状态快照 | 否 |
| `runtime/world-archive/` | 世界重置前归档的旧世界 | 否 |
| `runtime/staging/` | 隔离测试世界、会话状态和接受记录 | 否 |
| `runtime/removed-mods/` | 被移除模组元数据的临时保留位置 | 否 |
| `secrets/` | RCON、restic 和 S3 密钥 | 真实值不提交 |
| `dist/` | 本地生成的 `.mrpack` | 否 |
| `.env` | 本机端口、内存、EULA 和备份配置 | 否 |

### 2.4 当前发布基线

| 项目 | 当前值 |
|---|---|
| Minecraft | 26.1.2 |
| Fabric Loader | 0.19.3 |
| Java | 25 |
| 整合包版本 | 执行命令查询 |
| 模组版本和安装侧 | 执行 `./mcctl mod list` 查询 |

版本发布后不再手工维护模组总表。实际权威数据始终是 `pack/pack.toml` 和 `pack/mods/`，可以执行：

```bash
python3 tools/release_pack.py version --pack-dir pack
./mcctl mod list
```

## 3. 首次部署

### 3.1 准备软件

Windows 端需要：

- Docker Desktop。
- 已启用的 Arch WSL。
- Docker Desktop 对 Arch WSL 的 integration。
- 现有的 TCP 内网穿透客户端。
- 玩家测试时使用的 PCL2 和 Java 25。

WSL 中需要：

- Git。
- GitHub CLI `gh`。
- Python 3。
- OpenSSL、tar、zstd 等常用命令。

先确认 Docker 可用：

```bash
docker info
docker compose version
```

项目应放在 WSL 的 Linux 文件系统中，不要移动到 `/mnt/c`。Minecraft 世界包含大量小文件，放在 Windows 挂载盘会明显影响性能和文件语义。

### 3.2 初始化本机文件

首次克隆仓库后执行：

```bash
./mcctl init
```

该命令会：

- 从 `.env.example` 创建 `.env`，已有 `.env` 不会被覆盖。
- 创建正式服、备份、测试服和构建目录。
- 生成随机 RCON 密码。
- 生成随机 restic 密码。
- 从示例创建 S3 凭据文件。
- 把三个密钥文件权限设置为 `600`。

检查：

```bash
ls -l .env secrets/rcon_password.txt secrets/restic_password.txt secrets/aws_credentials
chmod 600 .env
```

不要把这些真实文件添加到 Git。

### 3.3 接受 EULA

管理员本人阅读 [Minecraft EULA](https://aka.ms/MinecraftEULA) 后，才可以编辑 `.env`：

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

脚本不会替管理员自动接受 EULA。

### 3.4 配置正式清单地址

当前仓库应使用：

```text
PACKWIZ_URL=https://izumichan16.github.io/wezza-mc/pack.toml
```

它必须是 HTTPS 地址，并且结尾是 `/pack.toml`。这是正式服务器读取的 Packwiz 清单，不是玩家下载 `.mrpack` 的地址。

启动前可检查：

```bash
curl -f https://izumichan16.github.io/wezza-mc/pack.toml
```

### 3.5 验证本机配置

```bash
docker compose config --quiet
./mcctl mod check
git status
```

`mod check` 会启动一次临时 Packwiz 工具容器、刷新 `index.toml` 并执行本地规则校验。第一次运行可能需要构建 Packwiz 镜像。

如果 `git status` 显示 Packwiz 刚刚修改了清单，先理解差异，不要直接开服或提交：

```bash
git diff -- pack
```

### 3.6 第一次启动

```bash
./mcctl start
```

第一次启动会下载服务器、Fabric 和模组。脚本最多等待三分钟健康检查；另开终端查看：

```bash
./mcctl logs
```

首次成功后执行：

```bash
./mcctl status
./mcctl rcon "list"
```

最后添加管理员自己的白名单：

```bash
./mcctl whitelist add 你的Java版玩家名
```

## 4. 本机配置说明

### 4.1 `.env`

| 变量 | 当前默认值 | 作用 | 何时生效 |
|---|---:|---|---|
| `EULA` | `FALSE` | 是否由本人接受 EULA | 下次启动 |
| `PACKWIZ_URL` | Pages 地址 | 正式服清单地址 | 下次创建/启动服务端 |
| `MC_BIND_IP` | `127.0.0.1` | 正式服主机绑定地址；`0.0.0.0` 允许局域网访问 | 重新创建容器后 |
| `MC_PORT` | `25565` | 正式服本机端口 | 重新创建容器后 |
| `STAGING_PORT` | `25566` | 测试服本机端口 | 重新创建测试容器后 |
| `WORLD_NAME` | `world` | 正式世界目录名（单层安全目录名） | 下次启动 |
| `WORLD_SEED` | 空 | 新世界生成的有符号 64 位整数；空值为随机 | 下次创建世界 |
| `MEMORY` | `5G` | 正式服 Java 最大内存 | 下次启动 |
| `STAGING_MEMORY` | `5G` | 测试服 Java 最大内存 | 下次测试启动 |
| `TZ` | `Asia/Taipei` | 日志和备份时区 | 下次启动 |
| `MOTD` | `Wezza Fabric 26.1.2` | 多人游戏列表名称 | 下次启动 |
| `MAX_PLAYERS` | `10` | 最大在线人数 | 下次启动 |
| `PUID` / `PGID` | `1000` | Packwiz 工具写文件时使用的 WSL 用户 | 下次工具运行 |
| `ENABLE_REMOTE_BACKUP` | `false` | 关服时是否执行异地备份 | 下次关服 |
| `RESTIC_REPOSITORY` | 示例值 | S3-compatible restic 仓库 | 异地备份时 |
| `RESTIC_HOSTNAME` | `wezza-home-pc` | restic 快照来源标识 | 异地备份时 |
| `AWS_DEFAULT_REGION` | `auto` | S3 区域 | 异地备份时 |

修改 `.env` 后先执行：

```bash
docker compose config --quiet
```

如果修改了 `WORLD_NAME` 或 `WORLD_SEED`，用 `./mcctl world status` 检查配置。种子只影响下次创建的世界，不会改变已经存在的世界。

端口变化时必须同步修改 Windows 内网穿透目标。

### 4.2 `compose.yaml`

以下规则由 Compose 固定管理：

- Minecraft 26.1.2。
- Fabric Loader 0.19.3。
- Java 25 镜像。
- 困难生存、正版验证、白名单和安全档案验证。
- PVP 开启、命令方块关闭。
- 视距 10、模拟距离 8。
- RCON 仅供容器内部管理，不映射到主机。

修改这些设置时编辑 `compose.yaml`。不要只修改 `runtime/data/server.properties` 中受环境变量管理的项目，因为容器重新创建时可能覆盖它们。

### 4.3 端口与内网穿透

默认情况下，正式服只绑定到本机。需要让局域网设备直接连接时，在 `.env` 中设置：

```text
MC_BIND_IP=0.0.0.0
```

重新创建正式服容器后，玩家使用宿主机的局域网 IP（例如 `192.168.x.x:25565`）连接，不要使用 `0.0.0.0`。同时确认 Windows 防火墙只在可信任的专用网络上允许该 TCP 端口。测试服仍固定绑定 `127.0.0.1:25566`。

Windows 内网穿透只转发：

```text
127.0.0.1:25565 TCP
```

不要转发：

- `127.0.0.1:25566`：隔离测试服。
- RCON：没有必要公开。
- Docker daemon/API。
- WSL SSH 或其他不相关端口。

玩家使用的是穿透服务给出的公网地址，不是 `127.0.0.1`。

## 5. 日常开服与关服

### 5.1 标准开服清单

1. 启动 Docker Desktop。
2. 启动 Windows 内网穿透客户端。
3. 打开 Arch WSL。
4. 确认没有未处理的维护工作。
5. 启动服务器：

```bash
cd /home/izumi/wezza_mc
./mcctl start
```

6. 确认状态和玩家列表：

```bash
./mcctl status
./mcctl rcon "list"
```

7. 通知玩家服务器已开放。

`start` 会在正式数据非空时先创建停服状态快照，然后启动正式服和两小时备份调度器。服务器已运行时再次执行会直接拒绝，不会启动第二份。

### 5.2 运行期间

查看实时日志：

```bash
./mcctl logs
```

按 `Ctrl+C` 只停止日志跟随，不会停止服务器。

检查状态：

```bash
./mcctl status
```

常用管理命令：

```bash
./mcctl rcon "list"
./mcctl rcon "say 十分钟后维护，请先回到安全位置"
./mcctl rcon "save-all flush"
```

`rcon` 参数中不要写游戏内的 `/` 前缀。

进入容器控制台：

```bash
./mcctl console
```

命令会先显示连接成功和操作说明。控制台没有命令提示符，直接输入 Minecraft 命令并按 Enter，命令不要带 `/`。分离控制台依次按 `Ctrl+P`、`Ctrl+Q`；不要按 `Ctrl+C` 结束 Java 进程。退出后脚本会再次报告服务器是否仍在运行。

### 5.3 标准关服清单

先通知玩家，再执行：

```bash
./mcctl stop
```

脚本会：

1. 在游戏内广播 10 秒提示。
2. 通过备份容器和 RCON 协调保存。
3. 创建本机备份。
4. 如果启用了远端备份，再执行加密异地备份。
5. 优雅停止备份调度器和 Minecraft，最长等待 120 秒。

只有命令完成后，才关闭穿透客户端、Docker Desktop、Windows，或让电脑睡眠。

如果远端备份失败，脚本会让正式服继续运行，避免在备份状态不明时直接关机。确认本机备份存在后，可明确跳过本次远端备份：

```bash
./mcctl backup-list
./mcctl stop --skip-remote
```

`--skip-remote` 不会跳过本机备份。

### 5.4 安全重启

```bash
./mcctl restart
```

它等价于完整安全关服后再启动，因此可能先创建关服备份，再在启动前创建停服状态快照。维护窗口要为备份和启动下载预留时间。

## 世界状态与重置

### 查看状态

```bash
./mcctl world status
```

输出包括正式服务和 staging 状态、`WORLD_NAME` 对应的世界路径、世界目录是否存在、大小、最近修改时间、下次生成种子配置以及旧世界归档数量。已有世界的真实种子不会从 `level.dat` 中猜测；`Next generation seed` 只表示下次创建世界时 Compose 会使用的配置。

### 安全重置

重置是破坏性操作，但脚本会保留可恢复副本。开始前确认没有玩家在线，并执行：

```bash
./mcctl world reset --seed 123456789 --confirm
```

或者明确要求随机种子：

```bash
./mcctl world reset --random --confirm
```

要求和流程如下：

1. 必须提供且只能提供一种种子模式；固定种子只能是有符号 64 位整数。
2. 必须带 `--confirm`；正式 Minecraft、备份和 staging 服务必须全部停止。
3. 脚本先创建完整停服快照，失败时不会移动世界。
4. 现有世界移动到 `runtime/world-archive/<时间>-<世界名>/`，不会直接删除。
5. 原子更新 `.env` 的 `WORLD_SEED`，不自动启动服务器。

如果当前还没有世界，命令只会写入种子配置，下一次 `./mcctl start` 才会生成世界。重置后先再次执行 `./mcctl world status`，然后再启动并检查世界。确认新世界正常前不要删除归档；需要正式恢复时使用现有的 `restore-test` 和 `restore` 备份流程。

## 6. 玩家、白名单和 OP

白名单：

```bash
./mcctl whitelist add 玩家Java版名称
./mcctl whitelist remove 玩家Java版名称
./mcctl whitelist list
```

名称必须是正版 Java 版名称。正版验证和强制白名单均已开启。

授予或撤销 OP：

```bash
./mcctl rcon "op 玩家名"
./mcctl rcon "deop 玩家名"
```

只给可信任的管理员 OP。普通玩家不需要为了使用模组获得 OP。

## 7. 模组变更的完整生命周期

任何模组变更都按以下顺序进行：

```text
检查兼容性
  → 建立本地候选变更
  → 修正 client/server/both
  → 完成非 Modrinth 许可登记
  → mod check
  → stage start
  → 服务端与客户端实测
  → 完成测试并清理测试副本
  → 选择 small 或 full
  → 发布并等待 Pages
  → 更新正式服与通知玩家
```

跳过某一步不会让风险消失，只会把风险推迟到正式世界或玩家端。

开始修改前先确保从最新 `main` 出发，并且工作区没有不认识的变化：

```bash
git switch main
git status --short
git pull --ff-only
```

如果 `git status` 非空，先处理现有工作，不要为了拉取远端而丢弃本地文件。

### 7.1 修改前调查

至少确认：

- 文件明确支持当前 Minecraft 版本。
- 文件是 Fabric 版本，不是 Forge/NeoForge 文件。
- 所有前置依赖都能用于同一 Minecraft/Fabric 版本。
- 模组安装侧是 `client`、`server` 还是 `both`。
- 是否包含方块、物品、实体、维度、附魔或世界生成内容。
- 从存档中删除它会不会造成方块消失、区块损坏或数据丢失。
- 来源和再分发许可是否允许进入标准整合包。
- 新版本是稳定版，不是 alpha、beta 或 snapshot。

优先选择 Modrinth 来源。CurseForge 或作者直链不是不能使用，但需要额外处理许可和下载兼容性。

### 7.2 查看 metadata slug

先列出当前清单：

```bash
./mcctl mod list
```

表格列出 `SLUG`、`SIDE`、`SOURCE` 和显示名称。`SLUG` 就是 `pack/mods/<slug>.pw.toml` 的文件名，可直接用于后面的 `mod update`、`mod side` 和 `mod remove` 命令；不带参数执行 `./mcctl mod` 也会显示这张表。该命令只做本地读取和校验，不刷新或修改清单。

### 7.3 添加 Modrinth 模组

使用 slug：

```bash
./mcctl mod add sodium
```

或完整项目地址：

```bash
./mcctl mod add https://modrinth.com/mod/sodium
```

命令在临时副本中调用 Packwiz；验证成功才会把候选清单复制回 `pack/`。此时只是本地候选，尚未部署到正式服务器或 Pages。

### 7.4 添加 CurseForge 模组

```bash
./mcctl mod add https://www.curseforge.com/minecraft/mc-mods/example-mod
```

可能遇到：

- 作者关闭第三方下载。
- 文件页面存在，但 Packwiz API 无法取得可下载文件。
- 作者许可不允许整合包再分发。
- Modrinth `.mrpack` 导出无法可靠携带该来源。

自动添加成功不代表允许发布。继续之前必须完成[非 Modrinth 文件许可登记](#10-非-modrinth-文件许可登记)。

### 7.5 添加作者 HTTPS 直链

只使用作者控制的永久 HTTPS 地址，优先官方 GitHub Release：

```bash
./mcctl mod add https://github.com/author/project/releases/download/v1.0/example.jar
```

直链通常不能由 Packwiz 自动发现更新。不要使用临时签名 URL、网盘跳转页、需要 Cookie 的链接或来源不明的镜像。

### 7.6 设置安装侧

```bash
./mcctl mod side metadata-slug client
./mcctl mod side metadata-slug server
./mcctl mod side metadata-slug both
```

含义：

| side | 正式服务器 | 玩家客户端 | 例子 |
|---|---|---|---|
| `client` | 不安装 | 安装 | Sodium |
| `server` | 安装 | 不安装 | ServerCore、spark |
| `both` | 安装 | 安装 | Fabric API、Refined Storage |

不要仅凭“性能模组”三个字判断安装侧，应阅读该模组当前版本说明。安装侧变化也属于玩家更新：例如从 `client` 改成 `server` 时，更新页会要求已有玩家删除旧 JAR。

### 7.7 检查更新

只查看，不修改真实清单：

```bash
./mcctl mod update-check
```

脚本复制 `pack/` 到临时目录，对副本执行全部更新并输出差异。临时目录随后删除。

查看输出时重点确认：

- 文件版本是否仍对应 Minecraft 26.1.2。
- 是否跨了重大模组版本。
- 是否出现依赖新增、文件名变化或安装侧变化。
- 是否出现 alpha、beta、snapshot。

### 7.8 应用更新

更新一个：

```bash
./mcctl mod update metadata-slug
```

更新全部：

```bash
./mcctl mod update all
```

更新在临时副本中完成。Packwiz 和本地校验都成功后才会覆盖候选清单。校验器默认拒绝文件名中标记为 alpha、beta 或 snapshot 的构件。

不要因为 `update all` 成功就直接发布；一次改变太多模组会增加定位问题和玩家手工更新的难度。

### 7.9 删除模组

先列出元数据：

```bash
ls pack/mods
```

删除：

```bash
./mcctl mod remove metadata-slug
```

元数据会移动到：

```text
runtime/removed-mods/<时间戳>/
```

随后刷新并校验清单。校验失败时脚本会尝试放回元数据。

恢复尚未清理的元数据：

```bash
mv runtime/removed-mods/<时间戳>/example.pw.toml pack/mods/
./mcctl mod check
```

删除内容模组前必须先在世界副本中检查。即使服务器能启动，原有方块被空气替换或物品丢失也可能是不可接受的损坏。

### 7.10 刷新并验证候选清单

```bash
./mcctl mod check
```

该命令会：

- 重新生成 `index.toml` 中的文件哈希。
- 校验 Minecraft 和 Fabric Loader 固定版本。
- 校验每个 `.pw.toml` 的名称、文件名、安装侧、下载哈希和来源。
- 检查重复目标文件名。
- 检查索引遗漏和陈旧哈希。
- 拒绝默认不允许的预发布构件。

查看变更：

```bash
git status --short
git diff -- pack
```

不要手工猜测或复制 `index.toml` 哈希。

## 8. 隔离测试服

### 8.1 日常入口与会话模型

日常操作进入 `./mcctl` 的“维护整合包”。面板会记住一次测试会话，不要求管理员组合多个命令：

1. “开始测试候选整合包”刷新并校验清单。
2. 正式服有数据时只在本次会话开始前创建一次备份；正式服运行时使用在线备份，停止时使用停服快照。
3. 备份身份、清单哈希和开始时间记录在 `runtime/staging/SESSION`。
4. 备份恢复到隔离的 `runtime/staging/data/`，然后启动测试服。

同一会话内暂停、继续或因模组变化重建测试服都不会再次备份正式服。面板发现测试期间 `pack/` 变化或上次启动未完成后会显示“重新建立并启动测试服”；重建前先校验新清单和原备份，再从最初的备份恢复干净副本。

测试服务每次启动都会重新创建 staging 容器，以更新 Docker Desktop 为 WSL bind mount 建立的内部路径。Packwiz 清单已经在启动前刷新，`pack-server` 启动时不会再做第二次 refresh，避免失败途中改变会话哈希。

高级命令对应为：

```bash
./mcctl stage start
./mcctl stage stop
./mcctl stage resume
./mcctl stage rebuild
```

`stage start` 只允许建立全新会话。已有会话必须继续、完成或结束；存在旧版遗留测试数据时也会拒绝，防止无意间继续堆积世界副本。

如果容器启动失败，已经创建的会话、测试世界和专用备份都会保留，错误输出写入 `runtime/staging/LAST_ERROR.log`。维护页会持续显示“测试服启动失败”，并提供“查看上次失败详情”和“修复后重试启动测试服”；重试沿用原备份。高级命令为：

```bash
./mcctl stage error
./mcctl stage rebuild
```

### 8.2 连接与日志

查看日志：

```bash
./mcctl stage logs
```

本机客户端连接：

```text
127.0.0.1:25566
```

测试服不应加入公网穿透。

### 8.3 服务端测试项目

至少检查：

- 日志没有缺少依赖、Mixin 错误或注册表错误。
- 测试服健康并可以进入世界。
- 原有区块、方块、物品、机器和玩家数据正常。
- 新增或更新模组的主要功能正常。
- 管理命令和白名单仍正常。
- 保存、停止、再次启动后仍能进入世界。
- 删除模组时不存在不可接受的数据损失。
- spark 或日志没有出现明显性能退化。

要验证**同一个测试世界**的保存与重启，保持 `pack-server` 运行，只重启测试 Minecraft 容器：

```bash
docker compose --profile staging restart minecraft-staging
./mcctl stage logs
```

暂停后选择面板中的“继续这次测试”，或执行 `./mcctl stage resume`。不要再次执行 `stage start`；它只负责建立新会话，并会拒绝覆盖现有会话。

### 8.4 客户端测试项目

隔离测试服健康只证明服务器一侧能够运行。凡是 `client` 或 `both` 变化，还必须测试客户端。

构建当前候选 `.mrpack`：

```bash
./mcctl client build
```

输出：

```text
dist/wezza-mc-<当前版本>.mrpack
dist/wezza-mc-latest.mrpack
```

在 PCL2 中导入为临时测试版本，确认：

- 导入阶段确实下载模组。
- 仅服务端模组没有装进客户端。
- Java 25 和内存设置正确。
- 客户端可以启动并连接 `127.0.0.1:25566`。
- 新增界面、按键和资源正常。
- 没有客户端崩溃、缺失依赖或模组重复。

候选发布尚未执行版本递增，所以临时 `.mrpack` 的版本 ID 仍可能是当前线上版本。测试时创建独立 PCL2 版本，不要覆盖日常使用实例。

### 8.5 测试通过：一次完成验收和清理

确认服务端和必要的客户端测试都通过后，在面板选择“测试没有问题：完成并清理”。它会依次完成以下流程：

1. 确认测试服健康，而且测试会话记录的清单哈希仍等于当前 `pack/`。
2. 写入接受记录。
3. 停止测试服和本地清单服务。
4. 删除 `runtime/staging/data/` 及旧的 `data.previous.*` 测试世界副本。
5. 询问是否删除本次测试专用备份；提示为 `[Y/n]`，默认删除。
6. 清除会话记录，立即询问发布小更新、完整更新或稍后发布。

自动删除只针对本次会话创建且文件身份仍完全一致的那一个备份。若在线备份工具生成了多个文件、备份后来发生变化，或无法唯一证明归属，mcctl 会保留备份并给出警告，不会猜测删除。

等价的高级命令是：

```bash
./mcctl stage finish --delete-backup --confirm
# 或保留本次测试备份
./mcctl stage finish --keep-backup --confirm
```

### 8.6 测试失败与旧数据清理

测试发现问题时选择“测试有问题：结束本次测试”。mcctl 会停止测试服、删除隔离测试副本并清除会话，但保留候选 `pack/` 变更和测试前备份，便于继续修改和排查：

```bash
./mcctl stage discard --confirm
```

总览会统计 `runtime/staging/data/` 与 `data.previous.*` 的总占用。没有活动会话但存在旧版本遗留数据时，维护页会显示明确的“清理旧测试数据”任务和可释放容量。确认后只删除这些测试世界副本，不触碰 `runtime/data/`、本机备份或接受记录：

```bash
./mcctl stage cleanup --confirm
```

`stage accept` 保留为高级排错命令，只写入接受哈希，不停止服务、不清理数据，也不结束会话。日常流程应使用面板中的完成动作或 `stage finish`。

## 9. 选择小更新或完整更新

### 9.1 小更新 `small`

适合：

- 一两个模组的小版本替换。
- 少量且关系简单的新增或删除。
- 玩家可以明确按照“删除旧文件、安装新文件”操作。
- 不改变 Minecraft 或 Fabric Loader。

已有玩家不重新导入整合包，而是在 PCL2 的当前版本中按更新页手动处理。新玩家始终导入最新完整 `.mrpack`。

### 9.2 完整更新 `full`

适合：

- Minecraft 版本变化。
- Fabric Loader 版本变化。
- 大批模组同时更新。
- 依赖关系复杂。
- 多个文件增删，手工操作容易遗漏。
- 客户端配置结构发生变化。
- 管理员不愿承担手工更新误差。

已有玩家必须下载新的 `.mrpack` 并导入为新版本。Minecraft 或 Fabric Loader 发生变化时，工具会直接拒绝 `small`。

### 9.3 判断原则

工具不会用固定数量替管理员决定“多少算大批”。如果你需要写很长的解释才能确保玩家操作正确，就选择 `full`。

无论发布类型，每次 Pages 都会生成当前完整 `.mrpack`。`small` 与 `full` 的区别是已有玩家的迁移方式，不是是否生成整合包。

常见判断：

| 变更 | 建议类型 | 玩家处理 | 服务器处理 |
|---|---|---|---|
| 一个仅服务端性能模组更新 | `small` | 无需处理 | Pages 成功后重启 |
| 一个双方模组的小版本更新 | `small` | 按更新页替换一个 JAR | Pages 成功后重启 |
| 一个客户端模组更新 | `small` | 按更新页替换一个 JAR | 通常无需安装该模组 |
| 同时新增多个模组和前置依赖 | `full` | 重新导入 | Pages 成功后重启 |
| Minecraft 或 Fabric Loader 升级 | `full`，工具强制 | 重新导入 | 使用备份副本测试后升级 |
| 客户端配置结构或大量文件变化 | `full` | 重新导入 | 按变更需要重启 |

`full` 是管理员可以主动选择的更安全迁移方式，即使只改变一个模组也可以使用。

## 10. 非 Modrinth 文件许可登记

当前策略是：所有非 Modrinth 元数据默认阻止 MRPACK 发布。

### 10.1 核对内容

确认：

- 下载链接由作者或可信官方项目控制。
- 许可明确允许用于整合包、再分发或当前采用的下载方式。
- 链接不是会过期的临时地址。
- 文件哈希与元数据一致。
- 玩家无需登录、Cookie 或网页交互即可下载。

### 10.2 登记批准

先完成模组添加/更新和 `mod check`，然后取得元数据哈希：

```bash
sha256sum pack/mods/example.pw.toml
```

编辑：

```bash
nano pack/redistribution.toml
```

加入：

```toml
[files."mods/example.pw.toml"]
approved = true
metadata-sha256 = "上一步得到的完整 SHA-256"
license-url = "https://作者的许可或再分发说明页面"
```

验证：

```bash
python3 tools/release_pack.py safety --pack-dir pack
```

### 10.3 为什么批准会过期

批准绑定 `.pw.toml` 的完整 SHA-256。版本、下载 URL、文件哈希、安装侧或其他元数据变化后，旧批准就会失效。管理员必须重新阅读许可并更新批准，不能把一次批准永久套用到所有未来文件。

`redistribution.toml` 被 Packwiz 忽略，不会进入玩家整合包，但会被 Git 提交并由 CI/Pages 校验。

如果无法取得明确许可或可靠直链，不要发布该模组。

## 11. 发布流程

### 11.1 发布前检查

确认：

- 隔离测试服已完成服务端测试。
- 涉及客户端时已用本地 `.mrpack` 测试 PCL2。
- 已在面板中完成测试并清理，完成后没有再改 `pack/`。
- 非 Modrinth 批准已完成。
- 当前分支是 `main`。
- `pack/` 以外的代码和文档变更已经单独提交。
- Git 远端 `origin` 正确。
- 重要世界有最近备份。

检查：

```bash
git branch --show-current
git status --short
git remote -v
./mcctl backup-list
```

如果客户端双方必装模组发生变化，建议先进入维护窗口并安全停服，防止服务器与玩家在不同版本上同时尝试连接：

```bash
./mcctl stop
```

### 11.2 发布小更新

```bash
./mcctl mod publish small
```

### 11.3 发布完整更新

```bash
./mcctl mod publish full
```

### 11.4 发布命令具体做什么

`mod publish` 会依次：

1. 刷新并校验真实 `pack/`。
2. 对比隔离测试接受的清单哈希。
3. 检查当前位于 `main`，并且存在 `origin`。
4. 拒绝 `pack/` 与 `site/release.json` 之外的未提交文件。
5. 对比 `HEAD`，确认确有 Minecraft、Fabric 或模组变化。
6. 自动计算新版本号。
7. 生成包含准确文件增删替换信息的 `site/release.json`。
8. 强制 Minecraft/Fabric 变化使用 `full`。
9. 再次校验 Packwiz 清单和非 Modrinth 许可。
10. 构建临时标准 `.mrpack` 并检查依赖、文件、URL、哈希和客户端安装侧。
11. 把新版本和发布记录写回真实目录。
12. 只提交 `pack/` 和 `site/release.json`。
13. 推送当前 `main` 到 `origin`。

它**不会**自动停止或启动正式服务器，也不会替玩家修改 PCL2 实例。

### 11.5 版本号

格式：

```text
Minecraft版本-r发布序号
```

示例：

```text
26.1.2-r1
26.1.2-r2
26.1.2-r3
26.2-r1
```

同一 Minecraft 版本每发布一次，序号加一。Minecraft 版本改变后从 `r1` 开始。`full` 但 Minecraft 未改变时仍然继续增加原序号。

### 11.6 `--force`

紧急情况下：

```bash
./mcctl mod publish small --force
./mcctl mod publish full --force
```

`--force` 只跳过“必须存在与当前清单匹配的测试接受记录”这一项，不会跳过：

- Packwiz 校验。
- 固定版本校验。
- 非 Modrinth 许可门禁。
- MRPACK 构建和内容验证。
- `main` 分支要求。
- Git 工作区要求。

除非已经通过其他隔离环境完成等价测试，否则不要使用。

### 11.7 推送失败时

如果本地 Git 提交已经成功，但 `git push` 因网络或认证失败：

```bash
git status
git log -1 --oneline
git push origin main
```

不要再次运行 `mod publish`，否则它会发现没有新的候选变更，或者在错误操作后产生不必要版本。

### 11.8 Pages 失败时

查看：

```bash
gh run list --workflow pages.yml --limit 5
gh run view <运行编号> --log-failed
```

不要为了重试 Pages 再发布一个新整合包版本。先修复工作流或数据问题，提交修复，或在 GitHub Actions 中重跑原工作流。

## 12. 发布后操作

### 12.1 等待 Pages

```bash
gh run list --workflow pages.yml --branch main --limit 5
gh run watch <运行编号> --exit-status
```

确认以下地址：

- <https://izumichan16.github.io/wezza-mc/>
- <https://izumichan16.github.io/wezza-mc/updates.html>
- <https://izumichan16.github.io/wezza-mc/downloads/wezza-mc-latest.mrpack>

如有缓存疑问，可在 URL 后加查询参数，例如 `?rev=<提交SHA>`。

### 12.2 更新正式服务器

Pages 成功后启动：

```bash
./mcctl start
./mcctl logs
```

正式服启动时通过 `PACKWIZ_URL` 读取新清单。确认健康、模组加载版本和世界数据后再开放穿透或通知玩家。

### 12.3 通知玩家

小更新至少发送：

- 当前整合包版本。
- 更新说明页链接。
- 必须完成更新的时间。
- 服务器重新开放时间。

玩家按更新页中的准确文件名添加、替换或删除，不需要重新导入。仅服务端变化不会列为玩家操作。

完整更新至少发送：

- 明确说明“必须重新导入”。
- `.mrpack` 下载或服务器信息页链接。
- Java 25 和建议 6 GB 内存。
- 要求先保留旧实例，确认新实例可用后再删除。

## 13. Git 与 GitHub 管理

### 13.1 日常检查

```bash
git status
git diff
git log --oneline -5
git remote -v
```

在工作区干净且准备开始新一轮维护时同步远端：

```bash
git switch main
git pull --ff-only
```

`mod publish` 不会自动执行 `pull`。如果远端 `main` 已领先，本地发布提交可能在推送阶段被拒绝，因此应在建立候选变更之前同步。

### 13.2 普通代码或文档变更

`mod publish` 只负责整合包发布。脚本、Compose、管理员手册或页面样式应单独提交：

```bash
git add docs/ADMIN_GUIDE.md
git diff --cached
git commit -m "docs: expand administrator guide"
git push origin main
```

提交前确认没有 `.env`、世界、备份或真实密钥。

### 13.3 哪些推送会触发 Pages

Pages 工作流监听：

- `pack/**`
- `site/**`
- `tools/release_pack.py`
- `tools/validate_pack.py`
- `.github/workflows/pages.yml`

只修改本管理员手册不会重新部署 Pages。

### 13.4 工作流职责

Pages 工作流会：

- 刷新并校验 Packwiz，要求仓库索引没有漂移。
- 校验发布记录与 `pack.toml` 版本一致。
- 检查非 Modrinth 许可。
- 生成 `mods.json`。
- 导出版本化和 `latest` 两份标准 `.mrpack`。
- 验证 MRPACK 内容和安装侧。
- 部署公开页面。

CI 工作流在 Pull Request、非 `main` 分支推送和手动触发时运行，负责相同的核心清单、脚本、Compose 与 MRPACK 验证。

### 13.5 仓库公开性的影响

公开仓库中的以下内容任何人都能看到：

- 模组名称、版本和下载 URL。
- Pages 页面和发布历史。
- `redistribution.toml` 中登记的许可页面。
- Compose 设置和服务器默认规则。

以下内容绝不能提交：

- `.env`。
- RCON 密码。
- restic 密码。
- S3 Access Key / Secret Key。
- 世界、玩家数据和备份。
- 内网穿透账号或令牌。

## 14. 本机备份

### 14.1 备份类型

| 类型 | 位置 | 触发方式 |
|---|---|---|
| 在线备份 | `runtime/backups/local/` | 正式服每两小时、`backup`、关服、测试前 |
| 停服快照 | `runtime/backups/offline/` | 开服前、正式服停止时执行 `backup`、测试前 |

本机策略保留约 14 天，并限制最近约 20 份。具体在线文件名和格式由备份容器生成；脚本同时识别 `.tar.zst`、`.tgz` 和 `.tar.gz`。

两者的用途不同：在线备份由 `backup-local` 在服务器运行时通过 RCON 协调保存，适合日常回退；停服快照是在服务器停止后直接打包 `runtime/data/`，适合开服前、测试服建立前和世界重置前使用。

### 14.2 手动备份

```bash
./mcctl backup
```

- 正式服运行时：通过 RCON 协调在线备份。
- 正式服停止时：直接从 `runtime/data/` 创建停服快照。
- 数据目录为空时：不会生成无意义快照。

### 14.3 列出备份

```bash
./mcctl backup-list
```

输出顶部会分别统计 `local` 在线备份、`offline` 停服快照及两者合计的文件数和容量，随后用人类可读单位列出每个归档的大小。交互面板总览显示合计占用，“世界与备份”分类标题会显示 local、offline 和总计，并在创建或删除后立即刷新。远端 restic 快照不计入这里的本机占用。

整合包测试开始时创建的归档也计入这些统计。测试通过后，面板默认删除本次会话唯一追踪到的专用备份；测试失败则保留。这个自动清理不会按文件名或“最新备份”猜测目标。

恢复和删除命令只接受列表显示的归档文件名，不接受任意路径。交互菜单选择“删除备份”时使用 `[y/N]` 确认，默认不删除；直接使用以下非交互命令时仍必须显式传入 `--confirm`：

删除单个本机归档：

```bash
./mcctl backup delete <归档文件名> --confirm
```

快捷别名：

```bash
./mcctl backup-delete <归档文件名> --confirm
```

删除是永久操作，必须带 `--confirm`。如果 local 和 offline 中存在同名文件，使用 `local/<文件名>` 或 `offline/<文件名>` 指定来源；在线备份调度器正在运行时不能删除 local 归档。该命令不会影响远端 restic 备份。

### 14.4 解压测试

```bash
./mcctl restore-test <备份文件名>
```

文件会解压到：

```text
runtime/restore-test/<时间戳>/
```

检查至少存在：

- `level.dat`。
- 世界目录或 `region/`。
- `playerdata/`（已有玩家时）。
- 需要保留的配置与白名单。

解压成功不等于世界逻辑完全正常；重要恢复还应在隔离环境启动验证。

### 14.5 正式恢复

1. 停止正式服务器：

```bash
./mcctl stop
./mcctl status
```

2. 先测试解压：

```bash
./mcctl restore-test <备份文件名>
```

3. 执行恢复：

```bash
./mcctl restore <备份文件名> --confirm
```

原来的 `runtime/data/` 会移动为：

```text
runtime/data.pre-restore.<时间戳>
```

不会立即删除。如果解压过程失败，脚本会尝试把原目录放回。

4. 启动并检查：

```bash
./mcctl start
./mcctl logs
```

确认世界、玩家位置、背包、机器、维度和白名单正常前，不要删除 `data.pre-restore.*`。

### 14.6 备份范围限制

世界备份不能恢复：

- Git 仓库中尚未推送的代码。
- `.env`。
- RCON、restic、S3 密钥。
- Windows 内网穿透配置。

这些内容需要单独安全保存。

## 15. 异地备份

### 15.1 配置

`.env`：

```text
ENABLE_REMOTE_BACKUP=true
RESTIC_REPOSITORY=s3:https://你的S3端点/存储桶/wezza-mc
RESTIC_HOSTNAME=wezza-home-pc
AWS_DEFAULT_REGION=区域或auto
```

`secrets/aws_credentials`：

```ini
[default]
aws_access_key_id = 你的AccessKey
aws_secret_access_key = 你的SecretKey
```

`secrets/restic_password.txt` 是加密密钥。丢失后远端快照无法恢复，必须把它另存到可信密码管理器；不要只保留在这台电脑上。

### 15.2 保留策略

- 最近 14 个日快照。
- 最近 8 个周快照。
- 最近 12 个月快照。

### 15.3 启用前验证

先使用没有重要数据的测试存储桶，验证：

- 凭据权限仅覆盖目标前缀。
- 可以创建快照。
- 可以列出快照。
- 在另一临时目录中可以恢复。
- 更换电脑后仍能使用同一个 restic 密码恢复。

当前 `mcctl` 主要在安全关服时调用远端备份；它不替代本机两小时备份。

## 16. 修改服务器规则

### 16.1 普通调整

MOTD、人数、内存和端口优先修改 `.env`。难度、游戏模式、视距、模拟距离、PVP、命令方块等共享规则修改 `compose.yaml`。

修改后：

```bash
docker compose config --quiet
git diff -- compose.yaml .env.example
```

`.env` 不提交；如果新增了所有管理员都应知道的变量，应同步更新 `.env.example` 和文档。

### 16.2 发布配置变更

不涉及模组清单的设置变更不使用 `mod publish`：

```bash
git add compose.yaml .env.example docs/ADMIN_GUIDE.md
git diff --cached
git commit -m "chore: update server settings"
git push origin main
```

然后在维护窗口安全重启：

```bash
./mcctl restart
```

### 16.3 内存调整

不要把 `MEMORY` 设置成物理内存的大部分。至少为以下内容留空间：

- Windows。
- WSL 与 Docker Desktop。
- PCL2/Minecraft 客户端。
- 测试服（如果同时运行）。
- 文件缓存和压缩备份。

卡顿不一定是内存不足。先使用：

```bash
./mcctl rcon "spark healthreport"
```

再判断是区块生成、实体、机器逻辑、网络还是垃圾回收。

## 17. 升级 Minecraft、Fabric 或 Java

这是完整更新，不能按普通模组小更新处理。

### 17.1 升级前条件

- Fabric Loader 支持目标 Minecraft。
- Fabric API 支持目标版本。
- Refined Storage、Time in a Bottle 和其他内容模组全部兼容。
- 性能模组有目标 Fabric 版本。
- Java 与服务器镜像支持目标 Minecraft。
- 已创建并测试旧世界备份。
- 已预留回退分支和维护时间。

核心内容模组缺失时继续运行旧版本，不要为了追新版本直接删除世界内容。

### 17.2 建立升级分支

```bash
git switch -c upgrade/minecraft-目标版本
```

### 17.3 需要同步修改的位置

- `pack/pack.toml` 中的 Minecraft/Fabric 版本。
- `compose.yaml` 中的 `VERSION`、`FABRIC_LOADER_VERSION`、Java 镜像标签和镜像摘要。
- `tools/validate_pack.py` 中的固定版本规则。
- `.env.example` 的 MOTD 或相关默认值。
- `site/index.html` 展示值。
- 本管理员手册中的当前版本。
- 所有模组元数据。

搜索旧版本：

```bash
rg '26\.1\.2|0\.19\.3|java25' .
```

### 17.4 更新和测试

```bash
./mcctl mod update all
./mcctl mod check
./mcctl stage start
./mcctl stage logs
```

使用正式世界备份副本完整测试：

- 首次升级启动。
- 进入已有区块和新生成区块。
- 原有物品、方块、机器和维度。
- 保存并关闭。
- 第二次启动。
- 新客户端 `.mrpack` 导入和连接。
- 备份工具与 RCON。

通过后：

```bash
./mcctl stage finish --delete-backup --confirm
```

交互面板会在完成测试后直接询问发布类型；命令行方式则继续执行 `./mcctl mod publish full`。

### 17.5 合并回 `main`

先在升级分支保留测试提交：

```bash
git add -A
git commit -m "test: validate Minecraft 目标版本 upgrade"
```

回到 `main` 并把内容以 squash 方式放入工作区：

```bash
git switch main
git merge --squash upgrade/minecraft-目标版本
git restore --staged .
```

先提交 `pack/` 和发布记录以外的配套变更：

```bash
git add -A -- . ':(exclude)pack' ':(exclude)site/release.json'
git commit -m "chore: prepare Minecraft 目标版本"
```

保持 `pack/` 为待发布变更，执行完整发布：

```bash
./mcctl mod publish full
```

发布工具会因为 Minecraft 版本变化把版本号重置为目标版本的 `r1`。

### 17.6 正式升级

1. 再次确认可恢复备份。
2. 等待 Pages 成功。
3. 通知所有玩家重新导入。
4. 在维护窗口启动正式服。
5. 检查日志和世界。
6. 确认无误后才开放穿透。

旧世界被新版本成功保存后，不要假定还能直接切回旧 Minecraft。回退应恢复升级前备份，而不是让旧服务端打开已升级世界。

## 18. 换电脑与灾难恢复

### 18.1 必须带走的内容

- 最新且经过测试的世界备份。
- `.env`。
- `secrets/restic_password.txt`。
- `secrets/aws_credentials`（如果继续使用原远端仓库）。
- 内网穿透配置和账号信息。
- GitHub/SSH 登录能力。

RCON 密码可以重新生成，但继续使用原 restic 仓库必须保留原 restic 密码。

### 18.2 新电脑步骤

```bash
git clone git@github.com:izumiChan16/wezza-mc.git wezza_mc
cd wezza_mc
./mcctl init
```

然后：

1. 恢复 `.env` 或重新填写。
2. 放回原 restic 密码和 S3 凭据。
3. 把世界备份放入 `runtime/backups/offline/`。
4. 执行 `backup-list` 和 `restore-test`。
5. 执行正式恢复。
6. 配置 Docker Desktop WSL integration。
7. 配置 Windows 穿透。
8. 启动并验证。

## 19. 故障排查

### 19.1 Docker Desktop 不可用

现象：

```text
Docker Desktop is not reachable from this WSL distribution.
```

检查：

1. Docker Desktop 是否运行。
2. Settings 中是否启用 WSL integration。
3. 是否勾选 Arch 发行版。
4. `docker info` 是否成功。

### 19.2 EULA 拒绝

脚本提示设置 `EULA=TRUE` 时，先确认本人已阅读并接受 EULA，再编辑 `.env`。不要修改脚本绕过检查。

### 19.3 启动三分钟仍不健康

```bash
docker compose logs --tail 200 minecraft
```

重点搜索：

- 版本不匹配。
- 缺少 Fabric 依赖。
- 客户端专用模组进入服务器。
- Mixin 或注册表错误。
- 世界数据解析失败。
- Packwiz 下载 URL 或哈希失败。

不要反复强制启动同一个失败世界。先保存日志、确认备份，再在测试副本定位。

### 19.4 测试服无法完成

“测试没有问题：完成并清理”要求 `minecraft-staging` 正在运行且健康，而且当前清单与会话中测试的清单一致：

```bash
./mcctl stage logs
./mcctl status
```

如果清单有变化，维护页会显示“重新建立并启动测试服”；如果服务不健康，先看日志。不要手工伪造 `SESSION` 或 `ACCEPTED_PACK_SHA256`。

如果出现 `OCI runtime create failed`、`docker-desktop-bind-mounts` 或挂载 `/data` 时 `no such file or directory`，这是 Docker Desktop 与 WSL 之间的旧 bind mount 已失效，不代表世界恢复失败。返回“维护整合包”，先查看已保存的失败详情，再选择“修复后重试启动测试服”。重试会强制重建 staging 容器，但保留并复用本次测试备份，不应选择“结束本次测试”。若重试仍失败，重启 Docker Desktop 后再次执行同一重试动作。

### 19.5 发布提示没有接受记录

完整执行：

```bash
./mcctl stage start
./mcctl stage logs
./mcctl stage finish --delete-backup --confirm
```

日常使用面板的“维护整合包”完成同一流程。

### 19.6 发布提示清单在接受后改变

说明完成测试之后又修改了 `pack/`。重新测试当前清单，不要覆盖接受文件。

### 19.7 发布提示非 Pack 文件未提交

检查：

```bash
git status --short
git diff
```

把脚本、文档或 Compose 变更单独审查并提交，再执行 `mod publish`。不要为了通过检查随意删除不认识的文件。

### 19.8 发布提示不在 `main`

普通模组发布必须先把已测试内容安全带回 `main`。不要在功能分支直接推送 Pages 发布。

### 19.9 再分发批准缺失或过期

```bash
python3 tools/release_pack.py safety --pack-dir pack
sha256sum pack/mods/对应文件.pw.toml
```

重新核对许可并更新 `pack/redistribution.toml`。如果许可不明确，应移除候选模组。

### 19.10 Pages 失败

```bash
gh run list --workflow pages.yml --limit 5
gh run view <运行编号> --log-failed
```

常见原因：

- `index.toml` 哈希陈旧。
- `site/release.json` 与 `pack.toml` 版本不一致。
- 非 Modrinth 批准过期。
- MRPACK 导出失败。
- 工作流语法或依赖问题。

### 19.11 玩家 PCL2 导入后没有模组

确认：

- 下载的是 `.mrpack`，没有先解压。
- Pages 工作流成功。
- 文件不是浏览器缓存中的旧下载。
- PCL2 导入日志没有网络、源站或哈希错误。
- 玩家是在导入阶段等待下载完成，而不是只创建空版本。

删除不完整的 PCL2 版本，重新下载当前 `wezza-mc-latest.mrpack` 后导入。不要把服务端 `mods` 整目录交给玩家。

### 19.12 玩家提示模组不一致

1. 查看更新页当前整合包版本。
2. 确认玩家没有自行更新单个模组。
3. 小更新逐项核对准确文件名。
4. 完整更新确认玩家导入了新实例。
5. 确认正式服在 Pages 发布后重新启动。
6. 检查元数据 `side`。

### 19.13 服务器卡顿

```bash
./mcctl rcon "list"
./mcctl rcon "spark healthreport"
```

结合日志判断：

- 新区块生成。
- 实体或掉落物过多。
- 自动化机器逻辑。
- 网络延迟。
- Java 垃圾回收。
- 磁盘或备份压缩争用。

不要先入为主地增加内存。

### 19.14 Windows 即将关机

优先：

```bash
./mcctl stop
```

等待完成。若 Windows 已进入紧急倒计时，仍优先让 Minecraft 保存并停止，不要直接结束 Docker Desktop。

## 20. 管理员检查清单

### 20.1 每次开服

- [ ] Docker Desktop 正常。
- [ ] 内网穿透已启动且目标仍是 `127.0.0.1:25565 TCP`。
- [ ] 没有正在进行但尚未完成的模组维护。
- [ ] `./mcctl start` 成功。
- [ ] `./mcctl status` 正常。
- [ ] 日志无错误。
- [ ] 再通知玩家。

### 20.2 每次关服

- [ ] 提前通知玩家。
- [ ] 执行 `./mcctl stop`。
- [ ] 确认本机备份成功。
- [ ] 如启用远端备份，确认远端步骤成功。
- [ ] 确认容器停止。
- [ ] 再关闭穿透、Docker Desktop 或 Windows。

### 20.3 每次模组发布

- [ ] 兼容性和依赖已调查。
- [ ] 安装侧正确。
- [ ] 非 Modrinth 许可已登记。
- [ ] `./mcctl mod check` 通过。
- [ ] 已有最近世界备份。
- [ ] 测试服启动和重启均正常。
- [ ] 内容、存档和性能已检查。
- [ ] 客户端 `.mrpack` 已测试。
- [ ] 已选择“测试没有问题：完成并清理”。
- [ ] 已正确选择 `small` 或 `full`。
- [ ] Pages 工作流成功。
- [ ] 正式服使用新清单启动成功。
- [ ] 已向玩家发送准确更新方式。

### 20.4 每次 Minecraft 大版本升级

- [ ] 核心模组全部兼容。
- [ ] 旧世界备份已做恢复测试。
- [ ] 使用独立升级分支。
- [ ] Compose、Packwiz、校验器、页面和文档版本一致。
- [ ] 世界副本完成首次和二次启动测试。
- [ ] 新客户端完成导入和连接测试。
- [ ] 以 `full` 发布。
- [ ] 玩家被明确要求重新导入。
- [ ] 正式升级验证完成前没有开放公网。

## 21. 命令速查

### 21.1 服务器

| 命令 | 作用 |
|---|---|
| `./mcctl` | 在交互终端中打开状态总览和方向键菜单 |
| `./mcctl menu --plain` | 使用不依赖 `fzf` 的编号菜单 |
| `./mcctl doctor` | 只读检查配置、依赖、密钥、Docker 和发布元数据 |
| `./mcctl help --all` | 查看全部高级非交互命令 |
| `./mcctl init` | 创建本机配置、运行目录和密钥 |
| `./mcctl start` | 先做停服快照，再启动正式服和备份调度器 |
| `./mcctl stop` | 通知、保存、本机/远端备份并关服 |
| `./mcctl stop --skip-remote` | 保留本机备份，但跳过本次远端备份 |
| `./mcctl restart` | 完整安全关服后启动 |
| `./mcctl status` | 查看正式服和测试服容器状态及本机端口 |
| `./mcctl logs` | 跟随正式服日志 |
| `./mcctl console` | 连接服务器控制台 |
| `./mcctl rcon "命令"` | 执行 Minecraft 管理命令 |

### 21.2 世界

| 命令 | 作用 |
|---|---|
| `./mcctl world status` | 查看世界路径、状态、种子配置和归档 |
| `./mcctl world reset --seed <整数> --confirm` | 归档旧世界并配置指定种子 |
| `./mcctl world reset --random --confirm` | 归档旧世界并配置随机种子 |

### 21.3 玩家权限

| 命令 | 作用 |
|---|---|
| `./mcctl whitelist add 玩家名` | 加入白名单 |
| `./mcctl whitelist remove 玩家名` | 移出白名单 |
| `./mcctl whitelist list` | 查看白名单 |
| `./mcctl rcon "op 玩家名"` | 授予 OP |
| `./mcctl rcon "deop 玩家名"` | 撤销 OP |

### 21.4 模组

| 命令 | 作用 |
|---|---|
| `./mcctl mod list` | 列出 metadata slug、安装侧、来源和名称 |
| `./mcctl mod add <slug或URL>` | 添加候选模组 |
| `./mcctl mod remove <slug>` | 可恢复地移除元数据 |
| `./mcctl mod side <slug> <client\|server\|both>` | 修正安装侧 |
| `./mcctl mod update-check` | 在临时副本检查全部更新 |
| `./mcctl mod update <slug>` | 更新一个候选模组 |
| `./mcctl mod update all` | 更新全部候选模组 |
| `./mcctl mod check` | 刷新并验证当前候选清单 |
| `./mcctl mod publish small` | 发布已有玩家可手动处理的小更新 |
| `./mcctl mod publish full` | 发布要求玩家重新导入的完整更新 |
| `./mcctl client build` | 在 `dist/` 构建并验证本地标准 `.mrpack` |

### 21.5 测试服

| 命令 | 作用 |
|---|---|
| `./mcctl stage start` | 创建一次备份并建立新的隔离测试会话 |
| `./mcctl stage resume` | 继续现有测试会话，不重复备份 |
| `./mcctl stage rebuild` | 用最新候选清单和原备份重建测试服 |
| `./mcctl stage logs` | 跟随测试服日志 |
| `./mcctl stage error` | 查看最近一次被保存的测试服启动错误 |
| `./mcctl stage stop` | 暂停测试服并保留会话 |
| `./mcctl stage finish --delete-backup --confirm` | 验收、停服、清理副本并删除可确认的专用备份 |
| `./mcctl stage finish --keep-backup --confirm` | 验收并清理测试副本，但保留备份 |
| `./mcctl stage discard --confirm` | 结束失败测试，保留备份和候选变更 |
| `./mcctl stage cleanup --confirm` | 清理没有活动会话的旧测试世界副本 |
| `./mcctl stage accept` | 高级：只记录清单哈希，不结束会话 |

### 21.6 备份恢复

| 命令 | 作用 |
|---|---|
| `./mcctl backup` | 创建在线本机备份或停服快照 |
| `./mcctl backup-list` | 列出备份、类型、单个大小及 local/offline/总计占用 |
| `./mcctl backup delete <文件名> --confirm` | 删除一个本机备份 |
| `./mcctl backup-delete <文件名> --confirm` | 删除备份的快捷别名 |
| `./mcctl restore-test <文件名>` | 解压到隔离目录检查 |
| `./mcctl restore <文件名> --confirm` | 停服状态下可恢复地替换正式数据 |

## 22. 发生事故时的优先级

当你不确定下一步怎么做时，按这个顺序：

1. 不要继续让正式世界写入可疑状态。
2. 正常停服；如果已崩溃，不要反复启动。
3. 保存日志、当前 Git 状态和错误信息。
4. 确认最近备份及其可解压性。
5. 使用隔离测试目录或测试服复现。
6. 确定修复方案后再动正式数据。
7. 恢复或修复后完整验证，再向玩家开放。

最危险的操作通常不是第一次报错，而是在没有备份和记录的情况下连续尝试多个不可逆修复。
