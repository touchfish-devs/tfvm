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
import re

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
VERSION = "1.3.2"

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
        self.upgraded_tfvm = False

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
        if self.installed.is_installed(pkg_name):
            return 'none', ''

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

    def _install_pkg(self, pkg_name: str, pkg_info: dict, skip_download=False):
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

        if not skip_download:
            if not os.path.exists(cache_path):
                self._download_file(download_url, cache_path)
            else:
                logger.info(f"使用缓存: {cache_path}")
        else:
            if not os.path.exists(cache_path):
                logger.error(f"缓存文件缺失: {cache_path}，请先执行下载阶段")
                sys.exit(1)

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

        logger.info(colorize("阶段 1/2: 下载所有包文件...", 'BLUE'))
        for pkg in all_pkgs:
            pkg_info = self.db.get_pkg(pkg)
            if not pkg_info:
                logger.error(f"包 {pkg} 不存在")
                continue
            version = pkg_info.get('Version')
            registry_template = pkg_info.get('Registry')
            if not version or not registry_template:
                logger.warning(f"包 {pkg} 缺少版本或 Registry，跳过")
                continue
            download_url = registry_template.replace('$version$', version)
            url_filename = os.path.basename(download_url.split('?')[0])
            cache_path = os.path.join(self.cache_dir, url_filename)
            if not os.path.exists(cache_path):
                self._download_file(download_url, cache_path)
            else:
                logger.info(f"使用缓存: {cache_path}")
        logger.info(colorize("所有包下载完成。", 'GREEN'))

        logger.info(colorize("阶段 2/2: 安装/升级所有包...", 'BLUE'))
        for pkg in all_pkgs:
            pkg_info = self.db.get_pkg(pkg)
            if not pkg_info:
                logger.error(f"包 {pkg} 不存在")
                continue
            self._install_pkg(pkg, pkg_info, skip_download=True)

    def upgrade(self, pkg_names=None, refresh=False, clean_cache=False):
        """
        仅升级已安装的包。若 pkg_names 为 None 或空，则升级所有已安装包。
        若指定包名但未安装，则报错。
        """
        self._check_sudo_requirement()
        if refresh:
            self.db.sync()
        if clean_cache:
            self.clean_cache()

        if pkg_names is None:
            pkg_names = list(self.installed.get_all().keys())
            if not pkg_names:
                logger.info("没有已安装的包")
                return
        else:
            for name in pkg_names:
                if not self.installed.is_installed(name):
                    logger.error(f"包 {name} 未安装，无法升级")
                    sys.exit(1)

        self.install(pkg_names, clean_cache=False, refresh=False)

    def remove(self, pkg_names: list, cascade=False, recursive=False):
        self._check_sudo_requirement()
        # 若 cascade 或 recursive，需处理依赖关系（简化实现：直接卸载，并提示依赖）
        if cascade:
            logger.warning("级联删除功能暂未完全实现，将只卸载目标包及其直接依赖（如果有）")
        if recursive:
            logger.warning("递归删除功能暂未完全实现，将只卸载目标包本身")

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

    def query(self, pkg_name=None, info=False, search=None, list_files=False, upgrades=False, quiet=False):
        if upgrades:
            # 列出可更新的包
            upgradable = []
            for name, inst in self.installed.get_all().items():
                pkg_info = self.db.get_pkg(name)
                if pkg_info:
                    cur_ver = inst.get('version')
                    new_ver = pkg_info.get('Version')
                    if cur_ver != new_ver:
                        upgradable.append((name, cur_ver, new_ver))
            if not upgradable:
                logger.info("所有已安装包都是最新的。")
            else:
                print("可更新的包：")
                for name, cur, new in upgradable:
                    print(f"{name} {cur} -> {new}")
            return

        if search:
            # 搜索已安装包（支持正则）
            pattern = re.compile(search, re.IGNORECASE)
            found = []
            for name, pkg_info in self.db.packages.items():
                if pattern.search(name) or pattern.search(pkg_info.get('Name', '')):
                    installed = self.installed.is_installed(name)
                    found.append((name, pkg_info, installed))
            if not found:
                logger.info("未找到匹配的包。")
            else:
                for name, info, installed in found:
                    status = colorize("已安装", 'GREEN') if installed else colorize("未安装", 'RED')
                    if quiet:
                        print(name)
                    else:
                        print(f"{name} {info.get('Version', '')} - {info.get('Name', '')} [{status}]")
            return

        if list_files:
            if not pkg_name:
                logger.error("列出文件需要指定包名")
                return
            if not self.installed.is_installed(pkg_name):
                logger.error(f"包 {pkg_name} 未安装")
                return
            install_dir = self.installed.data.get(pkg_name, {}).get('install_dir')
            if install_dir and os.path.exists(install_dir):
                print(f"包 {pkg_name} 安装文件列表：")
                for root, dirs, files in os.walk(install_dir):
                    rel = os.path.relpath(root, install_dir)
                    if rel == '.':
                        rel = ''
                    for f in files:
                        print(os.path.join(rel, f))
            else:
                logger.warning("安装目录不存在")
            return

        if pkg_name:
            info_data = self.db.get_pkg(pkg_name)
            if not info_data:
                logger.error(f"包 {pkg_name} 不存在")
                return
            installed = self.installed.is_installed(pkg_name)
            if info:
                # 显示详细信息
                print(f"名称: {pkg_name}")
                print(f"全名: {info_data.get('Name', '')}")
                print(f"说明: {info_data.get('Comment', '')}")
                print(f"版本: {info_data.get('Version', '')}")
                print(f"发布号: {info_data.get('Release', '')}")
                print(f"状态: {colorize('已安装', 'GREEN') if installed else colorize('未安装', 'RED')}")
                if installed:
                    inst_info = self.installed.data.get(pkg_name, {})
                    print(f"安装目录: {inst_info.get('install_dir', '')}")
                    print(f"符号链接: {inst_info.get('symlink', '')}")
            else:
                status = colorize("已安装", 'GREEN') if installed else colorize("未安装", 'RED')
                print(f"{pkg_name} {info_data.get('Version', '')} - {info_data.get('Name', '')} [{status}]")
        else:
            # 列出所有包
            for name in sorted(self.db.list_pkgs()):
                info_data = self.db.get_pkg(name)
                installed = self.installed.is_installed(name)
                status = colorize("已安装", 'GREEN') if installed else colorize("未安装", 'RED')
                if quiet:
                    print(name)
                else:
                    print(f"{name} {info_data.get('Version', '')} - {info_data.get('Name', '')} [{status}]")

    def sync_db(self):
        self.db.sync()

    def clean_cache(self, level=1):
        cache_dir = self.cache_dir
        if not os.path.exists(cache_dir):
            return
        if level == 1:
            # 只删除未安装的包（暂简化为删除所有缓存）
            shutil.rmtree(cache_dir)
            ensure_dir(cache_dir)
            logger.info("缓存已清理（所有文件）")
        elif level >= 2:
            shutil.rmtree(cache_dir)
            ensure_dir(cache_dir)
            logger.info("缓存已完全清空")
        else:
            logger.info("缓存清理级别无效，默认只删除未安装包")

    def launch(self, pkg_name):
        if not self.installed.is_installed(pkg_name):
            logger.error(f"包 {pkg_name} 未安装")
            sys.exit(1)
        exec_path = os.path.join(self.bin_dir, pkg_name)
        if not os.path.exists(exec_path) or not os.access(exec_path, os.X_OK):
            logger.error(f"可执行文件不存在或不可执行: {exec_path}")
            sys.exit(1)
        os.execv(exec_path, [exec_path] + sys.argv[2:])

