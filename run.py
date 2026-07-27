"""消除车牌 - 启动脚本"""
import sys
import os

# 把项目根目录加入 sys.path，便于直接 python run.py 运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main


if __name__ == "__main__":
    main()
