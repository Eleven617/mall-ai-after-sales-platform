"""
知识库导入脚本。
在启动服务前运行一次，把所有 .md 知识库文件生成 embedding 并存入 ChromaDB。

用法：
    ./.venv/Scripts/python.exe scripts/ingest_knowledge.py
"""
import sys
from pathlib import Path

# 确保 app 目录在 Python 搜索路径中
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vector_store import ingest_knowledge_base


if __name__ == "__main__":
    print("正在导入知识库...")
    count = ingest_knowledge_base()
    print(f"导入完成！共 {count} 个 chunk 已存入 ChromaDB。")
    print(f"存储位置：chroma_data/")
