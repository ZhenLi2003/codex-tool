# codex-tool

[English README](../README.md)

`codex-tool` 是一个面向 **Linux x86_64 / amd64** 的轻量级 OpenAI Codex CLI 版本管理工具。

它适合希望快速安装和管理 Codex CLI、又不想改动系统环境的用户：

- **无需 root / sudo 权限**：所有内容均安装在当前用户目录下。
- **无需 npm / Node.js**：直接从 GitHub Releases 安装官方 standalone Codex 完整包。
- **安装简单**：项目核心只有 `install.sh` 和 `codex-tool` 两个脚本。
- **支持多版本切换**：可同时保留多个 Codex 版本，并快速切换当前版本。
- **安装完整运行时**：使用完整 Codex package，包括 `codex-code-mode-host` 等现代组件。
- **适配新版 app-server/daemon 生命周期**：版本激活与 managed daemon 协调；会话清理由 Codex 官方 app-server API 完成，不再直接删除 `CODEX_HOME` 内部状态。
- **只读命令不再被全局锁阻塞**：`version`、`help`、`list`、`auth status`、`daemon status` 不获取独占 manager lock。
- **明确数据所有权**：codex-tool 直接管理自己的 CLI 版本；持久化 thread 则交给 Codex 官方 app-server RPC 管理。
- **适合不稳定网络**：大文件支持断点续传、自动重试和 SHA-256 校验。
- **自动处理 GitHub API 限流场景**：如果共享代理出口耗尽匿名 API 配额，工具会先尝试直连；若直连不可用，则在交互终端中引导创建 GitHub access token，隐藏输入并验证后，以 `0600` 权限保存，后续 API 请求自动复用。

> `codex-tool` 是社区工具，并非 OpenAI 官方项目。

## 快速开始

### 1. 克隆并安装管理器

```bash
git clone https://github.com/ZhenLi2003/codex-tool.git
cd codex-tool
./install.sh
```

如果当前 shell 尚未包含 `~/.local/bin`：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

检查管理器版本：

```bash
codex-tool version
```

### 2. 安装 Codex CLI

安装最新稳定版：

```bash
codex-tool update
```

或者安装指定稳定版本：

```bash
codex-tool install 0.154.0
```

整个过程无需：

```text
sudo
root
npm install -g
Node.js
```

## 版本管理

查看本地已安装版本：

```bash
codex-tool list
```

切换版本：

```bash
codex-tool switch 0.154.0
```

删除旧版本：

```bash
codex-tool delete 0.153.0
```

默认会保留当前版本以及最多两个历史版本。

## 命令概览

```text
codex-tool install X.Y.Z          安装/修复指定稳定版本并激活
codex-tool update                 安装并激活最新稳定版本
codex-tool list                   查看当前版本和本地已安装版本
codex-tool switch X.Y.Z           切换到已安装版本
codex-tool delete X.Y.Z           删除非当前版本
codex-tool clean [--all] [--dry-run] [--yes]
                                  通过 Codex app-server 清理持久化会话；默认只删除
                                  非活跃 thread，--all 会中断并删除后台 thread
codex-tool prune [--dry-run] [--yes] [--force]
                                  删除 loaded/background thread、停止 daemon，并清理
                                  Codex 程序/runtime；保留非活跃历史和用户配置/认证
codex-tool version                查看 codex-tool 版本
codex-tool daemon status          查看 app-server daemon 状态
codex-tool daemon repair [--yes]  修复 stale managed daemon 运行时状态
codex-tool auth login             保存并验证 GitHub access token
codex-tool auth status            查看当前 GitHub 认证来源
codex-tool auth logout            删除 codex-tool 保存的 token
codex-tool help                   查看帮助
```

## 系统要求

目标平台：

```text
Linux x86_64 / amd64
```

依赖常见命令行工具：

- Bash
- `curl`
- `python3`
- `tar`
- `sha256sum`
- `flock`

不依赖：

- root 权限
- sudo
- npm
- Node.js
- 系统级 Codex 安装

## 默认安装目录

管理器和 Codex 版本默认存放在：

```text
~/scripts/codex-tool/
├── codex-tool
├── current -> versions/X.Y.Z
├── downloads/
└── versions/
    └── X.Y.Z/
        ├── bin/codex
        ├── bin/codex-code-mode-host
        ├── codex-path/
        ├── codex-resources/
        └── ...
```

命令链接：

