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

安装器将 `codex-tool`、`background.py` 和 `codex-launcher` 安装到 `~/scripts/codex-tool/`。**只安装管理器不会修改 Codex 用户配置**；激活 Codex 版本时才自动优化。

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
```

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
