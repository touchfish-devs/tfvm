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
import importlib

# ---------- 语言加载 ----------
def load_language(lang_code):
    try:
        mod = importlib.import_module(f'lang.{lang_code}')
        return mod._
    except ImportError:
        # 回退到英文
        mod = importlib.import_module('lang.en')
        return mod._

# 先加载配置以获取语言设置（但配置尚未加载，需要延迟）
# 我们将在 Config 加载后调用 load_language

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
VERSION = "1.3.5"

DEFAULT_CONFIG = {
    "registry": "https://reg.touchfish.us.ci/db.yml",
    "proxy": "https://v4.gh-proxy.org",
    "sudo_at_start": False,
    "install_prefix": "/usr/local",
    "install_root": "/opt/tfvm",
    "cache_dir": "~/.tfvm/cache",
    "db_file": "~/.tfvm/db.yml",
    "installed_db": "~/.tfvm/installed.json",
    "lang": "en"          # 新增语言配置
}

# ---------- 全局翻译函数 ----------
_ = None  # 稍后初始化

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
        # 加载语言
        lang_code = self.data.get('lang', 'en')
        global _
        _ = load_language(lang_code)
        logger.info(_('loading_config'))

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = value
            return data
        else:
            # 首次启动，使用默认配置（语言为 en）
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

    def set(self, key, value):
        self.data[key] = value
        self.save()
        # 如果修改了语言，重新加载
        if key == 'lang':
            global _
            _ = load_language(value)

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
        logger.info(_('syncing_db').format(url))
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = yaml.safe_load(resp.text)
            if not data:
                raise ValueError("Database empty")
            self.packages = data
        except Exception as e:
            logger.error(_('download_failed').format(e))
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
            logger.info(colorize(_('added_tfvm_default'), 'YELLOW'))

        self.save()
        logger.info(colorize(_('db_sync_complete').format(len(self.packages)), 'GREEN'))

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
                logger.error(_('sudo_required'))  # 需要添加
                sys.exit(1)

    def _download_file(self, url: str, dest: str):
        proxy = self.config.get('proxy')
        if proxy:
            if proxy.endswith('/'):
                full_url = proxy + url
            else:
                full_url = proxy + '/' + url
            logger.info(f"使用代理: {proxy}")
        else:
            full_url = url

        logger.info(_('downloading').format(full_url))
        try:
            resp = requests.get(full_url, stream=True, timeout=60)
            resp.raise_for_status()
            total_size = int(resp.headers.get('content-length', 0))
            desc = os.path.basename(dest)
            with open(dest, 'wb') as f:
                if total_size == 0:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                    logger.info(_('download_complete').format(dest))
                    return

                with tqdm(total=total_size, unit='B', unit_scale=True,
                          desc=desc, ncols=80, file=sys.stdout) as pbar:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
                    pbar.close()
            logger.info(_('download_complete').format(dest))
        except Exception as e:
            logger.error(_('download_failed').format(e))
            sys.exit(1)

    def _extract_archive(self, archive_path: str, dest_dir: str):
        logger.info(_('extracting').format(archive_path, dest_dir))
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
            logger.error(_('extract_failed').format(e))
            sys.exit(1)
        except FileNotFoundError as e:
            logger.error(_('missing_tool').format(e))
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
            return 'conflict', _('conflict_check').format(pkg_name, _('path_conflict'))

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
            return 'occupied_ahead', _('occupied_ahead').format(existing_path)
        elif ext_idx > local_idx:
            return 'occupied_behind', _('occupied_behind').format(existing_path)
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
                logger.error(_('pkg_not_in_db').format(dep))
                sys.exit(1)
            sub = self._resolve_dependencies(dep, dep_info, visited)
            result.extend(sub)
            result.append(dep)
        return result

    def _install_pkg(self, pkg_name: str, pkg_info: dict, skip_download=False):
        if self.installed.is_installed(pkg_name):
            current_version = self.installed.get_installed_version(pkg_name)
            new_version = pkg_info.get('Version')
            if current_version == "build":
                logger.info(f"包 {pkg_name} 是 build 版本，强制重新安装")
            elif current_version == new_version:
                logger.info(_('pkg_up_to_date').format(pkg_name, current_version))
                return
            else:
                logger.info(_('upgrading_pkg').format(pkg_name, current_version, new_version))

            info = self.installed.data.get(pkg_name, {})
            symlink = info.get('symlink')
            install_dir = info.get('install_dir')
            if symlink and os.path.islink(symlink):
                if not run_sudo(['rm', '-f', symlink]):
                    logger.error(f"删除旧符号链接失败: {symlink}")
                    sys.exit(1)
                logger.info(_('removed_symlink').format(symlink))
            if install_dir and os.path.exists(install_dir):
                if not run_sudo(['rm', '-rf', install_dir]):
                    logger.error(f"删除旧安装目录失败: {install_dir}")
                    sys.exit(1)
                logger.info(_('removed_install_dir').format(install_dir))
            self.installed.remove_pkg(pkg_name)

        status, msg = self._check_path_conflict(pkg_name)
        if status == 'conflict':
            logger.error(_('conflict_check').format(pkg_name, msg))
            sys.exit(1)
        elif status in ('occupied_ahead', 'occupied_behind'):
            logger.warning(_('conflict_check').format(pkg_name, msg))

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
                logger.info(_('using_cache').format(cache_path))
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
                logger.info(colorize(_('pkg_install_complete').format(pkg_name), 'GREEN'))
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
            logger.info(colorize(_('pkg_install_complete').format(pkg_name), 'GREEN'))

    def install(self, pkg_names: list, clean_cache: bool = False, refresh: bool = False, upgrade_mode: bool = False):
        self._check_sudo_requirement()
        if refresh:
            self.db.sync()
        if clean_cache:
            self.clean_cache()

        if upgrade_mode and not pkg_names:
            pkg_names = list(self.installed.get_all().keys())
            if not pkg_names:
                logger.info(_('no_installed_pkgs'))
                return

        if upgrade_mode:
            for name in pkg_names:
                if not self.installed.is_installed(name):
                    logger.error(_('pkg_not_installed').format(name))
                    sys.exit(1)

        all_pkgs = []
        visited = set()
        for name in pkg_names:
            pkg_info = self.db.get_pkg(name)
            if not pkg_info:
                logger.error(_('pkg_not_in_db').format(name))
                sys.exit(1)
            deps = self._resolve_dependencies(name, pkg_info, visited)
            all_pkgs.extend(deps)
            all_pkgs.append(name)
        all_pkgs = list(dict.fromkeys(all_pkgs))

        if not all_pkgs:
            logger.info(_('no_pkgs_to_process'))
            return

        if upgrade_mode:
            upgradable = []
            for pkg in all_pkgs:
                if self.installed.is_installed(pkg):
                    inst_info = self.installed.data.get(pkg, {})
                    cur_ver = inst_info.get('version')
                    pkg_info = self.db.get_pkg(pkg)
                    new_ver = pkg_info.get('Version') if pkg_info else None
                    if cur_ver == "build" or (new_ver and cur_ver != new_ver):
                        upgradable.append((pkg, cur_ver, new_ver))
            if not upgradable:
                logger.info(_('no_upgradable_pkgs'))
                return
            print(_('upgradable_list_header'))
            for idx, (name, cur, new) in enumerate(upgradable):
                print(f"{idx}. {name} {cur} -> {new}")
            print(_('exclude_prompt'), end=' ')
            user_input = input().strip()
            exclude_set = set()
            if user_input:
                if user_input.lower() == 'b':
                    for name, cur, new in upgradable:
                        if cur == "build" or new == "build":
                            exclude_set.add(name)
                else:
                    parts = user_input.split()
                    for part in parts:
                        try:
                            idx = int(part)
                            if 0 <= idx < len(upgradable):
                                exclude_set.add(upgradable[idx][0])
                            else:
                                logger.warning(f"无效序号: {idx}")
                        except ValueError:
                            logger.warning(f"无效输入: {part}")
            if exclude_set:
                all_pkgs = [p for p in all_pkgs if p not in exclude_set]
                logger.info(_('excluded_pkgs').format(', '.join(exclude_set)))
                if not all_pkgs:
                    logger.info(_('no_pkgs_left'))
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
            logger.error(_('conflict_list'))
            for pkg, msg in conflicts:
                logger.error(f"  {pkg}: {msg}")
            sys.exit(1)
        if warnings:
            logger.warning(_('warning_list'))
            for pkg, msg in warnings:
                logger.warning(f"  {pkg}: {msg}")

        logger.info(_('processing_pkgs').format(', '.join(all_pkgs)))
        confirm = input(colorize(_('confirm_continue'), 'YELLOW')).strip().lower()
        if confirm and confirm != 'y':
            logger.info(_('operation_cancelled'))
            return

        logger.info(colorize(_('phase1_download'), 'BLUE'))
        for pkg in all_pkgs:
            pkg_info = self.db.get_pkg(pkg)
            if not pkg_info:
                logger.error(_('pkg_not_in_db').format(pkg))
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
                logger.info(_('using_cache').format(cache_path))
        logger.info(colorize(_('phase1_done'), 'GREEN'))

        logger.info(colorize(_('phase2_install'), 'BLUE'))
        for pkg in all_pkgs:
            pkg_info = self.db.get_pkg(pkg)
            if not pkg_info:
                logger.error(_('pkg_not_in_db').format(pkg))
                continue
            self._install_pkg(pkg, pkg_info, skip_download=True)

    def remove(self, pkg_names: list, cascade=False, recursive=False):
        self._check_sudo_requirement()
        if cascade:
            logger.warning(_('remove_cascade_warning'))
        if recursive:
            logger.warning(_('remove_recursive_warning'))

        for name in pkg_names:
            if not self.installed.is_installed(name):
                logger.warning(_('remove_not_installed').format(name))
                continue
            info = self.installed.data.get(name, {})
            symlink = info.get('symlink')
            install_dir = info.get('install_dir')
            if symlink and os.path.islink(symlink):
                if not run_sudo(['rm', '-f', symlink]):
                    logger.error(f"删除符号链接失败: {symlink}")
                    sys.exit(1)
                logger.info(_('remove_symlink_deleted').format(symlink))
            if install_dir and os.path.exists(install_dir):
                if not run_sudo(['rm', '-rf', install_dir]):
                    logger.error(f"删除安装目录失败: {install_dir}")
                    sys.exit(1)
                logger.info(_('remove_dir_deleted').format(install_dir))
            self.installed.remove_pkg(name)
            logger.info(colorize(_('remove_complete').format(name), 'GREEN'))

    def query(self, pkg_name=None, info=False, search=None, list_files=False, upgrades=False, quiet=False):
        if upgrades:
            upgradable = []
            for name, inst in self.installed.get_all().items():
                pkg_info = self.db.get_pkg(name)
                if pkg_info:
                    cur_ver = inst.get('version')
                    new_ver = pkg_info.get('Version')
                    if cur_ver != new_ver:
                        upgradable.append((name, cur_ver, new_ver))
            if not upgradable:
                logger.info(_('no_upgradable_pkgs'))
            else:
                print(_('query_upgradable_header'))
                for name, cur, new in upgradable:
                    print(f"{name} {cur} -> {new}")
            return

        if search:
            pattern = re.compile(search, re.IGNORECASE)
            found = []
            for name, pkg_info in self.db.packages.items():
                if pattern.search(name) or pattern.search(pkg_info.get('Name', '')):
                    installed = self.installed.is_installed(name)
                    found.append((name, pkg_info, installed))
            if not found:
                logger.info(_('query_search_not_found'))
            else:
                for name, info, installed in found:
                    status = colorize(_('query_pkg_status_installed'), 'GREEN') if installed else colorize(_('query_pkg_status_not_installed'), 'RED')
                    if quiet:
                        print(name)
                    else:
                        print(f"{name} {info.get('Version', '')} - {info.get('Name', '')} [{status}]")
            return

        if list_files:
            if not pkg_name:
                logger.error(_('query_list_files_need_pkg'))
                return
            if not self.installed.is_installed(pkg_name):
                logger.error(_('query_list_files_not_installed').format(pkg_name))
                return
            install_dir = self.installed.data.get(pkg_name, {}).get('install_dir')
            if install_dir and os.path.exists(install_dir):
                print(_('query_list_files_title').format(pkg_name))
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
                logger.error(_('query_pkg_not_found').format(pkg_name))
                return
            installed = self.installed.is_installed(pkg_name)
            if info:
                status = colorize(_('query_pkg_status_installed'), 'GREEN') if installed else colorize(_('query_pkg_status_not_installed'), 'RED')
                print(_('query_pkg_info_header').format(
                    pkg_name,
                    info_data.get('Name', ''),
                    info_data.get('Comment', ''),
                    info_data.get('Version', ''),
                    info_data.get('Release', ''),
                    status
                ))
                if installed:
                    inst_info = self.installed.data.get(pkg_name, {})
                    print(_('query_pkg_install_dir').format(inst_info.get('install_dir', '')))
                    print(_('query_pkg_symlink').format(inst_info.get('symlink', '')))
            else:
                status = colorize(_('query_pkg_status_installed'), 'GREEN') if installed else colorize(_('query_pkg_status_not_installed'), 'RED')
                print(f"{pkg_name} {info_data.get('Version', '')} - {info_data.get('Name', '')} [{status}]")
        else:
            for name in sorted(self.db.list_pkgs()):
                info_data = self.db.get_pkg(name)
                installed = self.installed.is_installed(name)
                status = colorize(_('query_pkg_status_installed'), 'GREEN') if installed else colorize(_('query_pkg_status_not_installed'), 'RED')
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
            shutil.rmtree(cache_dir)
            ensure_dir(cache_dir)
            logger.info(_('cache_cleared'))
        elif level >= 2:
            shutil.rmtree(cache_dir)
            ensure_dir(cache_dir)
            logger.info(_('cache_purged'))
        else:
            logger.info("缓存清理级别无效，默认只删除未安装包")

    def launch(self, pkg_name):
        if not self.installed.is_installed(pkg_name):
            logger.error(_('launch_not_installed').format(pkg_name))
            sys.exit(1)
        exec_path = os.path.join(self.bin_dir, pkg_name)
        if not os.path.exists(exec_path) or not os.access(exec_path, os.X_OK):
            logger.error(_('launch_exec_not_found').format(exec_path))
            sys.exit(1)
        os.execv(exec_path, [exec_path] + sys.argv[2:])

    def config_set(self, subcmd, values):
        if subcmd == 'r':
            if not values:
                logger.error(_('missing_registry_url'))
                return
            new_url = values[0]
            self.config.set('registry', new_url)
            logger.info(colorize(_('registry_updated').format(new_url), 'GREEN'))
        elif subcmd == 'p':
            if values:
                new_proxy = values[0]
            else:
                new_proxy = ""
            self.config.set('proxy', new_proxy)
            if new_proxy:
                logger.info(colorize(_('proxy_set').format(new_proxy), 'GREEN'))
            else:
                logger.info(colorize(_('proxy_cleared'), 'GREEN'))
        elif subcmd == 't':
            if not values:
                logger.error(_('missing_target_dir'))
                return
            target_dir = expand_path(values[0])
            if not os.path.exists(target_dir):
                try:
                    Path(target_dir).mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.error(_('dir_create_fail').format(target_dir, e))
                    return
            db_file = self.config.get('db_file')
            inst_db = self.config.get('installed_db')
            if not os.path.exists(db_file) and not os.path.exists(inst_db):
                logger.warning(_('no_db_files'))
                return
            if os.path.exists(db_file):
                new_db = os.path.join(target_dir, os.path.basename(db_file))
                shutil.move(db_file, new_db)
                self.config.set('db_file', new_db)
                logger.info(_('db_moved').format(new_db))
            if os.path.exists(inst_db):
                new_inst = os.path.join(target_dir, os.path.basename(inst_db))
                shutil.move(inst_db, new_inst)
                self.config.set('installed_db', new_inst)
                logger.info(_('db_moved').format(new_inst))
            logger.info(colorize(_('db_moved_success'), 'GREEN'))
        else:
            logger.error(_('unknown_config_subcmd').format(subcmd))