# ---------- 命令行解析（Pacman 风格） ----------
def print_help():
    help_text = f"""
{colorize('TouchFish Version Manager (tfvm) v' + VERSION, 'CYAN')}

用法: tfvm <操作> [选项] [目标]

操作:
  -Q, --query         查询本地数据库（已安装包）
  -R, --remove        移除软件包
  -S, --sync          同步/安装软件包

查询操作 (-Q) 选项:
  -c, --changelog     查看包的更新日志（暂未实现）
  -d, --deps          仅列出作为依赖项安装的包
  -e, --explicit      仅列出主动安装的包
  -g, --groups        查看包所属的组
  -i, --info          显示包的详细信息
  -k, --check         检查包的文件是否存在
  -l, --list          列出包安装的所有文件
  -o, --owns <文件>   查询文件属于哪个包
  -s, --search <表达式> 搜索已安装的包
  -t, --unrequired    列出孤立包（不被任何包需要）
  -u, --upgrades      列出所有可更新的包
  -q, --quiet         输出精简信息

移除操作 (-R) 选项:
  -c, --cascade       级联删除（移除目标包及依赖它们的包）
  -n, --nosave        移除时不保留配置文件（默认保留为 .pacsave）
  -s, --recursive     递归删除（移除不被需要的依赖）
  -u, --unneeded      移除不被需要的目标包

同步操作 (-S) 选项:
  -c, --clean         清理缓存（一次删除未安装包，两次清空全部）
  -i, --info          显示远程仓库包的详细信息
  -l, --list          列出指定仓库的所有包
  -s, --search <表达式> 在远程仓库中搜索包
  -u, --sysupgrade    升级系统（升级所有已安装包或指定包）
  -y, --refresh       刷新同步数据库（一次刷新，两次强制刷新）
  -q, --quiet         输出精简信息

通用选项:
  -v, --verbose       输出详细执行过程
  --noconfirm         不询问确认
  --debug             输出调试信息
  -h, --help          显示帮助

示例:
  tfvm -S touchfish              安装/升级 touchfish
  tfvm -Syu                      同步数据库并升级所有包
  tfvm -S -u touchfish           仅升级 touchfish（若未安装则报错）
  tfvm -S -c                     清理缓存（删除未安装的包）
  tfvm -S -cc                    清空整个缓存
  tfvm -Q                        列出所有已安装包
  tfvm -Q -i tfvm                显示 tfvm 详细信息
  tfvm -Q -s "fish"              搜索已安装包中包含 "fish" 的
  tfvm -Q -u                     列出可更新的包
  tfvm -Q -l touchfish           列出 touchfish 安装的文件
  tfvm -R touchfish              卸载 touchfish
  tfvm -R -c touchfish           级联删除 touchfish（及依赖它的包）
  tfvm touchfish                 启动已安装的 touchfish
"""
    print(help_text)

