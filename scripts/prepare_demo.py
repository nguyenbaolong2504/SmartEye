"""Create a separate synthetic history and train XGBoost (development only)."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.db import initialize_database,get_database,SessionLocal
from backend.app.seed import seed
from backend.app.demo_data import prepare_demo,status

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,default=31)
    args=parser.parse_args()
    initialize_database()
    with SessionLocal() as db:seed(db)
    prepare_demo(get_database(),days=args.days)
    result=status(get_database())
    print(f"Đã tạo lịch sử mô phỏng {result['history_days']} ngày cho {len(result['segment_ids'])} tuyến, huấn luyện XGBoost cho 15/30 phút.")
    print(result['notice'])
