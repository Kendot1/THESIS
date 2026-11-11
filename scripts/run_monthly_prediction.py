"""
Run monthly prediction for Foodcast-prod
"""

import os
import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "model_trainer"))

REF = 'zhwhnnxbodzrklhgsurn'
WORK = Path(os.environ['LOCALAPPDATA'])/'hermes/private-backups'/('foodcast-destination-'+REF)/'cli-workspace'
r = subprocess.run(['npx.cmd','--yes','supabase','projects','api-keys','--remote='+REF,'--reveal','--output','json','--workdir',str(WORK)], capture_output=True, text=True)
keys = json.loads(r.stdout)
service_key = next(x['api_key'] for x in keys if x.get('name')=='service_role')

os.environ['SUPABASE_URL'] = f'https://{REF}.supabase.co'
os.environ['SUPABASE_KEY'] = service_key

from pipeline.prediction_writer import PredictionWriter

writer = PredictionWriter()
print("Running monthly prediction...")
res = writer.run('monthly')
print(f"Monthly prediction complete:")
print(f"  Model Run ID: {res.get('model_run_id')}")
print(f"  Failures:     {len(res.get('failures', []))}")
