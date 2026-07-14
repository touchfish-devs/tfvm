#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import yaml
import shutil
import tarfile
import tempfile
import subprocess
import logging
import time
from pathlib import Path
import requests

# ---------- 颜色支持 ----------
COLORS = {
    'RED': '\033[91m',
    'GREEN': '\033[92m',
    'YELLOW': '\033[93m',
    'BLUE': '\033[94m',
    'MAGENTA': '\033[95m',
    'CYAN': '\033[96m',
    'RESET': '\033[0m'
}

def colorize(text, color):
    return f"{COLORS.get(color, '')}{text}{COLORS['RESET']}"

# ---------- 进度条支持 ----------
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    class tqdm_dummy:
        def __init__(self, iterable=None, total=None, desc=None, unit=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.unit = unit
            self.n = 0
            self.start_time = time.time()
        def __iter__(self):
            if self.iterable:
                for item in self.iterable:
                    yield item
                    self.n += 1
                    self._update()
        def update(self, n=1):
            self.n += n
            self._update()
        def _update(self):
            if self.total:
                percent = 100 * self.n / self.total
                sys.stdout.write(f"\r{self.desc or ''} {percent:.1f}% [{self.n}/{self.total}] {self.unit or ''}")
                sys.stdout.flush()
        def close(self):
            sys.stdout.write("\n")
            sys.stdout.flush()
    tqdm = tqdm_dummy

# ---------- 日志配置（带颜色） ----------
class ColorFormatter(logging.Formatter):
    def format(self, record):
        levelname = record.levelname
        if levelname == 'ERROR':
            record.msg = colorize(record.msg, 'RED')
        elif levelname == 'WARNING':
            record.msg = colorize(record.msg, 'YELLOW')
        elif levelname == 'INFO':
            record.msg = colorize(record.msg, 'CYAN')
        return super().format(record)

handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter('%(levelname)s: %(message)s'))
logger = logging.getLogger('tfvm')
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ---------- 常量 ----------
VERSION = "1.3.1"  # 自更新版本

DEFAULT_CONFIG = {
    "registry": "https://reg.touchfish.us.ci/db.yml",
    "sudo_at_start": False,
    "install_prefix": "/usr/local",
    "install_root": "/opt/tfvm",
    "cache_dir": "~/.tfvm/cache",
    "db_file": "~/.tfvm/db.yml",
    "installed_db": "~/.tfvm/installed.json"
}

# ---------- 辅助函数 ----------
def expand_path(path: str) -> str:
    if path is None:
        return None
    return os.path.abspath(os.path.expanduser(path))

def ensure_dir(path: str):
    if path:
        Path(path).mkdir(parents=True, exist_ok=True)

