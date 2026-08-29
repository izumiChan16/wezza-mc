# Wezza MC

一个面向 2–8 人的 Fabric 26.1.2 私服仓库。服务器运行在 Windows 的 Docker Desktop 中，通过 Arch Linux WSL 执行管理命令；默认随玩随开，不会随电脑自动常驻。

仓库把三类数据分开：

- `pack/`：可以提交的 Packwiz 模组清单，是服务端与玩家端的唯一版本来源。
- `compose.yaml` 与 `mcctl`：可以提交的部署和运维逻辑。
- `runtime/`、`.env`、`secrets/`：世界、备份和私人配置，均不会提交。

## 当前版本

| 项目 | 固定版本 | 安装侧 |
|---|---:|---|
| Minecraft | 26.1.2 | 双方 |
| Fabric Loader | 0.19.3 | 双方 |
| Fabric API | 0.155.2 | 双方 |
| Refined Storage | 3.2.1 | 双方 |
| Time in a Bottle | 7.0.1 | 双方 |
| FerriteCore | 9.0.0 | 双方 |
| Lithium | 0.24.7 | 服务端 |
| Krypton | 0.3.0 | 服务端 |
| ServerCore | 1.5.19 | 服务端 |
| spark | 1.10.173 | 服务端 |
| Sodium | 0.9.1 | 客户端 |

`pack/index.toml` 和每个 `.pw.toml` 同时锁定文件哈希。服务端专用模组不会被玩家端下载，客户端专用模组不会进入服务器。

## 第一次部署

### 1. 准备 Docker Desktop

在 Docker Desktop 中启用 Arch WSL integration。项目必须保存在 WSL 的 Linux 文件系统中，例如当前的 `/home/izumi/wezza_mc`，不要移动到 `/mnt/c`。

确认 WSL 可以访问 Docker：

```bash
docker info
docker compose version
```

### 2. 初始化私人配置

```bash
./mcctl init
```

编辑 `.env`：

