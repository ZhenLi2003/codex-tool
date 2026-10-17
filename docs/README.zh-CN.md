# codex-tool

[English README](../README.md)

`codex-tool` 是面向 **Linux x86_64** 的 Codex CLI standalone 完整包版本管理器，支持非 root 安装，无需 npm / Node.js。

## 核心特性

- 多版本安装、切换、自动更新，默认保留当前版本及最多两个历史版本。
- **版本安装、更新或切换时默认执行后台优化**。
- 显式 `--native` 可保留 Codex 官方原生后台行为，并恢复曾由工具修改的配置。
- 只向普通交互式 Codex、`resume`、`fork` 注入 `--no-daemon`；其他子命令使用真实 Codex 二进制。
- 使用官方 app-server API 管理历史会话，不直接删除 SQLite / rollout 文件。
- 保留配置、认证、MCP、skills 和用户数据，支持 SHA-256 校验、断点续传以及 GitHub token。

> 这是社区工具，不属于 OpenAI 官方项目。

## 安装与升级管理器

```bash
git clone https://github.com/ZhenLi2003/codex-tool.git
cd codex-tool
./install.sh
export PATH="$HOME/.local/bin:$PATH"
codex-tool version
```

安装器将 `codex-tool`、`background.py`、`background_v2.py`、随包 TOML 解析器和 `codex-launcher` 安装到 `~/scripts/codex-tool/`。**只安装管理器不会修改 Codex 用户配置**；激活 Codex 版本时才自动优化。

## 版本管理

```bash
codex-tool update
codex-tool update --native
codex-tool install 0.162.1
codex-tool install 0.162.1 --native
codex-tool switch 0.162.1
codex-tool switch 0.162.1 --native
codex-tool list
codex-tool delete 0.161.0
```

默认 `install/update/switch` 会采用 Optimized（前台优化）模式；`--native` 则采用 Native（官方原生）模式。

如果检测到受管理的 app-server / updater 残留，默认优化会提示：

```text
Optimize background runtime and continue? [y/N]
```

- 输入 `y`：停止受管理的后台服务并应用优化，继续版本激活。
- 输入 `n`：放弃优化，改以 Native 模式继续版本激活。
- 显式 `--native`：跳过优化确认，直接使用 Native 模式。

**注意**：仍在执行中的后台 agent/task 可能受到服务停止的影响。建议先处理这些任务；存在真实的 codex-tool 并发操作时，工具不会绕过 manager lock。

## 后台管理（新版）

```bash
codex-tool background status
codex-tool background optimize
codex-tool background native
codex-tool background status --json
codex-tool background status --cwd ~/projects/example
codex-tool background optimize --dry-run
codex-tool background native --dry-run
```

v2.2.0 在每次执行后台命令时重新读取文件配置、Codex 生效配置及配置来源，并独立检测 daemon 和 launcher。`manifest.json` 仅供原始字段恢复，不再决定当前配置状态。TOML 采用随包 `tomlkit` 完整解析及全局排版，官方 `config/batchWrite` 负责修改用户级字段；后台 JSON 单独结构化修改。若 API 无法验证或无法写入，工具拒绝假报成功。Native 通过 schema v3（兼容 v1/v2）恢复原始字段。

Optimized 将以下配置字段设为 `false`：

在 `~/.codex/config.toml`：

```toml
check_for_update_on_startup = false

[features]
daemon_auto_start = false
```

在 `~/.codex/app-server-daemon/settings.json`：

```json
{
  "remoteControlEnabled": false,
  "updater": {
    "autoUpdateEnabled": false
  }
}
```

以上仅为被管理的字段，其他配置保持不变。

Optimized 模式将 `~/.local/bin/codex` 链接到 `codex-tool` 安装的轻量 launcher：普通交互式 Codex、`resume`、`fork` 会采用 `--no-daemon`，避免自动启动或复用共享 daemon；`exec`、`agents`、`app-server` 等显式功能直接转发给官方 CLI。

Native 模式自动恢复原先的后台配置和原始二进制直连，不会为了切换模式而主动启动 daemon。

优化模式写入 `config.toml` 时，会整理工具管理的 `[features]` 表前后空行，并为 `check_for_update_on_startup`、`daemon_auto_start` 添加 `# codex-tool:` 行注释；不会重新排列其他表或删除用户注释。恢复 Native 时会移除工具添加的注释、还原字段值与原有配置。

## 备份与恢复

首次优化前，工具会在以下目录保存原始配置快照与字段记录：

```text
~/.config/codex-tool/background/
├── manifest.json
└── backup/
    ├── config.toml
    └── daemon-settings.json
```

