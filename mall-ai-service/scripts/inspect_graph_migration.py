"""部署前只读聚合检查；不读取原始消息、提案参数或凭证。"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", required=True)
    parser.parse_args()
    from app.config import settings
    from pymongo import MongoClient
    try:
        client = MongoClient(settings.agent_task_mongo_url, serverSelectionTimeoutMS=3000)
        collection = client[settings.agent_task_mongo_database][settings.agent_task_mongo_collection]
        rows = list(collection.aggregate([
            {"$group": {"_id": {"graphVersion": {"$ifNull": ["$graph_version", "legacy"]},
                                "status": "$task.status"}, "count": {"$sum": 1},
                         "earliestExpiry": {"$min": "$task.expires_at"}}},
            {"$sort": {"_id.graphVersion": 1, "_id.status": 1}},
        ]))
        print(json.dumps({"scope": "task-migration-aggregate", "groups": rows, "readOnly": True}, ensure_ascii=False))
        return 0
    except Exception:
        print("migration_inventory_unavailable")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
