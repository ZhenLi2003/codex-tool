# codex-tool

[English README](../README.md)

`codex-tool` 是一个面向 **Linux x86_64 / amd64** 的轻量级 OpenAI Codex CLI 版本管理工具。

它适合希望快速安装和管理 Codex CLI、又不想改动系统环境的用户：

- **无需 root / sudo 权限**：所有内容均安装在当前用户目录下。
- **无需 npm / Node.js**：直接从 GitHub Releases 安装官方 standalone Codex 完整包。
- **安装简单**：项目核心只有 `install.sh` 和 `codex-tool` 两个脚本。
- **支持多版本切换**：可同时保留多个 Codex 版本，并快速切换当前版本。
- **安装完整运行时**：使用完整 Codex package，包括 `codex-code-mode-host` 等现代组件。
- **感知后台 daemon 生命周期**：版本激活时安全停止/恢复 managed app-server，`clean` 不再删除 daemon 状态或 package。
- **保留用户数据**：`~/.codex` 中的配置、认证、daemon package 以及未来未知状态默认保留。
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
codex-tool clean [--yes]          仅清理已知历史/日志数据；保留配置、认证、daemon 状态/package
codex-tool prune [--yes] [--force]
                                  按需停止 managed daemon，再删除 codex-tool 管理的版本、缓存和 codex 链接
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

新版 Codex 会在 `CODEX_HOME` 下维护 managed app-server daemon。codex-tool 1.7.0 将其作为独立生命周期组件处理：

- `install` / `update` / `switch` 在下载和校验完成后，只有进入真正的版本激活事务时才停止健康的 managed daemon，并在切换后恢复。
- 如果 daemon 恢复失败，新 CLI 仍保持激活，旧版本不会被自动清理，便于后续恢复。
- `prune` 会停止 managed daemon 并故意保持 stopped，但不会删除 `CODEX_HOME/packages/app-server-daemon`、daemon 设置或用户数据。
- `clean` 改为删除 allowlist，只清理 `sessions/`、`archived_sessions/`、`history.jsonl`、`log/`。
- `clean` 不再“删除整个 `CODEX_HOME` 后恢复两个文件”，因此 `config.toml`、`auth.json`、daemon 状态、packages 以及未来未知目录都会保留。
- 如果某个受管理版本仍被前台 Codex 进程引用，`delete`、自动历史清理、同版本替换及 `prune` 都不会删除它。

诊断与修复：

```bash
codex-tool daemon status
codex-tool daemon repair
```

当 daemon 状态为 stale/unknown，或者发现 unmanaged app-server 时，普通变更命令会 fail closed；只有显式的 `daemon repair` 才进入 stale managed daemon 的恢复流程。

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

## 文档

- [完整使用手册](USAGE.md)
- [版本迭代历史](CHANGELOG.md)
- [English README](../README.md)
- [MIT License](../LICENSE)

## License

MIT，详见 [LICENSE](../LICENSE)。