def run_sudo(cmd: list):
    try:
        subprocess.run(['sudo'] + cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def is_root() -> bool:
    return os.geteuid() == 0

# ---------- 配置管理 ----------
class Config:
    def __init__(self):
        self.config_path = expand_path("~/tfvm.json")
        self.data = self.load()
        self._expand_paths()

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = value
            return data
        else:
            logger.info(f"首次启动，创建默认配置文件 {self.config_path}")
            self.data = DEFAULT_CONFIG.copy()
            self.save()
            return self.data

    def save(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def _expand_paths(self):
        for key in ['cache_dir', 'db_file', 'installed_db', 'install_prefix', 'install_root']:
            if key in self.data and self.data[key]:
                self.data[key] = expand_path(self.data[key])
        ensure_dir(os.path.dirname(self.data['db_file']))
        ensure_dir(os.path.dirname(self.data['installed_db']))
        ensure_dir(self.data['cache_dir'])

    def get(self, key, default=None):
        return self.data.get(key, default)

# ---------- 包数据库 ----------
class PackageDB:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.get('db_file')
        self.packages = {}
        self.load()

    def load(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r') as f:
                self.packages = yaml.safe_load(f) or {}
        else:
            self.packages = {}

    def save(self):
        with open(self.db_path, 'w') as f:
            yaml.dump(self.packages, f)

    def sync(self):
        url = self.config.get('registry')
        logger.info(f"正在同步软件包数据库: {url}")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = yaml.safe_load(resp.text)
            if not data:
                raise ValueError("数据库为空")
            self.packages = data
        except Exception as e:
            logger.error(f"同步数据库失败: {e}")
            sys.exit(1)

        # 确保 tfvm 自身包存在
        if 'tfvm' not in self.packages:
            self.packages['tfvm'] = {
                'Name': 'tfvm',
                'Comment': 'TouchFish Version Manager',
                'Version': VERSION,
                'Release': 1,
                'Registry': 'https://github.com/touchfish-devs/tfvm/archive/refs/tags/v$version$.tar.gz',
                'Exec': 'main.py',
                'Binary': ['main.py']
            }
            logger.info(colorize("已添加默认 tfvm 包到数据库", 'YELLOW'))

        self.save()
        logger.info(colorize(f"数据库同步完成，共 {len(self.packages)} 个软件包", 'GREEN'))

    def get_pkg(self, name: str):
        return self.packages.get(name)

    def list_pkgs(self):
        return self.packages.keys()

# ---------- 已安装包管理 ----------
class InstalledDB:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.get('installed_db')
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def save(self):
        with open(self.db_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def is_installed(self, name: str) -> bool:
        return name in self.data

    def get_installed_version(self, name: str):
        return self.data.get(name, {}).get('version')

    def add_pkg(self, name: str, version: str, install_dir: str, symlink_path: str):
        self.data[name] = {
            'version': version,
            'install_dir': install_dir,
            'symlink': symlink_path
        }
        self.save()

    def remove_pkg(self, name: str):
        if name in self.data:
            del self.data[name]
            self.save()

    def get_all(self):
        return self.data

# ---------- 核心包管理器 ----------
class TfvmManager:
    def __init__(self):
        self.config = Config()
        self.db = PackageDB(self.config)
        self.installed = InstalledDB(self.config)

        self.bin_dir = os.path.join(self.config.get('install_prefix'), 'bin')
        ensure_dir(self.bin_dir)

        self.cache_dir = self.config.get('cache_dir')
        ensure_dir(self.cache_dir)

        self.install_root = self.config.get('install_root')
        self.upgraded_tfvm = False  # 标记是否升级了自身

    def _check_sudo_requirement(self):
        if self.config.get('sudo_at_start', False):
            if not is_root():
                logger.error("配置要求以 sudo 运行，请使用 sudo tfvm ...")
                sys.exit(1)

    def _download_file(self, url: str, dest: str):
        logger.info(f"下载: {url}")
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total_size = int(resp.headers.get('content-length', 0))
            desc = os.path.basename(dest)
            with open(dest, 'wb') as f:
                if total_size == 0:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                    logger.info(f"下载完成: {dest}")
                    return

                with tqdm(total=total_size, unit='B', unit_scale=True,
                          desc=desc, ncols=80, file=sys.stdout) as pbar:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
                    pbar.close()
            logger.info(f"下载完成: {dest}")
        except Exception as e:
            logger.error(f"下载失败: {e}")
            sys.exit(1)

    def _extract_archive(self, archive_path: str, dest_dir: str):
        logger.info(f"解压: {archive_path} -> {dest_dir}")
        base = os.path.basename(archive_path)
        ext = os.path.splitext(archive_path)[1].lower()

        # AppImage 特殊处理
        if base.lower().endswith('.appimage'):
            shutil.copy2(archive_path, dest_dir)
            dest_file = os.path.join(dest_dir, os.path.basename(archive_path))
            os.chmod(dest_file, 0o755)
            return

        try:
            if ext in ('.gz', '.tgz') and archive_path.endswith(('.tar.gz', '.tgz')):
                subprocess.run(['tar', '-xzf', archive_path, '-C', dest_dir], check=True)
            elif ext in ('.xz', '.txz') and archive_path.endswith(('.tar.xz', '.txz')):
                subprocess.run(['tar', '-xJf', archive_path, '-C', dest_dir], check=True)
            elif ext == '.zst':
                if archive_path.endswith('.tar.zst'):
                    subprocess.run(['tar', '--zstd', '-xf', archive_path, '-C', dest_dir], check=True)
                else:
                    out_name = os.path.basename(archive_path)[:-4]
                    subprocess.run(['zstd', '-d', archive_path, '-o', os.path.join(dest_dir, out_name)], check=True)
            elif ext == '.zip':
                subprocess.run(['unzip', '-q', archive_path, '-d', dest_dir], check=True)
            else:
                subprocess.run(['tar', '-xf', archive_path, '-C', dest_dir], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"解压失败: {e}")
            sys.exit(1)
        except FileNotFoundError as e:
            logger.error(f"缺少必要的解压工具: {e}")
            sys.exit(1)

    def _check_path_conflict(self, pkg_name: str):
        import shutil
        existing_path = shutil.which(pkg_name)
        if existing_path is None:
            return 'none', ''

        target_path = os.path.join(self.bin_dir, pkg_name)
        if existing_path == target_path:
            return 'conflict', f"路径 {target_path} 已被占用，与 tfvm 安装位置冲突。"

        path_list = os.environ.get('PATH', '').split(os.pathsep)
        try:
            local_idx = path_list.index(self.bin_dir)
        except ValueError:
            return 'none', ''

        dirname = os.path.dirname(existing_path)
        try:
            ext_idx = path_list.index(dirname)
        except ValueError:
            return 'none', ''

        if ext_idx < local_idx:
            return 'occupied_ahead', f"外部包 {existing_path} 在 PATH 中优先于 {self.bin_dir}，建议卸载外部包。"
        elif ext_idx > local_idx:
            return 'occupied_behind', f"外部包 {existing_path} 在 PATH 中位于 {self.bin_dir} 之后，tfvm 将覆盖该命令。"
        else:
            return 'none', ''

    def _resolve_dependencies(self, pkg_name: str, pkg_info: dict, visited: set):
        if pkg_name in visited:
            return []
        visited.add(pkg_name)

        deps = pkg_info.get('Depends', [])
        result = []
        for dep in deps:
            dep_info = self.db.get_pkg(dep)
            if not dep_info:
                logger.error(f"依赖包 {dep} 不存在于数据库中")
                sys.exit(1)
            sub = self._resolve_dependencies(dep, dep_info, visited)
            result.extend(sub)
            result.append(dep)
        return result

    def _install_pkg(self, pkg_name: str, pkg_info: dict):
        if self.installed.is_installed(pkg_name):
            current_version = self.installed.get_installed_version(pkg_name)
            new_version = pkg_info.get('Version')
            if current_version == new_version:
                logger.info(f"包 {pkg_name} 已是最新版本 {current_version}")
                return
            else:
                logger.info(f"升级包 {pkg_name}: {current_version} -> {new_version}")
                info = self.installed.data.get(pkg_name, {})
                symlink = info.get('symlink')
                install_dir = info.get('install_dir')
                if symlink and os.path.islink(symlink):
                    if not run_sudo(['rm', '-f', symlink]):
                        logger.error(f"删除旧符号链接失败: {symlink}")
                        sys.exit(1)
                    logger.info(f"已删除旧符号链接: {symlink}")
                if install_dir and os.path.exists(install_dir):
                    if not run_sudo(['rm', '-rf', install_dir]):
                        logger.error(f"删除旧安装目录失败: {install_dir}")
                        sys.exit(1)
                    logger.info(f"已删除旧安装目录: {install_dir}")
                self.installed.remove_pkg(pkg_name)

        # 检查路径冲突
        status, msg = self._check_path_conflict(pkg_name)
        if status == 'conflict':
            logger.error(f"包 {pkg_name}: {msg}")
            sys.exit(1)
        elif status in ('occupied_ahead', 'occupied_behind'):
            logger.warning(f"包 {pkg_name}: {msg}")

        version = pkg_info.get('Version')
        if not version:
            logger.error(f"包 {pkg_name} 没有 Version 字段")
            sys.exit(1)
        registry_template = pkg_info.get('Registry')
        if not registry_template:
            logger.error(f"包 {pkg_name} 没有 Registry 字段")
            sys.exit(1)
        download_url = registry_template.replace('$version$', version)

        url_filename = os.path.basename(download_url.split('?')[0])
        cache_path = os.path.join(self.cache_dir, url_filename)
        if not os.path.exists(cache_path):
            self._download_file(download_url, cache_path)
        else:
            logger.info(f"使用缓存: {cache_path}")

        with tempfile.TemporaryDirectory(prefix='tfvm_') as tmpdir:
            is_appimage = cache_path.lower().endswith('.appimage')
            if is_appimage:
                target_dir = os.path.join(self.install_root, pkg_name)
                if os.path.exists(target_dir):
                    if not run_sudo(['rm', '-rf', target_dir]):
                        logger.error(f"删除旧目录失败: {target_dir}")
                        sys.exit(1)
                if not run_sudo(['mkdir', '-p', self.install_root]):
                    logger.error(f"无法创建安装根目录: {self.install_root}")
                    sys.exit(1)
                if not run_sudo(['mkdir', '-p', target_dir]):
                    logger.error(f"无法创建目标目录: {target_dir}")
                    sys.exit(1)
                dest_file = os.path.join(target_dir, os.path.basename(cache_path))
                if not run_sudo(['cp', cache_path, dest_file]):
                    logger.error(f"复制 AppImage 失败")
                    sys.exit(1)
                if not run_sudo(['chmod', '+x', dest_file]):
                    logger.warning(f"设置可执行权限失败: {dest_file}")

                exec_target = pkg_info.get('Exec')
                if exec_target:
                    exec_target = os.path.join(target_dir, exec_target)
                else:
                    exec_target = dest_file
                symlink_path = os.path.join(self.bin_dir, pkg_name)
                if os.path.islink(symlink_path) or os.path.exists(symlink_path):
                    if not run_sudo(['rm', '-f', symlink_path]):
                        logger.error(f"无法删除旧符号链接: {symlink_path}")
                        sys.exit(1)
                if not run_sudo(['ln', '-sf', exec_target, symlink_path]):
                    logger.error(f"创建符号链接失败: {symlink_path} -> {exec_target}")
                    sys.exit(1)
                logger.info(f"已创建符号链接: {symlink_path}")

                self.installed.add_pkg(pkg_name, version, target_dir, symlink_path)
                if pkg_name == 'tfvm':
                    self.upgraded_tfvm = True
                logger.info(colorize(f"包 {pkg_name} 安装完成", 'GREEN'))
                return

            self._extract_archive(cache_path, tmpdir)
            extracted_root = tmpdir
            items = os.listdir(tmpdir)
            if len(items) == 1 and os.path.isdir(os.path.join(tmpdir, items[0])):
                extracted_root = os.path.join(tmpdir, items[0])

            target_dir = os.path.join(self.install_root, pkg_name)
            if os.path.exists(target_dir):
                if not run_sudo(['rm', '-rf', target_dir]):
                    logger.error(f"删除旧目录失败: {target_dir}")
                    sys.exit(1)

            if not run_sudo(['mkdir', '-p', self.install_root]):
                logger.error(f"无法创建安装根目录: {self.install_root}")
                sys.exit(1)
            if not run_sudo(['mkdir', '-p', target_dir]):
                logger.error(f"无法创建目标目录: {target_dir}")
                sys.exit(1)
            if not run_sudo(['cp', '-rT', extracted_root, target_dir]):
                logger.error(f"复制文件到 {target_dir} 失败")
                sys.exit(1)

            binary_list = pkg_info.get('Binary', [])
            for rel_path in binary_list:
                bin_file = os.path.join(target_dir, rel_path)
                if not os.path.exists(bin_file):
                    logger.warning(f"Binary 文件不存在: {bin_file}，跳过")
                    continue
                if not run_sudo(['chmod', '+x', bin_file]):
                    logger.warning(f"设置可执行权限失败: {bin_file}")

            exec_rel = pkg_info.get('Exec')
            if not exec_rel:
                logger.warning(f"包 {pkg_name} 没有 Exec 字段，不创建符号链接")
            else:
                exec_target = os.path.join(target_dir, exec_rel)
                if not os.path.exists(exec_target):
                    logger.error(f"Exec 文件不存在: {exec_target}")
                    logger.error("请检查数据库中的 Exec 字段是否指向包内正确的可执行文件路径")
                    sys.exit(1)
                symlink_path = os.path.join(self.bin_dir, pkg_name)
                if os.path.islink(symlink_path) or os.path.exists(symlink_path):
                    if not run_sudo(['rm', '-f', symlink_path]):
                        logger.error(f"无法删除旧符号链接: {symlink_path}")
                        sys.exit(1)
                if not run_sudo(['ln', '-sf', exec_target, symlink_path]):
                    logger.error(f"创建符号链接失败: {symlink_path} -> {exec_target}")
                    sys.exit(1)
                logger.info(f"已创建符号链接: {symlink_path}")

            self.installed.add_pkg(pkg_name, version, target_dir, symlink_path)
            if pkg_name == 'tfvm':
                self.upgraded_tfvm = True
            logger.info(colorize(f"包 {pkg_name} 安装完成", 'GREEN'))

    def install(self, pkg_names: list, clean_cache: bool = False, refresh: bool = False):
        self._check_sudo_requirement()
        if refresh:
            self.db.sync()

        if clean_cache:
            self.clean_cache()

        all_pkgs = []
        visited = set()
        for name in pkg_names:
            pkg_info = self.db.get_pkg(name)
            if not pkg_info:
                logger.error(f"包 {name} 不存在于数据库")
                sys.exit(1)
            deps = self._resolve_dependencies(name, pkg_info, visited)
            all_pkgs.extend(deps)
            all_pkgs.append(name)
        all_pkgs = list(dict.fromkeys(all_pkgs))

        if not all_pkgs:
            logger.info("没有需要处理的新包或更新包")
            return

        # 冲突检查汇总
        conflicts = []
        warnings = []
        for pkg in all_pkgs:
            status, msg = self._check_path_conflict(pkg)
            if status == 'conflict':
                conflicts.append((pkg, msg))
            elif status in ('occupied_ahead', 'occupied_behind'):
                warnings.append((pkg, msg))

        if conflicts:
            logger.error("以下包与现有文件冲突，无法安装：")
            for pkg, msg in conflicts:
                logger.error(f"  {pkg}: {msg}")
            sys.exit(1)
        if warnings:
            logger.warning("以下包存在路径冲突，建议处理：")
            for pkg, msg in warnings:
                logger.warning(f"  {pkg}: {msg}")

        logger.info(f"将处理以下包: {', '.join(all_pkgs)}")
        confirm = input(colorize("确认继续吗？(Y/n): ", 'YELLOW')).strip().lower()
        if confirm and confirm != 'y':
            logger.info("操作取消")
            return

        for pkg in all_pkgs:
            pkg_info = self.db.get_pkg(pkg)
            if not pkg_info:
                logger.error(f"包 {pkg} 不存在")
                continue
            self._install_pkg(pkg, pkg_info)

    def upgrade(self, pkg_names=None, refresh=False):
        if pkg_names is None:
            installed = self.installed.get_all()
            pkg_names = list(installed.keys())
        self.install(pkg_names, clean_cache=False, refresh=refresh)

    def remove(self, pkg_names: list):
        self._check_sudo_requirement()
        for name in pkg_names:
            if not self.installed.is_installed(name):
                logger.warning(f"包 {name} 未安装")
                continue
            info = self.installed.data.get(name, {})
            symlink = info.get('symlink')
            install_dir = info.get('install_dir')
            if symlink and os.path.islink(symlink):
                if not run_sudo(['rm', '-f', symlink]):
                    logger.error(f"删除符号链接失败: {symlink}")
                    sys.exit(1)
                logger.info(f"已删除符号链接: {symlink}")
            if install_dir and os.path.exists(install_dir):
                if not run_sudo(['rm', '-rf', install_dir]):
                    logger.error(f"删除安装目录失败: {install_dir}")
                    sys.exit(1)
                logger.info(f"已删除安装目录: {install_dir}")
            self.installed.remove_pkg(name)
            logger.info(colorize(f"包 {name} 已卸载", 'GREEN'))

    def query(self, pkg_name=None):
        if pkg_name:
            info = self.db.get_pkg(pkg_name)
            if not info:
                logger.error(f"包 {pkg_name} 不存在")
                return
            installed = self.installed.is_installed(pkg_name)
            status = colorize("已安装", 'GREEN') if installed else colorize("未安装", 'RED')
            print(f"名称: {pkg_name}")
            print(f"全名: {info.get('Name', '')}")
            print(f"说明: {info.get('Comment', '')}")
            print(f"版本: {info.get('Version', '')}")
            print(f"发布号: {info.get('Release', '')}")
            print(f"状态: {status}")
            if installed:
                inst_info = self.installed.data.get(pkg_name, {})
                print(f"安装目录: {inst_info.get('install_dir', '')}")
                print(f"符号链接: {inst_info.get('symlink', '')}")
        else:
            for name in sorted(self.db.list_pkgs()):
                info = self.db.get_pkg(name)
                installed = self.installed.is_installed(name)
                status = colorize("已安装", 'GREEN') if installed else colorize("未安装", 'RED')
                print(f"{name} {info.get('Version', '')} - {info.get('Name', '')} [{status}]")

    def sync_db(self):
        self.db.sync()

    def clean_cache(self):
        cache_dir = self.cache_dir
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            ensure_dir(cache_dir)
            logger.info("缓存已清理")

    def launch(self, pkg_name):
        if not self.installed.is_installed(pkg_name):
            logger.error(f"包 {pkg_name} 未安装")
            sys.exit(1)
        exec_path = os.path.join(self.bin_dir, pkg_name)
        if not os.path.exists(exec_path) or not os.access(exec_path, os.X_OK):
            logger.error(f"可执行文件不存在或不可执行: {exec_path}")
            sys.exit(1)
        os.execv(exec_path, [exec_path] + sys.argv[2:])

# ---------- 命令行解析 ----------
def print_help():
    help_text = f"""
{colorize('TouchFish Version Manager (tfvm) v' + VERSION, 'CYAN')}
Usage:
  tfvm <pkg>               启动已安装的包
  tfvm -S <pkg> [pkg...]   安装或升级包及其依赖（自动更新依赖）
  tfvm -R <pkg> [pkg...]   卸载一个或多个包
  tfvm -Q [pkg]            查询包信息
  tfvm -Sy                 同步数据库
  tfvm -Su [pkg...]        升级指定包（不指定则升级所有）
  tfvm -Sc                 清理缓存
  tfvm -Syu                同步数据库并升级所有包
  tfvm -Scc                清理缓存（同 -Sc）
  tfvm -v                  版本号
  tfvm -h                  帮助

修饰符（与 -S 组合）：
  -y    同步数据库
  -c    安装前清理缓存
  -u    升级模式
"""
    print(help_text)

def parse_args():
    raw = sys.argv[1:]
    if not raw:
        print_help()
        sys.exit(0)

    expanded = []
    for arg in raw:
        if arg.startswith('--'):
            expanded.append(arg)
        elif arg.startswith('-') and len(arg) > 1:
            for ch in arg[1:]:
                expanded.append('-' + ch)
        else:
            expanded.append(arg)

    op = None
    pkg_names = []
    refresh = False
    clean_cache = False
    version_flag = False
    help_flag = False

    i = 0
    while i < len(expanded):
        arg = expanded[i]
        if arg in ('-v', '--version'):
            version_flag = True
            break
        elif arg in ('-h', '--help'):
            help_flag = True
            break
        elif arg == '-S':
            op = 'install'
            i += 1
            pkgs = []
            while i < len(expanded) and not expanded[i].startswith('-'):
                pkgs.append(expanded[i])
                i += 1
            pkg_names = pkgs
            continue
        elif arg == '-R':
            op = 'remove'
            i += 1
            pkgs = []
            while i < len(expanded) and not expanded[i].startswith('-'):
                pkgs.append(expanded[i])
                i += 1
            pkg_names = pkgs
            continue
        elif arg == '-Q':
            op = 'query'
            i += 1
            if i < len(expanded) and not expanded[i].startswith('-'):
                pkg_names = [expanded[i]]
                i += 1
            else:
                pkg_names = []
            continue
        elif arg == '-y':
            refresh = True
            i += 1
            continue
        elif arg == '-c':
            clean_cache = True
            i += 1
            continue
        elif arg == '-u':
            if op == 'install':
                op = 'upgrade'
            elif op is None:
                op = 'upgrade'
                pkg_names = []
            i += 1
            continue
        else:
            if op is None and not arg.startswith('-'):
                op = 'launch'
                pkg_names = [arg]
                i += 1
                break
            else:
                logger.error(f"未知选项: {arg}")
                sys.exit(1)

    if op == 'install' and clean_cache and not pkg_names:
        op = 'clean'
        clean_cache = False

    if op == 'install' and refresh and not pkg_names:
        op = 'sync'

    if version_flag:
        print(VERSION)
        sys.exit(0)
    if help_flag:
        print_help()
        sys.exit(0)

    if op is None and pkg_names:
        op = 'launch'

    return {
        'op': op,
        'pkg_names': pkg_names,
        'refresh': refresh,
        'clean_cache': clean_cache
    }

# ---------- 主函数 ----------
def main():
    args = parse_args()
    op = args['op']
    pkg_names = args['pkg_names']
    refresh = args['refresh']
    clean_cache = args['clean_cache']

    if not op:
        print_help()
        sys.exit(0)

    manager = TfvmManager()

    if op == 'install':
        manager.install(pkg_names, clean_cache=clean_cache, refresh=refresh)
    elif op == 'remove':
        if not pkg_names:
            logger.error("未指定要卸载的包")
            sys.exit(1)
        manager.remove(pkg_names)
    elif op == 'query':
        if pkg_names:
            manager.query(pkg_names[0])
        else:
            manager.query()
    elif op == 'sync':
        manager.sync_db()
    elif op == 'upgrade':
        manager.upgrade(pkg_names if pkg_names else None, refresh=refresh)
    elif op == 'clean':
        manager.clean_cache()
    elif op == 'launch':
        if not pkg_names:
            logger.error("未指定要启动的包")
            sys.exit(1)
        manager.launch(pkg_names[0])
    else:
        logger.error(f"未知操作: {op}")
        sys.exit(1)

    # 如果升级了 tfvm 自身，提示用户重新运行
    if manager.upgraded_tfvm:
        logger.info(colorize("tfvm 已升级到最新版本，请重新运行命令以应用更新。", 'YELLOW'))

if __name__ == "__main__":
    main()
