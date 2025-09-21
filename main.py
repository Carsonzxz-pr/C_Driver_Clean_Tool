#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C盘自动清理工具
作者: Assistant
时间: 2025-09-21
版本: 1.1.0

功能说明:
- 自动执行Windows磁盘清理（相当于cleanmgr）
- 清理系统临时文件、缓存文件等
- 提供图形界面和命令行两种使用方式
- 支持清理前预览和确认机制
"""

import os
import sys
import subprocess
import tempfile
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
import json
from datetime import datetime


class CDiskCleaner:
    """C盘清理工具主类"""
    
    def __init__(self):
        """初始化清理器"""
        self.cleanup_paths = [
            {
                "name": "临时文件夹",
                "path": os.environ.get('TEMP', r'C:\Windows\Temp'),
                "description": "系统和用户临时文件"
            },
            {
                "name": "Windows临时文件",
                "path": r'C:\Windows\Temp',
                "description": "Windows系统临时文件"
            },
            {
                "name": "用户临时文件",
                "path": os.path.expanduser(r'~\AppData\Local\Temp'),
                "description": "当前用户临时文件"
            },
            {
                "name": "回收站",
                "path": r'C:\$Recycle.Bin',
                "description": "回收站文件（需要管理员权限）"
            },
            {
                "name": "Windows更新缓存",
                "path": r'C:\Windows\SoftwareDistribution\Download',
                "description": "Windows更新下载缓存"
            },
            {
                "name": "预读取文件",
                "path": r'C:\Windows\Prefetch',
                "description": "系统预读取缓存文件"
            },
            {
                "name": "IIS日志",
                "path": r'C:\inetpub\logs\LogFiles',
                "description": "IIS Web服务器日志文件"
            },
            {
                "name": "浏览器缓存",
                "path": os.path.expanduser(r'~\AppData\Local\Microsoft\Windows\INetCache'),
                "description": "Internet Explorer缓存文件"
            }
        ]
        
        self.total_size = 0
        self.cleaned_size = 0
        self.errors = []
        
    def get_folder_size(self, folder_path):
        """计算文件夹大小"""
        total_size = 0
        try:
            if os.path.exists(folder_path):
                for dirpath, dirnames, filenames in os.walk(folder_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                        except (OSError, FileNotFoundError):
                            continue
        except Exception as e:
            self.errors.append(f"计算文件夹大小失败 {folder_path}: {str(e)}")
        return total_size
    
    def format_size(self, size_bytes):
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"
    
    def scan_cleanup_targets(self):
        """扫描清理目标，返回可清理的项目和大小"""
        cleanup_info = []
        self.total_size = 0
        
        for item in self.cleanup_paths:
            if os.path.exists(item["path"]):
                size = self.get_folder_size(item["path"])
                if size > 0:
                    cleanup_info.append({
                        "name": item["name"],
                        "path": item["path"],
                        "description": item["description"],
                        "size": size,
                        "size_str": self.format_size(size)
                    })
                    self.total_size += size
        
        return cleanup_info
    
    def clean_folder_fast(self, folder_path, progress_callback=None):
        """快速清理指定文件夹 - 使用系统命令批量删除"""
        cleaned_size = 0
        
        try:
            if not os.path.exists(folder_path):
                return cleaned_size
            
            # 先计算要删除的总大小
            size_before = self.get_folder_size(folder_path)
            if progress_callback:
                progress_callback(f"扫描完成: {os.path.basename(folder_path)} - {self.format_size(size_before)}")
            
            if size_before == 0:
                return 0
            
            # 方法1: 使用Windows原生命令快速删除
            if self.fast_delete_with_cmd(folder_path, progress_callback):
                # 计算清理后的实际大小
                size_after = 0
                if os.path.exists(folder_path):
                    size_after = self.get_folder_size(folder_path)
                cleaned_size = size_before - size_after
            else:
                # 方法2: 如果命令失败，使用优化的Python删除
                cleaned_size = self.clean_folder_optimized(folder_path, progress_callback)
            
            if progress_callback and cleaned_size > 0:
                progress_callback(f"✓ 清理完成: {os.path.basename(folder_path)} - 释放 {self.format_size(cleaned_size)}")
                
        except Exception as e:
            self.errors.append(f"清理文件夹失败 {folder_path}: {str(e)}")
        
        return cleaned_size
    
    def fast_delete_with_cmd(self, folder_path, progress_callback=None):
        """使用Windows命令行快速删除文件夹内容"""
        try:
            # 构建安全的路径
            safe_path = os.path.abspath(folder_path)
            
            # 确保路径存在且是目录
            if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
                return False
            
            # 先计算文件夹大小来估算超时时间
            folder_size = self.get_folder_size(safe_path)
            timeout_seconds = max(60, min(300, folder_size // (50 * 1024 * 1024) * 30))  # 每50MB给30秒
            
            if progress_callback:
                progress_callback(f"批量删除: {os.path.basename(safe_path)} (预计{timeout_seconds}秒)")
            
            try:
                # 使用del命令删除所有文件（包括隐藏文件和只读文件）
                cmd_files = f'del /f /s /q "{safe_path}\\*.*"'
                result_files = subprocess.run(cmd_files, shell=True, capture_output=True, text=True, timeout=timeout_seconds)
                
                # 使用rmdir命令删除空文件夹
                cmd_dirs = f'for /d %i in ("{safe_path}\\*") do rmdir /s /q "%i"'
                result_dirs = subprocess.run(cmd_dirs, shell=True, capture_output=True, text=True, timeout=60)
                
                # 检查是否成功
                if progress_callback:
                    progress_callback(f"✓ 批量删除完成: {os.path.basename(safe_path)}")
                return True
                
            except subprocess.TimeoutExpired:
                if progress_callback:
                    progress_callback(f"⏰ 批量删除超时: {os.path.basename(safe_path)}")
                return False
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ 批量删除失败: {os.path.basename(folder_path)}")
            return False
    
    def clean_folder_optimized(self, folder_path, progress_callback=None):
        """优化的Python文件删除方法"""
        cleaned_size = 0
        file_count = 0
        
        try:
            if not os.path.exists(folder_path):
                return cleaned_size
            
            # 批量收集文件信息，减少磁盘I/O
            files_to_delete = []
            dirs_to_delete = []
            
            for root, dirs, files in os.walk(folder_path, topdown=False):
                # 收集文件
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        files_to_delete.append((file_path, file_size))
                    except:
                        pass
                
                # 收集空目录
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    dirs_to_delete.append(dir_path)
            
            # 批量删除文件
            total_files = len(files_to_delete)
            for i, (file_path, file_size) in enumerate(files_to_delete):
                try:
                    os.remove(file_path)
                    cleaned_size += file_size
                    file_count += 1
                    
                    # 每100个文件更新一次进度（减少UI更新频率）
                    if file_count % 100 == 0 and progress_callback:
                        progress_callback(f"已删除 {file_count}/{total_files} 个文件...")
                        
                except Exception as e:
                    self.errors.append(f"无法删除文件 {file_path}: {str(e)}")
            
            # 批量删除空目录
            for dir_path in dirs_to_delete:
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except:
                    pass
            
            if progress_callback:
                progress_callback(f"完成清理，共删除 {file_count} 个文件")
                        
        except Exception as e:
            self.errors.append(f"清理文件夹失败 {folder_path}: {str(e)}")
        
        return cleaned_size
    
    def clean_folder(self, folder_path, progress_callback=None):
        """清理指定文件夹（保持向后兼容）"""
        return self.clean_folder_fast(folder_path, progress_callback)
    
    def run_disk_cleanup(self, progress_callback=None):
        """运行Windows磁盘清理工具"""
        try:
            if progress_callback:
                progress_callback("正在启动Windows系统磁盘清理...")
            
            # 方法1: 尝试使用cleanmgr的自动模式
            try:
                result = subprocess.run([
                    'cleanmgr', '/d', 'C:', '/verylowdisk'
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    if progress_callback:
                        progress_callback("✓ Windows系统磁盘清理完成")
                    return True
            except:
                pass
            
            # 方法2: 使用基本的cleanmgr命令
            try:
                if progress_callback:
                    progress_callback("使用基础磁盘清理命令...")
                
                result = subprocess.run([
                    'cleanmgr', '/d', 'C:'
                ], capture_output=True, text=True, timeout=60)
                
                if progress_callback:
                    progress_callback("✓ 磁盘清理工具已启动")
                return True
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"磁盘清理工具启动失败: {str(e)}")
                self.errors.append(f"启动磁盘清理工具失败: {str(e)}")
                return False
                
        except Exception as e:
            self.errors.append(f"磁盘清理失败: {str(e)}")
            return False
    
    def perform_cleanup(self, selected_items, progress_callback=None):
        """执行清理操作 - 优化版本"""
        self.cleaned_size = 0
        self.errors = []
        
        # 首先运行系统磁盘清理（异步执行）
        if progress_callback:
            progress_callback("正在启动系统磁盘清理...")
        
        # 使用线程池并行清理多个文件夹
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        # 启动系统清理（在后台运行）
        cleanup_thread = threading.Thread(target=self.run_disk_cleanup, args=(progress_callback,))
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        # 并行清理自定义路径
        if progress_callback:
            progress_callback(f"开始并行清理 {len(selected_items)} 个项目...")
        
        def clean_single_item(item):
            """清理单个项目"""
            try:
                if progress_callback:
                    progress_callback(f"正在处理: {item['name']}")
                
                cleaned = self.clean_folder_fast(item['path'], progress_callback)
                return item['name'], cleaned, None
            except Exception as e:
                return item['name'], 0, str(e)
        
        # 使用线程池并行处理（最多4个线程，避免磁盘I/O冲突）
        max_workers = min(4, len(selected_items))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有清理任务
            future_to_item = {executor.submit(clean_single_item, item): item for item in selected_items}
            
            # 收集结果
            completed_count = 0
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    name, cleaned, error = future.result()
                    if error:
                        self.errors.append(f"清理 {name} 失败: {error}")
                    else:
                        self.cleaned_size += cleaned
                        if progress_callback:
                            progress_callback(f"✓ 完成清理: {name}")
                    
                    completed_count += 1
                    if progress_callback:
                        progress_callback(f"进度: {completed_count}/{len(selected_items)} 项目完成")
                        
                except Exception as e:
                    self.errors.append(f"处理 {item['name']} 时出错: {str(e)}")
        
        # 等待系统清理完成（最多等待30秒）
        if progress_callback:
            progress_callback("等待系统磁盘清理完成...")
        
        cleanup_thread.join(timeout=30)
        if cleanup_thread.is_alive():
            if progress_callback:
                progress_callback("系统磁盘清理仍在进行中...")
        
        return self.cleaned_size, self.errors
    
    def perform_cleanup_ultra_fast(self, selected_items, progress_callback=None):
        """超快速清理模式 - 使用Windows原生工具"""
        self.cleaned_size = 0
        self.errors = []
        
        if progress_callback:
            progress_callback("启动超快速清理模式...")
        
        try:
            # 先计算清理前的总大小
            if progress_callback:
                progress_callback("计算清理前文件大小...")
            
            total_size_before = 0
            existing_paths = []
            
            for item in selected_items:
                path = item['path']
                if os.path.exists(path):
                    size_before = self.get_folder_size(path)
                    total_size_before += size_before
                    existing_paths.append((item, path, size_before))
                    if progress_callback:
                        progress_callback(f"扫描: {item['name']} - {self.format_size(size_before)}")
            
            if not existing_paths:
                if progress_callback:
                    progress_callback("没有找到需要清理的文件")
                return 0, []
            
            if progress_callback:
                progress_callback(f"开始清理，总大小: {self.format_size(total_size_before)}")
            
            # 使用Windows命令逐个清理文件夹
            for item, path, size_before in existing_paths:
                if progress_callback:
                    progress_callback(f"正在清理: {item['name']}")
                
                try:
                    # 根据文件大小动态设置超时时间
                    timeout_seconds = max(60, min(300, size_before // (100 * 1024 * 1024) * 30))  # 每100MB给30秒，最少60秒，最多300秒
                    
                    if progress_callback:
                        progress_callback(f"开始删除文件: {item['name']} (预计 {timeout_seconds}秒)")
                    
                    # 使用del命令删除文件
                    cmd1 = f'del /f /s /q "{path}\\*.*"'
                    result1 = subprocess.run(cmd1, shell=True, capture_output=True, text=True, timeout=timeout_seconds)
                    
                    if progress_callback:
                        progress_callback(f"正在删除子文件夹: {item['name']}")
                    
                    # 使用for循环删除子文件夹
                    cmd2 = f'for /d %i in ("{path}\\*") do @rmdir /s /q "%i"'
                    result2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True, timeout=60)
                    
                    # 计算清理后的大小
                    if progress_callback:
                        progress_callback(f"验证清理结果: {item['name']}")
                    
                    size_after = 0
                    if os.path.exists(path):
                        size_after = self.get_folder_size(path)
                    
                    cleaned_this_item = size_before - size_after
                    self.cleaned_size += cleaned_this_item
                    
                    if progress_callback:
                        if cleaned_this_item > 0:
                            progress_callback(f"✓ 完成: {item['name']} - 清理了 {self.format_size(cleaned_this_item)}")
                        else:
                            progress_callback(f"⚠ {item['name']} - 没有文件需要清理")
                        
                except subprocess.TimeoutExpired:
                    # 超时时尝试fallback到标准模式
                    if progress_callback:
                        progress_callback(f"⏰ {item['name']} 清理超时，尝试标准方式...")
                    
                    try:
                        # 使用标准Python方式清理这个项目
                        cleaned_fallback = self.clean_folder_optimized(path, progress_callback)
                        self.cleaned_size += cleaned_fallback
                        if progress_callback:
                            progress_callback(f"✓ 标准方式完成: {item['name']} - 清理了 {self.format_size(cleaned_fallback)}")
                    except Exception as fallback_e:
                        self.errors.append(f"清理 {item['name']} 超时且fallback失败: {str(fallback_e)}")
                        
                except Exception as e:
                    if progress_callback:
                        progress_callback(f"❌ {item['name']} 清理失败，尝试标准方式...")
                    
                    try:
                        # 出错时也尝试fallback到标准模式
                        cleaned_fallback = self.clean_folder_optimized(path, progress_callback)
                        self.cleaned_size += cleaned_fallback
                        if progress_callback:
                            progress_callback(f"✓ 标准方式完成: {item['name']} - 清理了 {self.format_size(cleaned_fallback)}")
                    except Exception as fallback_e:
                        self.errors.append(f"清理 {item['name']} 失败: {str(e)}, fallback也失败: {str(fallback_e)}")
            
            if progress_callback:
                progress_callback(f"超快速清理完成! 总共释放: {self.format_size(self.cleaned_size)}")
                
        except Exception as e:
            self.errors.append(f"超快速清理失败: {str(e)}")
            if progress_callback:
                progress_callback("超快速清理失败，切换到标准模式...")
            # fallback到普通清理模式
            return self.perform_cleanup(selected_items, progress_callback)
        
        return self.cleaned_size, self.errors
    
    def perform_cleanup_smart(self, selected_items, progress_callback=None):
        """智能清理模式 - 根据文件大小自动选择最佳清理方式"""
        self.cleaned_size = 0
        self.errors = []
        
        if progress_callback:
            progress_callback("启动智能清理模式...")
        
        try:
            # 首先启动系统清理（在后台运行）
            cleanup_thread = threading.Thread(target=self.run_disk_cleanup, args=(progress_callback,))
            cleanup_thread.daemon = True
            cleanup_thread.start()
            
            # 分析各个清理项目的大小，决定使用哪种清理方式
            small_items = []  # 小文件夹用标准模式
            large_items = []  # 大文件夹用超快速模式
            
            for item in selected_items:
                if not os.path.exists(item['path']):
                    continue
                    
                size = item.get('size', 0)
                if size > 500 * 1024 * 1024:  # 大于500MB用超快速模式
                    large_items.append(item)
                else:
                    small_items.append(item)
            
            if progress_callback:
                progress_callback(f"智能分析: {len(large_items)}个大项目用超快速模式, {len(small_items)}个小项目用标准模式")
            
            # 先处理大文件夹（超快速模式）
            for item in large_items:
                if progress_callback:
                    progress_callback(f"超快速清理: {item['name']}")
                
                try:
                    path = item['path']
                    size_before = self.get_folder_size(path)
                    
                    # 动态超时时间
                    timeout_seconds = max(60, min(300, size_before // (100 * 1024 * 1024) * 30))
                    
                    # 使用Windows命令清理
                    cmd = f'del /f /s /q "{path}\\*.*" && for /d %i in ("{path}\\*") do @rmdir /s /q "%i"'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_seconds)
                    
                    # 计算清理效果
                    size_after = self.get_folder_size(path) if os.path.exists(path) else 0
                    cleaned = size_before - size_after
                    self.cleaned_size += cleaned
                    
                    if progress_callback:
                        progress_callback(f"✓ 超快速完成: {item['name']} - {self.format_size(cleaned)}")
                        
                except subprocess.TimeoutExpired:
                    if progress_callback:
                        progress_callback(f"⏰ {item['name']} 超时，切换到标准模式...")
                    # 超时则用标准模式
                    cleaned = self.clean_folder_optimized(path, progress_callback)
                    self.cleaned_size += cleaned
                    
                except Exception as e:
                    self.errors.append(f"智能清理 {item['name']} 失败: {str(e)}")
            
            # 再处理小文件夹（标准模式，并行）
            if small_items:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                
                def clean_small_item(item):
                    try:
                        cleaned = self.clean_folder_optimized(item['path'], progress_callback)
                        return item['name'], cleaned, None
                    except Exception as e:
                        return item['name'], 0, str(e)
                
                with ThreadPoolExecutor(max_workers=2) as executor:
                    future_to_item = {executor.submit(clean_small_item, item): item for item in small_items}
                    
                    for future in as_completed(future_to_item):
                        item = future_to_item[future]
                        try:
                            name, cleaned, error = future.result()
                            if error:
                                self.errors.append(f"清理 {name} 失败: {error}")
                            else:
                                self.cleaned_size += cleaned
                                if progress_callback:
                                    progress_callback(f"✓ 标准完成: {name} - {self.format_size(cleaned)}")
                        except Exception as e:
                            self.errors.append(f"处理 {item['name']} 时出错: {str(e)}")
            
            # 等待系统清理完成
            cleanup_thread.join(timeout=30)
            
            if progress_callback:
                progress_callback(f"智能清理完成! 总共释放: {self.format_size(self.cleaned_size)}")
                
        except Exception as e:
            self.errors.append(f"智能清理失败: {str(e)}")
            if progress_callback:
                progress_callback("智能清理失败，使用标准模式...")
            # fallback到标准清理模式
            return self.perform_cleanup(selected_items, progress_callback)
        
        return self.cleaned_size, self.errors


class CleanerGUI:
    """清理工具图形界面"""
    
    def __init__(self):
        """初始化GUI"""
        self.cleaner = CDiskCleaner()
        self.cleanup_items = []
        
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("C盘自动清理工具 v1.1.0")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # 设置窗口图标（如果有的话）
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        self.setup_gui()
        
    def setup_gui(self):
        """设置GUI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # 标题
        title_label = ttk.Label(main_frame, text="C盘自动清理工具", 
                               font=("微软雅黑", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # 扫描按钮
        scan_frame = ttk.Frame(main_frame)
        scan_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.scan_button = ttk.Button(scan_frame, text="扫描可清理项目", 
                                     command=self.scan_targets)
        self.scan_button.pack(side=tk.LEFT)
        
        self.scan_status = ttk.Label(scan_frame, text="点击扫描按钮开始...")
        self.scan_status.pack(side=tk.LEFT, padx=(20, 0))
        
        # 清理项目列表
        list_frame = ttk.LabelFrame(main_frame, text="可清理项目", padding="5")
        list_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 创建Treeview显示清理项目
        columns = ("name", "size", "description")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="tree headings")
        
        self.tree.heading("#0", text="选择")
        self.tree.heading("name", text="项目名称")
        self.tree.heading("size", text="大小")
        self.tree.heading("description", text="描述")
        
        self.tree.column("#0", width=60)
        self.tree.column("name", width=150)
        self.tree.column("size", width=100)
        self.tree.column("description", width=300)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 操作按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.select_all_button = ttk.Button(button_frame, text="全选", 
                                          command=self.select_all)
        self.select_all_button.pack(side=tk.LEFT)
        
        self.deselect_all_button = ttk.Button(button_frame, text="全不选", 
                                            command=self.deselect_all)
        self.deselect_all_button.pack(side=tk.LEFT, padx=(5, 0))
        
        # 清理模式选择
        mode_frame = ttk.LabelFrame(button_frame, text="清理模式", padding="2")
        mode_frame.pack(side=tk.LEFT, padx=(20, 0))
        
        self.cleanup_mode = tk.StringVar(value="smart")
        self.expert_mode = tk.BooleanVar(value=False)
        
        # 主要模式选择
        mode_smart = ttk.Radiobutton(mode_frame, text="智能清理🧠", variable=self.cleanup_mode, 
                                    value="smart")
        mode_smart.pack(side=tk.LEFT)
        
        mode_fast = ttk.Radiobutton(mode_frame, text="极速清理⚡", variable=self.cleanup_mode, 
                                   value="ultra_fast")
        mode_fast.pack(side=tk.LEFT, padx=(5, 0))
        
        # 专家模式切换
        expert_check = ttk.Checkbutton(mode_frame, text="专家", variable=self.expert_mode,
                                     command=self.toggle_expert_mode)
        expert_check.pack(side=tk.LEFT, padx=(10, 0))
        
        # 兼容模式（默认隐藏）
        self.mode_normal = ttk.Radiobutton(mode_frame, text="兼容", variable=self.cleanup_mode, 
                                         value="normal")
        
        # 模式说明
        mode_help = ttk.Label(mode_frame, text="💡", foreground="blue", cursor="hand2")
        mode_help.pack(side=tk.LEFT, padx=(5, 0))
        mode_help.bind("<Button-1>", self.show_mode_help)
        
        self.clean_button = ttk.Button(button_frame, text="开始清理", 
                                     command=self.start_cleanup, state=tk.DISABLED)
        self.clean_button.pack(side=tk.RIGHT)
        
        # 进度显示
        progress_frame = ttk.LabelFrame(main_frame, text="清理进度", padding="5")
        progress_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_var = tk.StringVar(value="准备就绪")
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # 日志显示
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="5")
        log_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
    def log_message(self, message):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def scan_targets(self):
        """扫描清理目标"""
        self.scan_button.config(state=tk.DISABLED)
        self.scan_status.config(text="正在扫描...")
        self.log_message("开始扫描可清理项目...")
        
        # 清空现有项目
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        def scan_thread():
            try:
                self.cleanup_items = self.cleaner.scan_cleanup_targets()
                
                # 更新UI（在主线程中执行）
                self.root.after(0, self.update_scan_results)
                
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"扫描失败: {str(e)}"))
            finally:
                self.root.after(0, lambda: self.scan_button.config(state=tk.NORMAL))
        
        threading.Thread(target=scan_thread, daemon=True).start()
        
    def update_scan_results(self):
        """更新扫描结果"""
        total_size = 0
        
        for i, item in enumerate(self.cleanup_items):
            # 默认选中所有项目
            self.tree.insert("", tk.END, iid=str(i), text="☑", 
                           values=(item["name"], item["size_str"], item["description"]))
            total_size += item["size"]
        
        total_size_str = self.cleaner.format_size(total_size)
        self.scan_status.config(text=f"找到 {len(self.cleanup_items)} 个项目，总计 {total_size_str}")
        self.log_message(f"扫描完成：找到 {len(self.cleanup_items)} 个可清理项目，总大小 {total_size_str}")
        
        if self.cleanup_items:
            self.clean_button.config(state=tk.NORMAL)
        
        # 绑定点击事件切换选择状态
        self.tree.bind("<Button-1>", self.on_tree_click)
        
    def on_tree_click(self, event):
        """处理树形视图点击事件"""
        item = self.tree.identify("item", event.x, event.y)
        if item:
            current_text = self.tree.item(item, "text")
            new_text = "☐" if current_text == "☑" else "☑"
            self.tree.item(item, text=new_text)
            
    def select_all(self):
        """全选所有项目"""
        for item in self.tree.get_children():
            self.tree.item(item, text="☑")
            
    def deselect_all(self):
        """取消选择所有项目"""
        for item in self.tree.get_children():
            self.tree.item(item, text="☐")
            
    def get_selected_items(self):
        """获取选中的清理项目"""
        selected = []
        for item_id in self.tree.get_children():
            if self.tree.item(item_id, "text") == "☑":
                index = int(item_id)
                selected.append(self.cleanup_items[index])
        return selected
        
    def start_cleanup(self):
        """开始清理操作"""
        selected_items = self.get_selected_items()
        
        if not selected_items:
            messagebox.showwarning("警告", "请至少选择一个要清理的项目！")
            return
        
        # 确认对话框
        total_size = sum(item["size"] for item in selected_items)
        total_size_str = self.cleaner.format_size(total_size)
        
        result = messagebox.askyesno(
            "确认清理", 
            f"您选择了 {len(selected_items)} 个项目进行清理，\n"
            f"预计可释放空间：{total_size_str}\n\n"
            f"注意：此操作不可撤销！\n"
            f"确定要继续吗？"
        )
        
        if not result:
            return
        
        # 禁用按钮，开始清理
        self.clean_button.config(state=tk.DISABLED)
        self.scan_button.config(state=tk.DISABLED)
        self.progress_bar.start()
        self.progress_var.set("正在清理...")
        
        def cleanup_thread():
            try:
                def progress_callback(message):
                    self.root.after(0, lambda: self.log_message(message))
                    self.root.after(0, lambda: self.progress_var.set(message))
                
                # 根据选择的模式执行不同的清理方法
                cleanup_mode = self.cleanup_mode.get()
                if cleanup_mode == "smart":
                    self.log_message("使用智能清理模式...")
                    cleaned_size, errors = self.cleaner.perform_cleanup_smart(selected_items, progress_callback)
                elif cleanup_mode == "ultra_fast":
                    self.log_message("使用超快速清理模式...")
                    cleaned_size, errors = self.cleaner.perform_cleanup_ultra_fast(selected_items, progress_callback)
                else:
                    self.log_message("使用标准清理模式...")
                    cleaned_size, errors = self.cleaner.perform_cleanup(selected_items, progress_callback)
                
                # 清理完成，更新UI
                self.root.after(0, lambda: self.cleanup_completed(cleaned_size, errors))
                
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"清理过程中出现错误: {str(e)}"))
            finally:
                self.root.after(0, self.cleanup_finished)
        
        threading.Thread(target=cleanup_thread, daemon=True).start()
        
    def cleanup_completed(self, cleaned_size, errors):
        """清理完成后的处理"""
        cleaned_size_str = self.cleaner.format_size(cleaned_size)
        
        self.log_message(f"清理完成！释放空间：{cleaned_size_str}")
        
        if errors:
            self.log_message(f"清理过程中遇到 {len(errors)} 个错误：")
            for error in errors[:10]:  # 只显示前10个错误
                self.log_message(f"  - {error}")
            if len(errors) > 10:
                self.log_message(f"  ... 还有 {len(errors) - 10} 个错误")
        
        # 显示完成对话框
        message = f"清理完成！\n\n释放空间：{cleaned_size_str}"
        if errors:
            message += f"\n\n注意：清理过程中遇到 {len(errors)} 个错误，\n部分文件可能由于权限或占用问题无法删除。"
        
        messagebox.showinfo("清理完成", message)
        
    def cleanup_finished(self):
        """清理结束后恢复界面"""
        self.progress_bar.stop()
        self.progress_var.set("清理完成")
        self.clean_button.config(state=tk.NORMAL)
        self.scan_button.config(state=tk.NORMAL)
        self.status_var.set("清理完成，可以重新扫描")
        
    def show_mode_help(self, event):
        """显示清理模式帮助信息"""
        help_text = """清理模式说明：

🧠 智能清理（默认推荐）：
• 程序自动选择最佳清理方式
• 大文件用极速模式，小文件用安全模式
• 智能避免各种问题，适合所有用户
• 99%的情况下这是最佳选择

⚡ 极速清理：
• 全部使用Windows批处理命令
• 速度最快，但在某些环境可能不稳定
• 适合高级用户和文件较少的情况

🔧 兼容模式（专家选项）：
• 逐个文件处理，最高兼容性
• 适用于：企业环境、老旧系统、调试问题
• 速度较慢，但几乎不会出错

❓ 为什么需要多种模式：
• 不同Windows版本和配置差异很大
• 某些杀毒软件可能阻止批处理命令
• 网络驱动器和特殊文件系统需要兼容处理
• 调试时需要详细的错误信息

💡 建议：
• 新手用户：直接用智能清理
• 高级用户：可尝试极速清理
• 遇到问题：勾选"专家"使用兼容模式"""
        
        messagebox.showinfo("清理模式说明", help_text)
        
    def toggle_expert_mode(self):
        """切换专家模式显示"""
        if self.expert_mode.get():
            # 显示兼容模式选项
            self.mode_normal.pack(side=tk.LEFT, padx=(5, 0), before=self.mode_normal.master.children['!label'])
        else:
            # 隐藏兼容模式选项
            self.mode_normal.pack_forget()
            # 如果当前选择的是兼容模式，自动切换到智能模式
            if self.cleanup_mode.get() == "normal":
                self.cleanup_mode.set("smart")
        
    def run(self):
        """运行GUI"""
        # 启动时自动扫描
        self.root.after(100, self.scan_targets)
        self.root.mainloop()


def main():
    """主函数"""
    try:
        # 检查是否以管理员权限运行
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        
        if not is_admin:
            # 尝试以管理员权限重新启动
            result = messagebox.askyesno(
                "权限提升", 
                "此程序需要管理员权限才能清理系统文件。\n是否以管理员权限重新启动？"
            )
            if result:
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, " ".join(sys.argv), None, 1
                )
                return
        
        # 启动GUI
        app = CleanerGUI()
        app.run()
        
    except Exception as e:
        messagebox.showerror("错误", f"程序启动失败：{str(e)}")


if __name__ == "__main__":
    main()