1. 阅读并接受 [Minecraft EULA](https://aka.ms/MinecraftEULA) 后，将 `EULA=FALSE` 改为 `EULA=TRUE`。
2. 把 `PACKWIZ_URL` 改成仓库的 GitHub Pages 地址，必须以 `/pack.toml` 结尾。
3. 如有需要，修改内存、端口、MOTD 和时区。

### 3. 建立 GitHub 仓库和 Pages

当前执行环境如果还没有正常的 Git 仓库，在普通终端中初始化并推送：

```bash
git init -b main
git add .
git commit -m "feat: initialize Fabric server"
git remote add origin <你的 GitHub 仓库地址>
git push -u origin main
```

在 GitHub 仓库的 **Settings → Pages → Build and deployment** 中选择 **GitHub Actions**。`pages.yml` 会发布：

- 在线 Packwiz 清单；
- 当前模组列表；
- 玩家首次导入用的 `wezza-mc-prism.zip`。

Pages 首次成功后，将页面对应的 `.../pack.toml` 地址写入 `.env`。

### 4. 启动服务器

```bash
./mcctl start
./mcctl logs
```

启动命令会先备份已有数据，然后等待服务器健康检查通过。Windows 上的内网穿透客户端只需转发：

```text
127.0.0.1:25565 TCP
```

不要转发 RCON 或 `25566` 测试端口。

添加第一名玩家：

```bash
./mcctl whitelist add 玩家Java版名称
```

### 5. 玩家安装

玩家访问 GitHub Pages，下载 `wezza-mc-prism.zip`，然后在 Prism Launcher 中选择：

```text
添加实例 → 导入 → 选择 wezza-mc-prism.zip
```

该实例包含 Packwiz 的启动前更新命令。首次启动以及此后每次启动时，它都会读取 Pages；玩家不需要在每次模组变化后重新导入 ZIP。

Minecraft 26.1.2 需要 Java 25。Prism 应为该实例选择 Java 25，并分配约 6GB 客户端内存。

## 日常启停

```bash
./mcctl start
./mcctl status
./mcctl logs
./mcctl stop
```

`stop` 会广播提示、等待 10 秒、执行 `save-all flush`、创建本机备份，然后优雅停服。Windows 关机、睡眠或关闭 Docker Desktop 前应先执行它。

如果启用了远程备份但 S3 暂时不可用，服务器会保持运行，避免在没有完成计划备份时关服。确认本机备份存在后可使用：

```bash
./mcctl stop --skip-remote
```

## 新增或更新模组

### 添加 Modrinth 模组

```bash
./mcctl mod add sodium
./mcctl mod add https://modrinth.com/mod/sodium
```

没有写网站的 slug 默认按 Modrinth 查找。

### 添加 CurseForge 模组

```bash
./mcctl mod add https://www.curseforge.com/minecraft/mc-mods/example-mod
```

Packwiz 会保存 CurseForge 项目和文件元数据。若作者禁止第三方自动下载，Packwiz 可能要求手动文件；这种模组默认不得发布，除非作者许可证明确允许重新托管。

### 添加作者官方直链

```bash
./mcctl mod add https://github.com/author/project/releases/download/v1.0/example.jar
```

直链模组不会自动获得可靠的版本更新元数据。发布前必须检查作者身份、HTTPS 地址、SHA 哈希和再分发许可证；优先使用作者官方 GitHub Release。

### 更新和删除

```bash
./mcctl mod update-check       # 在 /tmp 副本中检查，不改正式清单
./mcctl mod update 模组名称
./mcctl mod update all
./mcctl mod remove metadata-slug
./mcctl mod side metadata-slug client   # 也可以是 server 或 both
./mcctl mod check
```

这些命令只产生本地候选版本，不会立即改变 Pages 或正式服务器。
添加或更新会先在 `/tmp` 副本中完成；如果解析到 alpha、beta 或 snapshot 文件，校验会拒绝它，真实清单保持不变。CurseForge 无法可靠提供安装侧时，用 `mod side` 明确修正。

### 测试并发布

```bash
./mcctl stage start
./mcctl stage logs
```

测试服使用备份恢复出的独立数据，监听 `127.0.0.1:25566`，并从本地候选 Packwiz 清单安装模组。完成启动、联机和目标功能测试后：

```bash
./mcctl stage accept
./mcctl stage stop
./mcctl mod publish
```

`publish` 只接受已测试且测试后未再次变化的清单。它会提交 `pack/` 并推送到 `origin`，GitHub Actions 随后更新 Pages。紧急情况下可以使用 `mod publish --force`，但不推荐。

发布后的影响：

| 变化 | 服务端 | 玩家端 |
|---|---:|---:|
| 服务端专用模组 | 下次启动更新 | 不下载 |
| 客户端专用模组 | 不下载 | 下次启动更新 |
| 双方必装模组 | 下次启动更新 | 下次启动更新 |

## ZIP、MRPACK 与 Packwiz

- `wezza-mc-prism.zip` 是 Prism 实例，引导玩家连接在线 Packwiz 清单，因此能够持续更新。
- `.mrpack` 是某个时间点的 Modrinth 安装清单快照；普通 `.mrpack` 本身不会持续跟踪 Pages。
- 类似 BMC4 的 `ServerPack.zip` 通常是把特定版本的服务端模组、配置和脚本整体打包，更新时需要重新制作整包。
- 本项目不维护完整 Server Pack ZIP；Docker 和 Packwiz 能从声明重新构建服务器，世界由独立备份恢复。

确实需要 `.mrpack` 快照时，先确认所有可能被打包进去的第三方文件都允许再分发，再执行：

```bash
./mcctl client mrpack --confirm
```

输出位于 `dist/wezza-mc-manual.mrpack`，不会自动发布到 Pages。

## 备份与恢复

备份发生在：

- 每次开服前；
- 运行期间每 2 小时；
- 每次安全停服时；
- 候选模组或游戏版本测试前。

查看和测试恢复：

```bash
./mcctl backup
./mcctl backup-list
./mcctl restore-test <列表中的文件名>
```

`restore-test` 不会覆盖正式数据。确认需要正式恢复、并已经停服后：

```bash
./mcctl restore <列表中的文件名> --confirm
```

原来的 `runtime/data` 会被改名保留，而不是直接删除。

### 可选的 restic/S3

1. 在 `.env` 中设置 `ENABLE_REMOTE_BACKUP=true` 和 `RESTIC_REPOSITORY`。
2. 编辑 `secrets/aws_credentials`，填写 S3-compatible access key。
3. 保管好 `secrets/restic_password.txt`；丢失它将无法解密远程备份。

远程保留策略为 14 个日备、8 个周备、12 个每月备份。

## 常用诊断

```bash
./mcctl status
./mcctl rcon "list"
./mcctl rcon "spark healthreport"
./mcctl console
docker compose config
python3 tools/validate_pack.py pack
```

进入 `console` 后用 `Ctrl-P`、`Ctrl-Q` 分离，不要按 `Ctrl-C` 强杀容器。

## 安全边界

- `.env`、世界、备份和真实 secret 已被 `.gitignore` 排除。
- Compose 只向本机回环地址发布 Minecraft 端口。
- 白名单、正版验证和 secure profile 默认开启。
- Pages 只包含公开模组元数据和客户端引导包。
- 不要通过依赖覆盖强行运行未声明支持 26.1.2 的模组。
