"""Generate Compass-importable MongoDB JSON from public synthetic fixtures."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.models import ALL_MODELS, User
from backend.app.seed import seed_demo_roads
from backend.app.demo_accounts import DEMO_ACCOUNTS
from backend.app.passwords import hash_password
from backend.app.mongo_schema import SCHEMAS


class FixtureCollector:
    """Collect only generated road/camera fixtures, with no database connection."""
    def __init__(self):
        self.rows={model.collection:[] for model in ALL_MODELS}
    def find_one(self,model,*_): return None
    def add(self,row):
        rows=self.rows[row.collection]
        row.id=len(rows)+1
        rows.append(row)
    def flush(self): pass
    def find(self,model,*,sort=None,limit=0):
        return self.rows[model.collection][:limit or None]


def build(output_directory):
    output=Path(output_directory)
    output.mkdir(parents=True,exist_ok=True)
    fixture=FixtureCollector()
    seed_demo_roads(fixture)
    for account in DEMO_ACCOUNTS:
        fixture.add(User(**{k:v for k,v in account.items() if k!='password'},password=hash_password(account['password'])))
    counters=[]
    for name,rows in fixture.rows.items():
        documents=[]
        for row in rows:
            document=row.values()
            document['_id']=document.pop(row.primary)
            documents.append(document)
        (output/f'{name}.json').write_text(json.dumps(documents,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        if name not in ('sessions','reset_tokens','video_jobs'):
            counters.append({'_id':name,'seq':len(rows)})
    (output/'counters.json').write_text(json.dumps(counters,indent=2)+'\n',encoding='utf-8',newline='\n')
    (output/'schema.json').write_text(json.dumps(SCHEMAS,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    return {name:len(rows) for name,rows in fixture.rows.items()}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'database/mongodb')
    args=parser.parse_args()
    print('MongoDB public fixtures:',json.dumps(build(args.output)))
