"""全局配置：路径、阈值、模型下载地址等"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 模型目录
MODELS_DIR = PROJECT_ROOT / "models"
YOLO_MODEL_PATH = MODELS_DIR / "yolov8_plate.pt"
LAMA_MODEL_DIR = MODELS_DIR / "lama"

# 默认输出与日志目录
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT /