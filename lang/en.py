MSG = {
    # 通用
    'loading_config': 'Loading configuration...',
    'syncing_db': 'Syncing package database: {}',
    'db_sync_complete': 'Database sync completed, {} packages total.',
    'added_tfvm_default': 'Added default tfvm package to database.',
    'pkg_up_to_date': 'Package {} is already up to date version {}.',
    'upgrading_pkg': 'Upgrading package {}: {} -> {}',
    'removed_symlink': 'Removed old symlink: {}',
    'removed_install_dir': 'Removed old install directory: {}',
    'pkg_install_complete': 'Package {} installed successfully.',
    'using_cache': 'Using cache: {}',
    'downloading': 'Downloading: {}',
    'download_complete': 'Download complete: {}',
    'download_failed': 'Download failed: {}',
    'extracting': 'Extracting: {} -> {}',
    'extract_failed': 'Extraction failed: {}',
    'missing_tool': 'Missing necessary extraction tool: {}',
    'conflict_check': 'Package {}: {}',
    'conflict_list': 'The following packages conflict with existing files and cannot be installed:',
    'warning_list': 'The following packages have path conflicts, it is recommended to handle them:',
    'processing_pkgs': 'Will process the following packages: {}',
    'confirm_continue': 'Confirm to continue? (Y/n): ',
    'operation_cancelled': 'Operation cancelled.',
    'phase1_download': 'Phase 1/2: Downloading all package files...',
    'phase1_done': 'All packages downloaded.',
    'phase2_install': 'Phase 2/2: Installing/Upgrading all packages...',
    'no_pkgs_to_process': 'No new or updated packages to process.',
    'pkg_not_in_db': 'Package {} does not exist in database.',
    'pkg_not_installed': 'Package {} is not installed.',
    'pkg_already_installed': 'Package {} is already installed.',
    'no_installed_pkgs': 'No installed packages.',
    'no_upgradable_pkgs': 'All installed packages are up to date.',
    'upgradable_list_header': 'The following packages will be updated:',
    'exclude_prompt': 'Enter package numbers to exclude (space-separated, e.g. "0 1 6 15"), "b" to exclude all build packages, or press Enter to update all: ',
    'excluded_pkgs': 'Excluded update packages: {}',
    'no_pkgs_left': 'No packages left to update.',
    'registry_updated': 'Registry updated to: {}',
    'proxy_set': 'Proxy set to: {}',
    'proxy_cleared': 'Proxy cleared (no proxy used).',
    'proxy_used': 'Using proxy: {}',
    'symlink_created': 'Created symbolic link: {}',
    'db_moved': 'Moved database files to: {}',
    'db_moved_success': 'Database files moved successfully.',
    'cache_cleared': 'Cache cleared (all files).',
    'cache_purged': 'Cache purged completely.',
    'tfvm_self_upgraded': 'tfvm has been upgraded to latest version, please re-run command to apply changes.',
    'unknown_config_subcmd': 'Unknown config subcommand: {}',
    'missing_registry_url': 'Missing registry URL.',
    'missing_target_dir': 'Missing target directory.',
    'dir_create_fail': 'Cannot create directory {}: {}',
    'no_db_files': 'Database files do not exist, no need to move.',
    'help_text': """TouchFish Version Manager (tfvm) v{version}

Usage: tfvm <operation> [options] [targets]

Operations:
  -Q, --query         Query local database (installed packages)
  -R, --remove        Remove packages
  -S, --sync          Sync/Install packages
  -C, --config        Configuration management (with subcommands)
  -U, --publish       Publish a package to the database

Config subcommands (-C):
  -Cr <url>           Change remote database URL
  -Cp <proxy>         Set proxy prefix (empty to disable)
  -Ct <dir>           Move local database files to new directory

Publish subcommands (-U):
  -Ui                 Publish and install
  -Us                 Publish and output YAML only
  (no subcmd)         Publish to database only (interactive)

Query options (-Q):
  -i, --info          Show detailed package info
  -s, --search <expr> Search installed packages (regex)
  -l, --list          List files installed by a package
  -u, --upgrades      List packages that can be upgraded
  -q, --quiet         Quiet output

Remove options (-R):
  -c, --cascade       Cascade remove (also remove dependents)
  -s, --recursive     Recursive remove (remove unneeded dependencies)
  -n, --nosave        Do not keep config files

Sync options (-S):
  -y, --refresh       Refresh database
  -c, --clean         Clean cache (once: remove uninstalled; twice: purge all)
  -u, --sysupgrade    Upgrade mode (only upgrade installed packages)
  -i, --info          Show remote package info (not yet implemented)
  -s, --search <expr> Search remote packages (not yet implemented)
  -q, --quiet         Quiet output

Publish options:
  --depends <dep>     Add a dependency (can be repeated)
  --provides <prov>   Add a provides (can be repeated)

Examples:
  tfvm -S touchfish              Install/upgrade touchfish
  tfvm -Syu                      Sync and upgrade all packages (interactive exclusion)
  tfvm -S -u touchfish           Upgrade only touchfish (must be installed)
  tfvm -Cr https://new.repo/db.yml  Change registry
  tfvm -Cp ""                    Disable proxy
  tfvm -Ct /new/db/path          Move database files
  tfvm touchfish                 Launch installed package
  tfvm -Ui ./pkg.tar.gz mypkg    Publish and install mypkg
  tfvm -Us ./pkg.tar.gz mypkg "My App" 1.0 1 > BUILD.yml
""",
    'query_upgradable_header': 'Upgradable packages:',
    'query_search_not_found': 'No matching packages found.',
    'query_list_files_title': 'File list for package {}:',
    'query_list_files_not_installed': 'Package {} is not installed.',
    'query_list_files_need_pkg': 'Listing files requires a package name.',
    'query_info_need_pkg': 'Showing detailed info requires a package name.',
    'query_pkg_not_found': 'Package {} not found.',
    'query_pkg_info_header': 'Name: {}\nFull name: {}\nDescription: {}\nVersion: {}\nRelease: {}\nStatus: {}',
    'query_pkg_install_dir': 'Install directory: {}',
    'query_pkg_symlink': 'Symbolic link: {}',
    'query_pkg_status_installed': 'Installed',
    'query_pkg_status_not_installed': 'Not installed',
    'remove_cascade_warning': 'Cascade removal is not fully implemented; will only remove target package and its direct dependencies (if any).',
    'remove_recursive_warning': 'Recursive removal is not fully implemented; will only remove target package itself.',
    'remove_not_installed': 'Package {} is not installed.',
    'remove_symlink_deleted': 'Removed symlink: {}',
    'remove_dir_deleted': 'Removed install directory: {}',
    'remove_complete': 'Package {} removed.',
    'launch_not_installed': 'Package {} is not installed.',
    'launch_exec_not_found': 'Executable not found or not executable: {}',
    'config_change_success': 'Configuration updated successfully.',
    'error_only_one_operation': 'Only one operation can be specified.',
    'error_unknown_op': 'Unknown operation: -{}',
    'error_invalid_char': 'Invalid character: {}',
    'error_s_needs_arg': '-s option requires an argument.',
    'error_missing_config_subcmd': '-C requires a subcommand (r/p/t).',
    'error_launch_missing_pkg': 'No package specified to launch.',
    'error_remove_missing_pkg': 'No package specified to remove.',
    'error_unknown_op_final': 'Unknown operation: {}',

    # 新增发布相关
    'publish_missing_fullname': 'Full name (Name) [package name]: ',
    'publish_missing_version': 'Version [1.0.0]: ',
    'publish_missing_release': 'Release number [1]: ',
    'publish_missing_comment': 'Description (Comment) []: ',
    'publish_missing_exec': 'Executable path (Exec) [package name]: ',
    'publish_missing_binary': 'List of binaries needing executable permission (Binary, space separated) []: ',
    'publish_missing_depends': 'Dependencies (Depends, space separated) []: ',
    'publish_missing_provides': 'Provided virtual packages (Provides, space separated) []: ',
    'publish_downloading': 'Downloading package file to: {}',
    'publish_file_not_exist': 'Package file does not exist: {}',
    'publish_added_to_db': 'Package {} added to database.',
    'publish_installing': 'Installing published package...',
    'publish_output_yaml': 'YAML output:',
    'publish_missing_pkgfile': 'Package file (pkgfile) is required.',
    'publish_missing_pkgname': 'Package name (pkgname) is required.',
    'publish_invalid_subcmd': 'Invalid subcommand: {}',
    'publish_interactive_prompt': 'Interactive input (press Enter to skip or use default):',

    # 安装过程中的错误信息
    'pkg_missing_version': 'Package {} has no Version field.',
    'pkg_missing_registry': 'Package {} has no Registry field.',
    'exec_file_not_exists': 'Exec file does not exist: {}',
    'symlink_creation_failed': 'Failed to create symbolic link: {} -> {}',
    'binary_missing': 'Binary file does not exist: {}',
    'chmod_failed': 'Failed to set executable permission: {}',
    'cache_file_missing': 'Cache file missing: {}, please run download phase first.',
    'sudo_required': 'This operation requires root privileges (sudo).',
    'noconfirm_enabled': '--noconfirm enabled, auto-confirming.',
}
def _(key):
    return MSG.get(key, key)