def parse_args():
    raw = sys.argv[1:]
    if not raw:
        print_help()
        sys.exit(0)

    # 处理 -v, -h (独立)
    if '-v' in raw or '--version' in raw:
        print(VERSION)
        sys.exit(0)
    if '-h' in raw or '--help' in raw:
        print_help()
        sys.exit(0)

    op = None
    params = {
        'refresh': False,      # -y
        'clean': 0,            # -c 数量
        'upgrade': False,      # -u (针对 -S)
        'info': False,         # -i
        'search': None,        # -s <expr>
        'list_files': False,   # -l
        'quiet': False,        # -q
        'cascade': False,      # -c (针对 -R)
        'recursive': False,    # -s (针对 -R)
        'nosave': False,       # -n
        'unneeded': False,     # -u (针对 -R)
        'verbose': False,      # -v
        'noconfirm': False,    # --noconfirm
        'debug': False,        # --debug
    }
    packages = []

    # 用于收集长选项（如 --noconfirm）
    long_opts = {
        '--sync': 'S',
        '--query': 'Q',
        '--remove': 'R',
        '--refresh': 'y',
        '--sysupgrade': 'u',
        '--clean': 'c',
        '--info': 'i',
        '--search': 's',
        '--list': 'l',
        '--quiet': 'q',
        '--cascade': 'c',
        '--recursive': 's',
        '--nosave': 'n',
        '--unneeded': 'u',
        '--verbose': 'v',
        '--noconfirm': 'noconfirm',
        '--debug': 'debug',
        '--help': 'h',
        '--version': 'v',
    }

    # 先尝试识别操作（第一个非选项参数可能是操作，也可能直接是包名）
    # 但也可以先扫描所有参数，提取操作
    # 为了支持 -Syu 这种组合，我们先将所有参数展开为单字符列表（长选项除外）
    expanded = []
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg.startswith('--'):
            expanded.append(arg)
        elif arg.startswith('-') and len(arg) > 1:
            for ch in arg[1:]:
                expanded.append('-' + ch)
        else:
            expanded.append(arg)
        i += 1

    # 解析 expanded
    idx = 0
    while idx < len(expanded):
        arg = expanded[idx]
        if arg.startswith('--'):
            # 长选项
            if arg in long_opts:
                opt = long_opts[arg]
                if opt in ('s', 'o'):  # 需要参数
                    if idx+1 < len(expanded):
                        params['search'] = expanded[idx+1]
                        idx += 2
                    else:
                        logger.error(f"选项 {arg} 需要参数")
                        sys.exit(1)
                else:
                    # 处理特殊长选项
                    if opt == 'noconfirm':
                        params['noconfirm'] = True
                    elif opt == 'debug':
                        params['debug'] = True
                    elif opt in ('y', 'u', 'c', 'i', 'l', 'q', 'n', 'v'):
                        # 映射到对应短选项
                        # 但我们通过短选项逻辑处理，这里暂时不重复
                        pass
                    idx += 1
            else:
                logger.warning(f"忽略未知长选项: {arg}")
                idx += 1
            continue

        if arg.startswith('-'):
            # 短选项
            for ch in arg[1:]:
                if ch.isupper():
                    if op is not None:
                        logger.error("只能指定一个操作")
                        sys.exit(1)
                    if ch == 'Q':
                        op = 'query'
                    elif ch == 'R':
                        op = 'remove'
                    elif ch == 'S':
                        op = 'sync'
                    else:
                        logger.error(f"未知操作: -{ch}")
                        sys.exit(1)
                elif ch.islower():
                    # 参数选项
                    if ch == 'y':
                        params['refresh'] = True
                    elif ch == 'c':
                        params['clean'] += 1
                    elif ch == 'u':
                        params['upgrade'] = True
                    elif ch == 'i':
                        params['info'] = True
                    elif ch == 's':
                        # -s 后面需要参数
                        if idx+1 < len(expanded) and not expanded[idx+1].startswith('-'):
                            params['search'] = expanded[idx+1]
                            idx += 1
                        else:
                            logger.error("-s 选项需要参数")
                            sys.exit(1)
                    elif ch == 'l':
                        params['list_files'] = True
                    elif ch == 'q':
                        params['quiet'] = True
                    elif ch == 'n':
                        params['nosave'] = True
                    elif ch == 'v':
                        params['verbose'] = True
                    else:
                        logger.warning(f"忽略未知选项: -{ch}")
                else:
                    logger.error(f"无效字符: {ch}")
                    sys.exit(1)
            idx += 1
        else:
            # 目标（包名或搜索字符串）
            # 注意：如果当前在 -s 的参数后，已经消耗了，这里不再重复添加
            # 但为简单，我们这里收集所有非选项参数作为包名
            packages.append(arg)
            idx += 1

    # 如果未指定操作，但有包名，则视为启动模式（launch）
    if op is None:
        if packages:
            op = 'launch'
        else:
            print_help()
            sys.exit(0)

    # 针对 -S 操作，如果 -u 被指定，则视为升级模式
    if op == 'sync' and params['upgrade']:
        # 升级模式：如果没有包名，则升级所有已安装包；否则升级指定包（必须已安装）
        pass  # 在 main 中处理

    # 清理：如果 -c 在 -S 下，可能是清理缓存；如果 -c 在 -R 下，表示 cascade
    if op == 'remove' and params['clean'] > 0:
        params['cascade'] = True
    if op == 'remove' and params['search'] is not None:  # -s 在 -R 下表示 recursive
        params['recursive'] = True

    # 将操作统一为内部方法名
    internal_op = op
    if op == 'sync':
        internal_op = 'install'
    elif op == 'query':
        internal_op = 'query'
    elif op == 'remove':
        internal_op = 'remove'

    return {
        'op': internal_op,
        'params': params,
        'packages': packages,
        'original_op': op
    }