```text
~/.local/bin/codex-tool
~/.local/bin/codex
```

Codex 用户配置和运行数据仍保存在：

```text
~/.codex/
```

升级管理器、安装新版本或切换版本都不会自动清空该目录。

## Daemon-aware 生命周期

新版 Codex 已经是由长期运行的 app-server、持久化 thread store、SQLite state、writer lock 和 managed daemon package 共同组成的本地运行时。codex-tool 1.8.0 不再把 `CODEX_HOME` 当作可以直接清理的缓存目录。

对于 `install` / `update` / `switch`，下载、SHA 校验和 package validation 阶段不会打断现有 daemon；真正激活版本时才停止健康的 managed daemon，并在切换后恢复。

会话管理改为调用 Codex 官方 app-server JSON-RPC：

```text
thread/list
thread/read
thread/loaded/list
thread/turns/list
turn/interrupt
thread/delete
```

### clean

```bash
codex-tool clean --dry-run
codex-tool clean
codex-tool clean --all
```

默认 `clean` 删除当前状态不是 active 的持久化 thread，健康的后台 app-server/daemon 保持运行。

`clean --all` 会额外对 active thread 请求 `turn/interrupt`，等待其退出 active 状态，然后通过 `thread/delete` 删除持久化记录。

任何 clean 模式都不会直接删除 `sessions/`、`archived_sessions/`、`thread_history_*.sqlite`、`state_*.sqlite` 或 Codex 锁文件。

### prune

`prune` 定位为“程序与后台 runtime 清理”：

1. 通过 app-server 枚举 loaded/background thread；
2. 对 active turn 请求 interrupt；
3. 停止 managed daemon；
4. 使用临时 stdio app-server 删除此前 loaded/background thread 的持久化记录；
5. 删除 codex-tool 管理的版本/current/download cache、`codex` 链接、managed daemon/standalone package，以及 daemon runtime state。

默认保留已经结束的非活跃会话历史，以及用户配置、认证、skills、rules 等用户状态。

如果仍有前台 Codex 进程正在使用受管理 executable，prune 会 fail closed，不会从运行进程下方删除程序文件。

诊断和 stale-state 修复仍使用：

```bash
codex-tool daemon status
codex-tool daemon repair
```

## GitHub API 认证与限流恢复

GitHub 未认证 REST API 会按源 IP 限流，共享实验室代理或公共出口比较容易耗尽匿名配额。

当检测到明确的匿名 API rate limit 后，codex-tool 会：
1. 先仅针对该 API 元数据请求尝试绕过代理直连；
2. 如果直连失败且当前是交互终端，显示预填充的 GitHub fine-grained token 创建网址；
3. 只要求仓库 `Contents: read`，以隐藏方式读取 token，并使用当前正常代理路径验证其能访问公开的 `openai/codex` release API；
4. 验证成功后保存到 `~/.config/codex-tool/github-token`，文件权限为 `0600`；
5. 后续 API 请求自动使用该 token，从而使用认证后的 GitHub API 配额。

也可以手动管理：

```bash
codex-tool auth login
codex-tool auth status
codex-tool auth logout
```

如设置了环境变量 `GITHUB_TOKEN`，其优先级高于工具保存的 token。

## Manager 锁机制

codex-tool 1.7.1 对只读命令不再获取独占锁：

```bash
codex-tool version
codex-tool help
codex-tool list
codex-tool auth status
codex-tool daemon status
```

需要修改版本或运行状态的命令才获取 manager lock。锁优先存放于：

```text
$XDG_RUNTIME_DIR/codex-tool
```

如果不可用，则使用：

```text
/tmp/codex-tool-$UID
```

锁目录必须属于当前用户，并强制为 `0700`。锁等待由 `CODEX_TOOL_LOCK_TIMEOUT` 控制，默认 10 秒；超时后会明确报错，并在可用时显示持锁 PID/命令，不再无限卡住。

1.8.0 进一步要求所有可能启动或连接长期 Codex daemon 的子进程在 exec 前显式关闭 codex-tool 的 manager-lock FD；codex-tool 自身退出时也显式 unlock/close。这样后台 app-server/updater 不会再继承并长期占用 codex-tool 的 `flock`。

## 文档

- [完整使用手册](USAGE.md)
- [版本迭代历史](CHANGELOG.md)
- [English README](../README.md)
- [MIT License](../LICENSE)

## License

MIT，详见 [LICENSE](../LICENSE)。
