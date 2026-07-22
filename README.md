# tfvm - TouchFish Version Manager

[![版本](https://img.shields.io/badge/version-1.3.2-blue)](https://github.com/touchfish-devs/tfvm)
[![许可](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.6%2B-blue)](https://www.python.org/)

`tfvm` 是 TouchFish 系列软件的轻量级包管理器，灵感来源于 `pacman`，支持多格式软件包、自动依赖解析、自我更新和灵活的安装策略。

---

## 功能特性

- **Pacman‑风格命令行** – 熟悉的 `-S`、`-R`、`-Q` 操作和丰富的选项（`-y`、`-u`、`-c`、`-i`、`-s`、`-l` 等）。
- **多格式支持** – 自动识别并安装 `.tar.gz`、`.tar.xz`、`.zst`、`.zip`、`.AppImage` 等多种归档/可执行格式。
- **智能依赖管理** – 递归解析依赖，按拓扑顺序安装，确保依赖始终为最新版本。
- **路径冲突检查** – 安装前检测系统中同名命令，根据 PATH 顺序给出警告或阻止安装。
- **自我更新** – `tfvm` 可管理自身，通过 `-Syu` 一键升级，安装脚本自动自举。
- **跨发行版安装** – 支持 Debian/Ubuntu、Arch、Fedora/RHEL，自动安装系统依赖。
- **彩色输出与进度条** – 清晰的日志分级和下载进度显示（支持 `tqdm`）。

---

## 📥 安装

```bash
# 克隆仓库
git clone https://github.com/touchfish-devs/tfvm.git
cd tfvm

# 安装 Python 依赖（如未安装）
pip3 install --user requests pyyaml tqdm   # 或使用系统包管理器

# 使用临时脚本安装 tfvm 自身
python3 main.py -S tfvm
```

执行 `-S tfvm` 会：
- 同步远程数据库。
- 下载 `tfvm` 源码包并安装到 `/opt/tfvm/tfvm`。
- 创建 `/usr/local/bin/tfvm` 符号链接。

安装完成后，即可在任意位置使用 `tfvm` 命令。

---

## 🚀 使用方法

基本语法：
```bash
tfvm <操作> [选项] [目标]
```

### 操作（必须指定其一）

| 操作 | 说明 |
|------|------|
| `-Q, --query` | 查询本地数据库（已安装包信息） |
| `-R, --remove` | 移除软件包 |
| `-S, --sync`   | 同步/安装软件包（可从远程仓库安装或升级） |

### 常用命令示例

#### 安装/升级包
```bash
# 安装或升级 touchfish（若已安装则升级，否则安装）
tfvm -S touchfish

# 同步数据库并升级所有已安装包
tfvm -Syu

# 仅升级 touchfish（若未安装则报错）
tfvm -S -u touchfish
```

#### 查询操作
```bash
# 列出所有已安装包
tfvm -Q

# 显示 touchfish 的详细信息
tfvm -Qi touchfish

# 搜索已安装包中包含 "fish" 的
tfvm -Qs "fish"

# 列出可更新的包
tfvm -Qu

# 列出 touchfish 安装的所有文件
tfvm -Ql touchfish
```

#### 移除操作
```bash
# 卸载 touchfish
tfvm -R touchfish

# 级联删除（卸载 touchfish 及依赖它的包）
tfvm -Rc touchfish
```

#### 其他
```bash
# 清理缓存（删除未安装的包）
tfvm -Sc

# 清空整个缓存
tfvm -Scc

# 启动已安装的包（等同于直接执行命令）
tfvm touchfish
```

### 完整的参数支持

| 操作 | 选项 | 说明 |
|------|------|------|
| **-Q** | `-i` | 显示包的详细信息 |
| | `-s <表达式>` | 搜索已安装的包（支持正则） |
| | `-l` | 列出包安装的所有文件 |
| | `-u` | 列出所有可更新的包 |
| | `-q` | 精简输出 |
| **-R** | `-c` | 级联删除（移除目标包及依赖它们的包） |
| | `-s` | 递归删除（移除不被需要的依赖） |
| | `-n` | 移除时不保留配置文件（默认保留为 .pacsave） |
| | `-u` | 移除不被需要的目标包 |
| **-S** | `-y` | 刷新同步数据库 |
| | `-c` | 清理缓存（一次删除未安装包，两次清空全部） |
| | `-u` | 升级模式（仅升级已安装包，未安装则报错） |
| | `-i` | 显示远程仓库包的详细信息（目前未实现） |
| | `-s` | 在远程仓库中搜索包（目前未实现） |
| | `-q` | 精简输出 |

> 长选项（如 `--sync`、`--query`、`--refresh`、`--sysupgrade`、`--clean` 等）同样支持。

---

## ⚙️ 配置文件

首次运行自动生成 `~/tfvm.json`，可手动编辑：

```json
{
  "registry": "https://reg.touchfish.us.ci/db.yml",
  "sudo_at_start": false,
  "install_prefix": "/usr/local",
  "install_root": "/opt/tfvm",
  "cache_dir": "~/.tfvm/cache",
  "db_file": "~/.tfvm/db.yml",
  "installed_db": "~/.tfvm/installed.json"
}
```

- `registry` – 远程软件包数据库 URL。
- `sudo_at_start` – 若为 `true`，所有操作必须用 `sudo` 执行。
- `install_prefix` – 符号链接安装目录（默认为 `/usr/local/bin`）。
- `install_root` – 包实际安装根目录（默认为 `/opt/tfvm`）。
- `cache_dir` – 下载缓存目录。
- `db_file` – 本地数据库文件路径。
- `installed_db` – 已安装包信息记录文件。

---

## 📦 包数据库格式

远程数据库（YAML）示例：

```yaml
touchfish:
  Name: TouchFish
  Comment: "FOSS multi-distribution LAN chatting tool"
  Version: 4.8.0
  Release: 2
  Registry: "https://github.com/touchfish-devs/TouchFish-AUR/archive/refs/tags/v$version$.tar.gz"
  Exec: LTS.py
  Binary:
    - LTS.py
  Depends:
    - tfvm
```

- `Name` – 包全名（显示用）。
- `Comment` – 简短描述。
- `Version` – 版本号。
- `Release` – 发布号（整数）。
- `Registry` – 下载 URL，可用 `$version$` 占位符。
- `Exec` – 相对于包根目录的可执行文件路径。
- `Binary` – 需要设置可执行权限的文件列表（相对于包根目录）。
- `Depends` – 依赖的包名列表（可选）。

---

## 🔧 开发与贡献

### 目录结构
```
tfvm/
├── main.py          # 主程序
├── README.md        # 本文件
└── ...
```

### 测试
```bash
# 直接运行（无需安装）
python3 main.py -h
```

### 贡献
欢迎提交 Issue 和 PR。请确保代码风格符合 PEP 8，并添加必要的文档。

---

## 📝 更新日志

### v1.3.2 (2026-07-15)
- **参数体系重构** – 完全遵循 Pacman 风格，仅保留 `-Q`、`-R`、`-S` 操作，增加多项选项支持（`-y`、`-u`、`-c`、`-i`、`-s`、`-l`、`-q` 等）。
- **多格式支持** – 新增 `.zip`、`.tar.xz`、`.zst`、`.AppImage` 安装支持，自动识别并调用相应工具（`unzip`、`zstd`、`tar`）。
- **两阶段安装** – 安装过程分为“全部下载”和“统一安装”两步，提升可靠性。
- **路径冲突检查** – 安装前检测 `/usr/local/bin` 下同名文件，根据 PATH 优先级给出警告或阻止安装。
- **自举安装** – 新增 `install.sh` 脚本，支持 Debian/Arch/Fedora 发行版，自动安装系统依赖并完成自举。
- **依赖管理优化** – 解析依赖时强制升级所有依赖包至最新版本，确保依赖兼容性。
- **Bug 修复** – 修复升级自身时的迭代错误和冲突检查误报问题。
- **帮助信息** – 更新为 Pacman 风格帮助文档。

### v1.3.1 (2026-07-14)
- 修复自身升级时的冲突检查误判问题。
- 改进错误提示信息。

### v1.3.0 (2026-07-13)
- 初始版本，支持基本安装、卸载、查询，依赖管理，彩色输出和进度条。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE)。

---

## 🤝 相关链接

- [TouchFish 项目主页](https://touchfish.us.ci)
- [软件包数据库](https://reg.touchfish.us.ci/db.yml)
- [GitHub 仓库](https://github.com/touchfish-devs/tfvm)
