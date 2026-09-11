# codex-tool

[English README](../README.md)

`codex-tool` 是一个面向 **Linux x86_64 / amd64** 的轻量级 OpenAI Codex CLI 版本管理工具。

它适合希望快速安装和管理 Codex CLI、又不想改动系统环境的用户：

- **无需 root / sudo 权限**：所有内容均安装在当前用户目录下。
- **无需 npm / Node.js**：直接从 GitHub Releases 安装官方 standalone Codex 完整包。
- **安装简单**：项目核心只有 `install.sh` 和 `codex-tool` 两个脚本。
- **支持多版本切换**：可同时保留多个 Codex 版本，并快速切换当前版本。
- **安装完整运行时**：使用完整 Codex package，包括 `codex-code-mode-host` 等现代组件。
- **保留用户数据**：`~/.codex` 与程序版本分离，切换和升级不会清空用户配置。
- **适合不稳定网络**：大文件支持断点续传、自动重试和 SHA-256 校验。
- **自动处理部分 GitHub API 限流场景**：如果 GitHub 明确返回 API quota 耗尽，工具会仅针对该元数据请求尝试一次绕过代理直连，不改变后续大文件下载的网络配置。

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
codex-tool clean [--yes]          清理 Codex 数据，但保留 config.toml 和 auth.json
codex-tool prune [--yes] [--force]
                                  删除所有受管理的 Codex 版本、下载缓存和 codex 命令链接
codex-tool version                查看 codex-tool 版本
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

## 文档

- [完整使用手册](USAGE.md)
- [版本迭代历史](CHANGELOG.md)
- [English README](../README.md)
- [MIT License](../LICENSE)

## License

MIT，详见 [LICENSE](../LICENSE)。