# ---------- 命令行解析 ----------
def print_help():
    # 使用翻译的 help_text
    help_str = _('help_text').format(version=VERSION)
    print(help_str)

def parse_args():
    raw = sys.argv[1:]
    if not raw:
        print_help()
        sys.exit(0)

    if '-v' in raw or '--version' in raw:
        print(VERSION)
        sys.exit(0)
    if '-h' in raw or '--help' in raw:
        print_help()
        sys.exit(0)

    op = None
    params = {
        'refresh': False,
        'clean': 0,
        'upgrade': False,
        'info': False,
        'search': None,
        'list_files': False,
        'quiet': False,
        'cascade': False,
        'recursive': False,
        'nosave': False,
        'verbose': False,
        'noconfirm': False,
        'debug': False,
        'config_subcmd': None,
        'config_values': []
    }
    packages = []

    expanded = []
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg.startswith('-C') and len(arg) == 3 and arg[2].islower():
            expanded.append(arg)
        else:
            if arg.startswith('--'):
                expanded.append(arg)
            elif arg.startswith('-') and len(arg) > 1:
                for ch in arg[1:]:
                    expanded.append('-' + ch)
            else:
                expanded.append(arg)
        i += 1

    idx = 0
    while idx < len(expanded):
        arg = expanded[idx]
        if arg.startswith('--'):
            # 简化长选项，忽略
            idx += 1
            continue

        if arg.startswith('-'):
            if arg == '-C':
                op = 'config'
                idx += 1
                if idx < len(expanded) and expanded[idx].startswith('-') and len(expanded[idx]) == 2 and expanded[idx][1] in ('r', 'p', 't'):
                    subcmd = expanded[idx][1]
                    idx += 1
                    values = []
                    while idx < len(expanded) and not expanded[idx].startswith('-'):
                        values.append(expanded[idx])
                        idx += 1
                    params['config_subcmd'] = subcmd
                    params['config_values'] = values
                else:
                    logger.error(_('error_missing_config_subcmd'))
                    sys.exit(1)
                continue
            for ch in arg[1:]:
                if ch.isupper():
                    if op is not None:
                        logger.error(_('error_only_one_operation'))
                        sys.exit(1)
                    if ch == 'Q':
                        op = 'query'
                    elif ch == 'R':
                        op = 'remove'
                    elif ch == 'S':
                        op = 'sync'
                    else:
                        logger.error(_('error_unknown_op').format(ch))
                        sys.exit(1)
                elif ch.islower():
                    if ch == 'y':
                        params['refresh'] = True
                    elif ch == 'c':
                        params['clean'] += 1
                    elif ch == 'u':
                        params['upgrade'] = True
                    elif ch == 'i':
                        params['info'] = True
                    elif ch == 's':
                        if idx+1 < len(expanded) and not expanded[idx+1].startswith('-'):
                            params['search'] = expanded[idx+1]
                            idx += 1
                        else:
                            logger.error(_('error_s_needs_arg'))
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
                    logger.error(_('error_invalid_char').format(ch))
                    sys.exit(1)
            idx += 1
        else:
            packages.append(arg)
            idx += 1

    if op is None and packages:
        op = 'launch'
    elif op is None:
        print_help()
        sys.exit(0)

    internal_op = op
    if op == 'sync':
        internal_op = 'install'

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

    manager = TfvmManager()

    if args['original_op'] == 'config':
        manager.config_set(params['config_subcmd'], params['config_values'])
        return

    if op == 'install':
        manager.install(packages,
                        clean_cache=(params['clean'] > 0),
                        refresh=params['refresh'],
                        upgrade_mode=params['upgrade'])
    elif op == 'remove':
        manager.remove(packages,
                       cascade=params['cascade'],
                       recursive=params['recursive'])
    elif op == 'query':
        if params.get('upgrade', False):
            manager.query(upgrades=True, quiet=params['quiet'])
        elif params['search'] is not None:
            manager.query(search=params['search'], quiet=params['quiet'])
        elif params['list_files']:
            if packages:
                manager.query(pkg_name=packages[0], list_files=True, quiet=params['quiet'])
            else:
                logger.error(_('query_list_files_need_pkg'))
                sys.exit(1)
        elif params['info']:
            if packages:
                manager.query(pkg_name=packages[0], info=True, quiet=params['quiet'])
            else:
                logger.error(_('query_info_need_pkg'))
                sys.exit(1)
        else:
            if packages:
                manager.query(pkg_name=packages[0], quiet=params['quiet'])
            else:
                manager.query(quiet=params['quiet'])
    elif op == 'launch':
        if not packages:
            logger.error(_('error_launch_missing_pkg'))
            sys.exit(1)
        manager.launch(packages[0])
    else:
        logger.error(_('error_unknown_op_final').format(op))
        sys.exit(1)

    if manager.upgraded_tfvm:
        logger.info(colorize(_('tfvm_self_upgraded'), 'YELLOW'))

if __name__ == "__main__":
    main()
