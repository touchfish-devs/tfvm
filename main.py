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
import argparse
import logging
from pathlib import Path
from urllib.parse import urlparse
import requests

# ---------- 日志配置 ----------
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger('tfvm')

# ---------- 常量 ----------
DEFAULT_CONFIG = {
    "registry": "https://reg.touchfish.us.ci/db.yml",
    "sudo_at_start": False,
    "sudo_at_download": False,
    "install_prefix": "/usr/local",
    "cache_dir": "~/.tfvm/cache",
    "db_file": "~/.tfvm/db.yml",
    "installed_db": "~/.tfvm/installed.json"
}

VERSION = "1.1.0"

# ---------- 辅助函数 ----------
def expand_path(path: str) -> str:
    """展开 ~ 并转换为绝对路径"""
    return os.path.abspath(os.path.expanduser(path))

def ensure_dir(path: str):
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)

def run_sudo(cmd: list):
    """以 sudo 执行命令，返回是否成功"""
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
                return json.load(f)
        else:
            # 首次启动创建默认配置
            logger.info(f"首次启动，创建默认配置文件 {self.config_path}")
            self.data = DEFAULT_CONFIG.copy()
            self.save()
            return self.data

    def save(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def _expand_paths(self):
        """将路径字段展开为绝对路径"""
        for key in ['cache_dir', 'db_file', 'installed_db']:
            if key in self.data:
                self.data[key] = expand_path(self.data[key])
        # 确保这些目录存在
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
        """从本地数据库文件加载"""
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r') as f:
                self.packages = yaml.safe_load(f) or {}
        else:
            self.packages = {}

    def save(self):
        """保存到本地数据库文件（一般不需要，因为从远程同步）"""
        with open(self.db_path, 'w') as f:
            yaml.dump(self.packages, f)

    def sync(self):
        """从远程仓库下载数据库"""
        url = self.config.get('registry')
        logger.info(f"正在同步软件包数据库: {url}")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = yaml.safe_load(resp.text)
            if not data:
                raise ValueError("数据库为空")
            self.packages = data
            self.save()
            logger.info(f"数据库同步完成，共 {len(self.packages)} 个软件包")
        except Exception as e:
            logger.error(f"同步数据库失败: {e}")
            sys.exit(1)

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

    def add_pkg(self, name: str, version: str, files: list):
        """记录安装的包及其文件列表"""
        self.data[name] = {'version': version, 'files': files}
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

        # 安装前缀下的 bin 目录
        self.bin_dir = os.path.join(self.config.get('install_prefix'), 'bin')
        ensure_dir(self.bin_dir)

        # 缓存目录
        self.cache_dir = self.config.get('cache_dir')
        ensure_dir(self.cache_dir)

    def _check_sudo_requirement(self):
        """根据配置检查是否需要以 root 运行"""
        if self.config.get('sudo_at_start', False):
            if not is_root():
                logger.error("配置要求以 sudo 运行，请使用 sudo tfvm ...")
                sys.exit(1)

    def _download_file(self, url: str, dest: str):
        """下载文件到指定路径，支持进度显示"""
        logger.info(f"下载: {url}")
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            total = int(resp.headers.get('content-length', 0))
            with open(dest, 'wb') as f:
                if total == 0:
                    f.write(resp.content)
                else:
                    downloaded = 0
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        # 简单进度
                        if total > 0:
                            percent = int(100 * downloaded / total)
                            sys.stdout.write(f"\r下载进度: {percent}%")
                            sys.stdout.flush()
            sys.stdout.write("\n")
            logger.info(f"下载完成: {dest}")
        except Exception as e:
            logger.error(f"下载失败: {e}")
            sys.exit(1)

    def _extract_tar_gz(self, tarball: str, dest_dir: str):
        """解压 tar.gz 到目标目录"""
        logger.info(f"解压: {tarball} -> {dest_dir}")
        with tarfile.open(tarball, 'r:gz') as tar:
            tar.extractall(dest_dir)

    def _install_files(self, pkg_name: str, pkg_info: dict, temp_dir: str):
        """复制二进制文件到系统 bin 目录并设置可执行权限"""
        binary_list = pkg_info.get('Binary', [])
        if not binary_list:
            logger.warning(f"包 {pkg_name} 没有需要安装的二进制文件")
            return []

        installed_files = []
        for rel_path in binary_list:
            src = os.path.join(temp_dir, rel_path)
            if not os.path.exists(src):
                logger.error(f"二进制文件不存在: {src}")
                sys.exit(1)
            dest = os.path.join(self.bin_dir, os.path.basename(rel_path))
            # 使用 sudo 复制
            if not run_sudo(['cp', src, dest]):
                logger.error(f"复制 {src} 到 {dest} 失败")
                sys.exit(1)
            # 设置可执行权限
            if not run_sudo(['chmod', '+x', dest]):
                logger.error(f"设置可执行权限失败: {dest}")
                sys.exit(1)
            installed_files.append(dest)
            logger.info(f"已安装: {dest}")
        return installed_files

    def _resolve_dependencies(self, pkg_name: str, pkg_info: dict, visited: set):
        """递归解析依赖，返回需要安装的包列表（按拓扑顺序）"""
        if pkg_name in visited:
            return []  # 避免循环
        visited.add(pkg_name)

        deps = pkg_info.get('Depends', [])
        install_list = []
        for dep in deps:
            if self.installed.is_installed(dep):
                # 已安装，跳过
                continue
            dep_info = self.db.get_pkg(dep)
            if not dep_info:
                logger.error(f"依赖包 {dep} 不存在于数据库中")
                sys.exit(1)
            # 递归解析依赖
            sub_deps = self._resolve_dependencies(dep, dep_info, visited)
            install_list.extend(sub_deps)
            install_list.append(dep)
        return install_list

    def _install_pkg(self, pkg_name: str, pkg_info: dict):
        """安装单个包（已解决依赖）"""
        if self.installed.is_installed(pkg_name):
            logger.info(f"包 {pkg_name} 已安装，跳过")
            return

        # 构造下载 URL
        registry_template = pkg_info.get('Registry')
        if not registry_template:
            logger.error(f"包 {pkg_name} 没有 Registry 字段")
            sys.exit(1)
        version = pkg_info.get('Version')
        if not version:
            logger.error(f"包 {pkg_name} 没有 Version 字段")
            sys.exit(1)
        # 替换 $version$，注意可能有多个
        download_url = registry_template.replace('$version$', version)

        # 下载到缓存
        tarball_name = f"{pkg_name}-{version}.tar.gz"
        cache_path = os.path.join(self.cache_dir, tarball_name)
        if not os.path.exists(cache_path):
            self._download_file(download_url, cache_path)

        # 解压到临时目录
        with tempfile.TemporaryDirectory(prefix='tfvm_') as tmpdir:
            self._extract_tar_gz(cache_path, tmpdir)
            # 确定解压根目录（可能包含单个顶层目录）
            # 通常 tar 包内有一个同名目录，我们进入该目录
            extracted_root = tmpdir
            items = os.listdir(tmpdir)
            if len(items) == 1 and os.path.isdir(os.path.join(tmpdir, items[0])):
                extracted_root = os.path.join(tmpdir, items[0])

            # 安装二进制
            installed_files = self._install_files(pkg_name, pkg_info, extracted_root)

        # 记录已安装
        self.installed.add_pkg(pkg_name, version, installed_files)
        logger.info(f"包 {pkg_name} 安装完成")

    def install(self, pkg_names: list, options: dict):
        """安装一个或多个包，处理依赖"""
        self._check_sudo_requirement()

        # 同步数据库
        self.db.sync()

        # 解析所有要安装的包及其依赖
        all_pkgs = set()
        visited = set()
        for name in pkg_names:
            pkg_info = self.db.get_pkg(name)
            if not pkg_info:
                logger.error(f"包 {name} 不存在于数据库")
                sys.exit(1)
            deps = self._resolve_dependencies(name, pkg_info, visited)
            all_pkgs.update(deps)
            all_pkgs.add(name)

        # 过滤已安装的
        to_install = [p for p in all_pkgs if not self.installed.is_installed(p)]
        if not to_install:
            logger.info("所有包已安装")
            return

        logger.info(f"将安装以下包: {', '.join(to_install)}")
        # 确认
        confirm = input("确认安装吗？(Y/n): ").strip().lower()
        if confirm and confirm != 'y':
            logger.info("安装取消")
            return

        # 按顺序安装
        # 注意：to_install 顺序是依赖在前，但我们从依赖解析获得的是线性列表，
        # 实际上需要按照依赖顺序安装，我们重新整理顺序：先安装依赖，再安装主包。
        # 由于 _resolve_dependencies 返回的列表已经包含依赖顺序（依赖先出现），
        # 我们只需按该顺序安装，但要确保每个包只安装一次。
        # 我们使用一个集合记录已安装的包。
        installed_set = set()
        for pkg in to_install:
            if pkg in installed_set:
                continue
            pkg_info = self.db.get_pkg(pkg)
            if not pkg_info:
                logger.error(f"包 {pkg} 不存在")
                continue
            # 检查其依赖是否已安装（理论上已在列表中，但可能因为循环导致未安装）
            deps = pkg_info.get('Depends', [])
            for dep in deps:
                if not self.installed.is_installed(dep) and dep not in installed_set:
                    # 如果依赖不在已安装集合中，则先安装（递归调用）
                    self._install_pkg(dep, self.db.get_pkg(dep))
                    installed_set.add(dep)
            self._install_pkg(pkg, pkg_info)
            installed_set.add(pkg)

    def remove(self, pkg_names: list):
        """卸载包"""
        self._check_sudo_requirement()
        for name in pkg_names:
            if not self.installed.is_installed(name):
                logger.warning(f"包 {name} 未安装")
                continue
            info = self.installed.data.get(name, {})
            files = info.get('files', [])
            if files:
                for f in files:
                    if os.path.exists(f):
                        if not run_sudo(['rm', '-f', f]):
                            logger.error(f"删除文件失败: {f}")
                            sys.exit(1)
                        logger.info(f"已删除: {f}")
            self.installed.remove_pkg(name)
            logger.info(f"包 {name} 已卸载")

    def query(self, pkg_name=None):
        """查询包信息"""
        if pkg_name:
            info = self.db.get_pkg(pkg_name)
            if not info:
                logger.error(f"包 {pkg_name} 不存在")
                return
            installed = self.installed.is_installed(pkg_name)
            status = "已安装" if installed else "未安装"
            print(f"名称: {pkg_name}")
            print(f"全名: {info.get('Name', '')}")
            print(f"说明: {info.get('Comment', '')}")
            print(f"版本: {info.get('Version', '')}")
            print(f"发布号: {info.get('Release', '')}")
            print(f"状态: {status}")
            if installed:
                print(f"已安装版本: {self.installed.get_installed_version(pkg_name)}")
        else:
            # 列出所有包
            for name in sorted(self.db.list_pkgs()):
                info = self.db.get_pkg(name)
                installed = self.installed.is_installed(name)
                status = "安装" if installed else "未安装"
                print(f"{name} {info.get('Version', '')} - {info.get('Name', '')} [{status}]")

    def sync_db(self):
        """仅同步数据库"""
        self.db.sync()

    def upgrade(self, pkg_names=None):
        """升级包，如果未指定则升级所有已安装包"""
        self._check_sudo_requirement()
        self.db.sync()

        if pkg_names:
            # 指定包升级
            for name in pkg_names:
                if not self.installed.is_installed(name):
                    logger.warning(f"包 {name} 未安装，跳过")
                    continue
                pkg_info = self.db.get_pkg(name)
                if not pkg_info:
                    logger.error(f"包 {name} 不存在于数据库")
                    sys.exit(1)
                current_version = self.installed.get_installed_version(name)
                new_version = pkg_info.get('Version')
                if current_version == new_version:
                    logger.info(f"包 {name} 已是最新版本 {current_version}")
                else:
                    logger.info(f"升级包 {name}: {current_version} -> {new_version}")
                    # 先卸载，再安装
                    self.remove([name])
                    self.install([name], {})
        else:
            # 升级所有已安装包
            installed = self.installed.get_all()
            for name in installed:
                pkg_info = self.db.get_pkg(name)
                if not pkg_info:
                    logger.warning(f"包 {name} 在数据库中不存在，可能已废弃")
                    continue
                current_version = installed[name].get('version')
                new_version = pkg_info.get('Version')
                if current_version == new_version:
                    logger.info(f"包 {name} 已是最新版本")
                else:
                    logger.info(f"升级包 {name}: {current_version} -> {new_version}")
                    self.remove([name])
                    self.install([name], {})

    def clean_cache(self):
        """清理下载的 tar.gz 包"""
        cache_dir = self.cache_dir
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            ensure_dir(cache_dir)
            logger.info("缓存已清理")

    def launch(self, pkg_name):
        """启动包的主程序"""
        if not self.installed.is_installed(pkg_name):
            logger.error(f"包 {pkg_name} 未安装")
            sys.exit(1)
        pkg_info = self.db.get_pkg(pkg_name)
        if not pkg_info:
            logger.error(f"包 {pkg_name} 不在数据库中")
            sys.exit(1)
        exec_rel = pkg_info.get('Exec')
        if not exec_rel:
            logger.error(f"包 {pkg_name} 没有 Exec 字段")
            sys.exit(1)
        # Exec 可能是相对于安装目录的路径，我们尝试在 bin 目录中查找
        exec_path = os.path.join(self.bin_dir, os.path.basename(exec_rel))
        if not os.path.exists(exec_path):
            # 也许直接就是绝对路径？
            exec_path = exec_rel
        if not os.path.exists(exec_path):
            logger.error(f"可执行文件不存在: {exec_path}")
            sys.exit(1)
        # 直接执行（替换当前进程）
        os.execv(exec_path, [exec_path] + sys.argv[2:])  # 注意原参数


# ---------- 命令行解析 ----------
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="TouchFish Version Manager",
        prog="tfvm"
    )
    parser.add_argument('-v', '--version', action='version', version=VERSION)

    # 主操作组（互斥）
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-S', '--install', nargs='+', metavar='PKG', help='安装一个或多个包')
    group.add_argument('-R', '--remove', nargs='+', metavar='PKG', help='卸载一个或多个包')
    group.add_argument('-Q', '--query', nargs='?', const='all', metavar='PKG', help='查询包信息（不指定则列出所有）')
    group.add_argument('--sync', action='store_true', help='仅同步数据库（-Sy）')
    group.add_argument('-Su', '--upgrade', nargs='*', metavar='PKG', help='升级指定包（不指定则升级所有）')
    group.add_argument('-Sc', '--clean', action='store_true', help='清理下载缓存')
    # 启动模式：直接给出包名（无选项）
    parser.add_argument('launch', nargs='?', metavar='PKG', help='启动已安装的包')

    # 额外选项（模拟 pacman 的 -y、-c 等组合）
    parser.add_argument('-y', '--refresh', action='store_true', help='安装/升级前强制同步数据库')
    parser.add_argument('-c', '--clean-cache', action='store_true', help='安装时同时清理缓存')

    args = parser.parse_args()

    # 如果没有任何操作，显示帮助
    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(0)

    # 延迟加载配置和管理器（避免提前创建配置文件）
    manager = TfvmManager()

    # 处理操作
    if args.install:
        if args.refresh:
            manager.sync_db()
        if args.clean_cache:
            manager.clean_cache()
        manager.install(args.install, {})
    elif args.remove:
        manager.remove(args.remove)
    elif args.query is not None:
        if args.query == 'all':
            manager.query()
        else:
            manager.query(args.query)
    elif args.sync:
        manager.sync_db()
    elif args.upgrade is not None:
        if args.refresh:
            manager.sync_db()
        manager.upgrade(args.upgrade if args.upgrade else None)
    elif args.clean:
        manager.clean_cache()
    elif args.launch:
        manager.launch(args.launch)
    else:
        # 理论上不会到这里
        parser.print_help()

if __name__ == "__main__":
    main()
