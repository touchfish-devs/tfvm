MSG = {
    # 通用
    'loading_config': '正在加载配置...',
    'syncing_db': '正在同步软件包数据库: {}',
    'db_sync_complete': '数据库同步完成，共 {} 个软件包。',
    'added_tfvm_default': '已添加默认 tfvm 包到数据库。',
    'pkg_up_to_date': '包 {} 已是最新版本 {}。',
    'upgrading_pkg': '升级包 {}: {} -> {}',
    'removed_symlink': '已删除旧符号链接: {}',
    'removed_install_dir': '已删除旧安装目录: {}',
    'pkg_install_complete': '包 {} 安装完成。',
    'using_cache': '使用缓存: {}',
    'downloading': '正在下载: {}',
    'download_complete': '下载完成: {}',
    'download_failed': '下载失败: {}',
    'extracting': '正在解压: {} -> {}',
    'extract_failed': '解压失败: {}',
    'missing_tool': '缺少必要的解压工具: {}',
    'conflict_check': '包 {}: {}',
    'conflict_list': '以下包与现有文件冲突，无法安装：',
    'warning_list': '以下包存在路径冲突，建议处理：',
    'processing_pkgs': '将处理以下包: {}',
    'confirm_continue': '确认继续吗？(Y/n): ',
    'operation_cancelled': '操作已取消。',
    'phase1_download': '阶段 1/2: 下载所有包文件...',
    'phase1_done': '所有包下载完成。',
    'phase2_install': '阶段 2/2: 安装/升级所有包...',
    'no_pkgs_to_process': '没有需要处理的新包或更新包。',
    'pkg_not_in_db': '包 {} 不存在于数据库。',
    'pkg_not_installed': '包 {} 未安装。',
    'pkg_already_installed': '包 {} 已安装。',
    'no_installed_pkgs': '没有已安装的包。',
    'no_upgradable_pkgs': '所有已安装包都是最新的。',
    'upgradable_list_header': '将更新以下包：',
    'exclude_prompt': '输入要排除的包序号（空格分隔，如 "0 1 6 15"），输入 "b" 排除所有 build 包，直接回车全部更新：',
    'excluded_pkgs': '已排除更新包: {}',
    'no_pkgs_left': '没有剩余包需要更新。',
    'registry_updated': 'registry 已更新为: {}',
    'proxy_set': 'proxy 已设置为: {}',
    'proxy_cleared': 'proxy 已清除（不使用代理）。',
    'proxy_used': '使用代理: {}',
    'symlink_created': '已创建符号链接: {}',
    'db_moved': '数据库文件已移动到: {}',
    'db_moved_success': '数据库文件已转移。',
    'cache_cleared': '缓存已清理（所有文件）。',
    'cache_purged': '缓存已完全清空。',
    'tfvm_self_upgraded': 'tfvm 已升级到最新版本，请重新运行命令以应用更新。',
    'unknown_config_subcmd': '未知配置子命令: {}',
    'missing_registry_url': '缺少 registry URL。',
    'missing_target_dir': '缺少目标目录。',
    'dir_create_fail': '无法创建目录 {}: {}',
    'no_db_files': '数据库文件不存在，无需移动。',
    'help_text': """TouchFish 版本管理器 (tfvm) v{version}

用法: tfvm <操作> [选项] [目标]

操作:
  -Q, --query         查询本地数据库（已安装包）
  -R, --remove        移除软件包
  -S, --sync          同步/安装软件包
  -C, --config        配置管理（后接子命令）
  -U, --publish       发布软件包到数据库

配置子命令 (-C):
  -Cr <url>           修改远程数据库地址
  -Cp <proxy>         修改代理前缀（设为空字符串清除代理）
  -Ct <目录>          移动本地数据库文件到新目录

发布子命令 (-U):
  -Ui                 发布并安装
  -Us                 仅输出 YAML（不修改数据库）
  (无子命令)          仅发布到数据库（交互式）

查询选项 (-Q):
  -i, --info          显示包的详细信息
  -s, --search <表达式> 搜索已安装的包（支持正则）
  -l, --list          列出包安装的所有文件
  -u, --upgrades      列出所有可更新的包
  -q, --quiet         精简输出

移除选项 (-R):
  -c, --cascade       级联删除（移除目标包及依赖它们的包）
  -s, --recursive     递归删除（移除不被需要的依赖）
  -n, --nosave        移除时不保留配置文件

同步选项 (-S):
  -y, --refresh       刷新同步数据库
  -c, --clean         清理缓存（一次删除未安装包，两次清空全部）
  -u, --sysupgrade    升级模式（仅升级已安装包，未安装则报错）
  -i, --info          显示远程仓库包的详细信息（未实现）
  -s, --search <表达式> 在远程仓库中搜索包（未实现）
  -q, --quiet         精简输出

发布选项:
  --depends <依赖>     添加依赖（可多次）
  --provides <提供>   添加提供的虚拟包（可多次）

示例:
  tfvm -S touchfish              安装/升级 touchfish
  tfvm -Syu                      同步数据库并升级所有包（可交互排除）
  tfvm -S -u touchfish           仅升级 touchfish（必须已安装）
  tfvm -Cr https://new.repo/db.yml  修改仓库地址
  tfvm -Cp ""                    禁用代理
  tfvm -Ct /new/db/path          移动数据库文件
  tfvm touchfish                 启动已安装的包
  tfvm -Ui ./pkg.tar.gz mypkg    发布并安装 mypkg
  tfvm -Us ./pkg.tar.gz mypkg "我的应用" 1.0 1 > BUILD.yml
""",
    'query_upgradable_header': '可更新的包：',
    'query_search_not_found': '未找到匹配的包。',
    'query_list_files_title': '包 {} 安装文件列表：',
    'query_list_files_not_installed': '包 {} 未安装。',
    'query_list_files_need_pkg': '列出文件需要指定包名。',
    'query_info_need_pkg': '显示详细信息需要指定包名。',
    'query_pkg_not_found': '包 {} 不存在。',
    'query_pkg_info_header': '名称: {}\n全名: {}\n说明: {}\n版本: {}\n发布号: {}\n状态: {}',
    'query_pkg_install_dir': '安装目录: {}',
    'query_pkg_symlink': '符号链接: {}',
    'query_pkg_status_installed': '已安装',
    'query_pkg_status_not_installed': '未安装',
    'remove_cascade_warning': '级联删除功能暂未完全实现，将只卸载目标包及其直接依赖（如果有）。',
    'remove_recursive_warning': '递归删除功能暂未完全实现，将只卸载目标包本身。',
    'remove_not_installed': '包 {} 未安装。',
    'remove_symlink_deleted': '已删除符号链接: {}',
    'remove_dir_deleted': '已删除安装目录: {}',
    'remove_complete': '包 {} 已卸载。',
    'launch_not_installed': '包 {} 未安装。',
    'launch_exec_not_found': '可执行文件不存在或不可执行: {}',
    'config_change_success': '配置更新成功。',
    'error_only_one_operation': '只能指定一个操作。',
    'error_unknown_op': '未知操作: -{}',
    'error_invalid_char': '无效字符: {}',
    'error_s_needs_arg': '-s 选项需要参数。',
    'error_missing_config_subcmd': '-C 需要子命令 (r/p/t)。',
    'error_launch_missing_pkg': '未指定要启动的包。',
    'error_remove_missing_pkg': '未指定要卸载的包。',
    'error_unknown_op_final': '未知操作: {}',

    # 新增发布相关
    'publish_missing_fullname': '全名 (Name) [包名]: ',
    'publish_missing_version': '版本 (Version) [1.0.0]: ',
    'publish_missing_release': '发布号 (Release) [1]: ',
    'publish_missing_comment': '描述 (Comment) []: ',
    'publish_missing_exec': '可执行文件路径 (Exec) [包名]: ',
    'publish_missing_binary': '需要可执行权限的文件列表 (Binary, 空格分隔) []: ',
    'publish_missing_depends': '依赖 (Depends, 空格分隔) []: ',
    'publish_missing_provides': '提供的虚拟包 (Provides, 空格分隔) []: ',
    'publish_downloading': '下载包文件到: {}',
    'publish_file_not_exist': '包文件不存在: {}',
    'publish_added_to_db': '包 {} 已添加到数据库。',
    'publish_installing': '正在安装已发布的包...',
    'publish_output_yaml': 'YAML 输出:',
    'publish_missing_pkgfile': '需要包文件 (pkgfile)。',
    'publish_missing_pkgname': '需要包名 (pkgname)。',
    'publish_invalid_subcmd': '无效子命令: {}',
    'publish_interactive_prompt': '交互式输入（回车跳过或使用默认值）：',

    # 安装过程中的错误信息
    'pkg_missing_version': '包 {} 没有 Version 字段。',
    'pkg_missing_registry': '包 {} 没有 Registry 字段。',
    'exec_file_not_exists': 'Exec 文件不存在: {}',
    'symlink_creation_failed': '创建符号链接失败: {} -> {}',
    'binary_missing': 'Binary 文件不存在: {}',
    'chmod_failed': '设置可执行权限失败: {}',
    'cache_file_missing': '缓存文件缺失: {}，请先执行下载阶段。',
    'sudo_required': '此操作需要 root 权限 (sudo)。',
    'noconfirm_enabled': '--noconfirm 已启用，自动确认。',
}
def _(key):
    return MSG.get(key, key)
