#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReviewAgent 对话式智能体 - 简化测试版本
"""
import sys
import os

print("=" * 70, flush=True)
print("ReviewAgent 对话式智能体启动测试", flush=True)
print("=" * 70, flush=True)
print("\n[INFO] Python 版本:", sys.version, flush=True)
print("[INFO] 当前目录:", os.getcwd(), flush=True)
print("[INFO] 脚本路径:", __file__, flush=True)

# 测试导入
print("\n[TEST] 测试模块导入...", flush=True)

try:
    from pathlib import Path
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    print(f"[OK] 项目路径: {project_root}", flush=True)
except Exception as e:
    print(f"[ERROR] 路径设置失败: {e}", flush=True)
    sys.exit(1)

try:
    from scripts.smart_reviewer import SmartReviewer
    print("[OK] SmartReviewer 导入成功", flush=True)
except Exception as e:
    print(f"[ERROR] SmartReviewer 导入失败: {e}", flush=True)
    sys.exit(1)

try:
    from scripts.ai_adapter import get_ai_client
    print("[OK] AI Adapter 导入成功", flush=True)
except Exception as e:
    print(f"[ERROR] AI Adapter 导入失败: {e}", flush=True)
    sys.exit(1)

# 测试配置
print("\n[TEST] 测试配置文件...", flush=True)
config_file = 'config/ai_config.json'

if os.path.exists(config_file):
    print(f"[OK] 配置文件存在: {config_file}", flush=True)

    try:
        import json
        with open(config_file, 'r') as f:
            config = json.load(f)
        print(f"[OK] 配置内容: provider={config.get('provider')}, model={config.get('model')}", flush=True)
    except Exception as e:
        print(f"[ERROR] 读取配置失败: {e}", flush=True)
else:
    print(f"[WARN] 配置文件不存在: {config_file}", flush=True)

print("\n[TEST] 基础测试完成！", flush=True)
print("\n如果看到这条消息，说明环境正常。", flush=True)
print("现在尝试运行完整版本: python chat.py", flush=True)