# ---------- 主函数 ----------
def main():
    args = parse_args()
    op = args['op']
    params = args['params']
    packages = args['packages']
    original_op = args['original_op']

    manager = TfvmManager()

    if op == 'install':
        # 判断是正常安装还是升级模式（仅升级已安装）
        if params['upgrade']:
            # 升级模式
            if not packages:
                # 升级所有已安装包
                manager.upgrade(refresh=params['refresh'], clean_cache=(params['clean'] > 0))
            else:
                manager.upgrade(packages, refresh=params['refresh'], clean_cache=(params['clean'] > 0))
        else:
            # 正常安装/升级
            manager.install(packages, clean_cache=(params['clean'] > 0), refresh=params['refresh'])
    elif op == 'remove':
        manager.remove(packages, cascade=params['cascade'], recursive=params['recursive'])
    elif op == 'query':
        # 处理查询选项
        if params['upgrades']:
            manager.query(upgrades=True, quiet=params['quiet'])
        elif params['search'] is not None:
            manager.query(search=params['search'], quiet=params['quiet'])
        elif params['list_files']:
            if packages:
                manager.query(pkg_name=packages[0], list_files=True, quiet=params['quiet'])
            else:
                logger.error("列出文件需要指定包名")
                sys.exit(1)
        elif params['info']:
            if packages:
                manager.query(pkg_name=packages[0], info=True, quiet=params['quiet'])
            else:
                logger.error("显示详细信息需要指定包名")
                sys.exit(1)
        else:
            # 默认查询：若指定包名则显示，否则列出所有
            if packages:
                manager.query(pkg_name=packages[0], quiet=params['quiet'])
            else:
                manager.query(quiet=params['quiet'])
    elif op == 'clean':
        # 独立清理（虽然文档没有独立 -C，但保留作为扩展）
        manager.clean_cache(level=params['clean'] if params['clean'] > 0 else 1)
    elif op == 'launch':
        if not packages:
            logger.error("未指定要启动的包")
            sys.exit(1)
        manager.launch(packages[0])
    else:
        logger.error(f"未知操作: {op}")
        sys.exit(1)

    if manager.upgraded_tfvm:
        logger.info(colorize("tfvm 已升级到最新版本，请重新运行命令以应用更新。", 'YELLOW'))

if __name__ == "__main__":
    main()