备份目录权限为 `0700`，文件为 `0600`。恢复 Native 时仅还原工具曾修改的字段，而不是覆盖用户后来改动的模型、MCP 等设置。

若受管理字段在优化期间被外部程序修改，工具会拒绝覆盖并报告冲突。

## 手动下载与上传安装包

运行 `codex-tool install X.Y.Z` 或 `codex-tool update` 时，工具会显示官方安装包下载链接、预期 SHA-256 以及服务器的完整上传路径。服务器网络很慢时，可以通过其他设备下载完整的 Codex standalone package，再上传到对应目录。

例如版本 `X.Y.Z`：

```text
官方下载链接：
https://github.com/openai/codex/releases/download/rust-vX.Y.Z/codex-package-x86_64-unknown-linux-musl.tar.gz

上传目录：
~/scripts/codex-tool/downloads/rust-vX.Y.Z/

上传文件名：
codex-package-x86_64-unknown-linux-musl.tar.gz
```

实际运行输出会给出**绝对路径**。上传完成后重新运行相同的 `install X.Y.Z` 命令即可，`update` 也支持本地包识别。如果此前下载尚未完成，可先用 Ctrl+C 中断，将完整包上传后重新执行。无需新增命令或参数。

优先级：**本地完整 `.tar.gz`（SHA 校验通过）→ 已有 `.part` 断点续传 → 全新自动下载**。

工具会先核对 GitHub Release 中的 SHA-256 digest 与官方校验清单，再校验上传文件的实际 SHA-256，并继续执行 tar 安全检查、完整包检查和 Codex 版本检查。上传文件必须属于当前用户且为非符号链接的普通文件。手动文件校验失败时**保留原文件并报错**，不会直接用损坏文件安装或改作断点续传；自动下载的损坏 `.part` 则沿用原有清理方式。安装成功后清理该版本下载缓存。

**限制**：服务器仍需能够获取 GitHub Release 元数据和体积较小的 checksum manifest；这不是完全离线安装。手动下载固定版本后，建议使用 `codex-tool install X.Y.Z`，避免 `update` 检查到新发布的 latest 版本。

### 手动编辑配置后的状态协调（2.1.1）

`codex-tool background status` 会对比当前实际配置与已保存的后台优化策略。如果用户手动修改了 `config.toml` 或 daemon 设置中的受管理字段，会显示 `Configuration: modified` 和具体偏移项，而不再仅凭 `manifest.json` 判断优化已经生效。

`codex-tool background optimize` 可重新应用偏移的后台配置，且**不会覆盖首次优化前保存的 Original 备份**。`codex-tool background native` 允许字段已经被用户手动还原为原值的情况正常完成恢复；只有出现既非原始值也非已应用值的冲突时才需确认。交互式命令使用 `[y/N]` 确认；非交互环境可以先检查状态，再使用 `background optimize --yes` 或 `background native --yes`。

升级兼容旧版 schema v1 备份，自动迁移到 v2，保留用户手动修改的其他模型、MCP 和配置字段。涉及版本激活和卸载的流程会在停止 daemon 或删除持久化 thread 之前检查配置冲突。

## 会话清理与卸载

```bash
codex-tool clean --dry-run
codex-tool clean
codex-tool clean --all

codex-tool prune --dry-run
codex-tool prune
codex-tool prune --purge-history
```

`clean` 默认清理不活跃会话，`--all` 包含活跃及后台会话。会话删除通过官方 thread API 完成。

`prune` 移除 Codex 程序、受管理 daemon/runtime 和后台 thread，默认保留非活跃历史，并在卸载前恢复工具管理的后台配置字段。认证、MCP、skills 等用户数据不会被直接清空。

## 锁机制与兼容性

工具保留本机有超时的 manager lock。只读命令不获取独占锁。Codex 子进程启动时不继承 manager lock FD；旧版本 daemon 遗留的持锁问题只在确认真实持有进程身份后恢复。

为保持 CLI 简洁，已移除旧版公开的 `codex-tool stop`、`codex-tool daemon ...` 命令。普通管理使用 `background status/optimize/native`；需要手工排障时仍可使用 Codex 官方 `codex app-server daemon ...` 命令。

## GitHub 认证

```bash
codex-tool auth login
codex-tool auth status
codex-tool auth logout
```

支持环境变量 `GITHUB_TOKEN`、本地保存的 token 和代理出口 GitHub API 限流恢复。详细参数见 [使用指南](USAGE.md)。

## 许可证

MIT，见 [LICENSE](../LICENSE)。
