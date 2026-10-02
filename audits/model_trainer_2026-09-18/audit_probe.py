"""Read-only production audit; outputs and any probe artifacts stay in this directory.
Usage: python -B audit_probe.py [--fetch]
No training, publishing, DB mutations, or production artifact writes.
"""
import sys, types, logging, json, hashlib, argparse, urllib.request, urllib.parse, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'model_trainer'))
stub = types.ModuleType('utils.logger')
stub.get_logger = lambda name: logging.getLogger(name)
sys.modules['utils.logger'] = stub
logging.disable(logging.CRITICAL)
import numpy as np
import pandas as pd
import torch
import lightgbm as lgb
from config.settings import get_settings
cfg = get_settings()
ART = cfg.artifacts_dir
SCRATCH = OUT / 'probe_artifacts'
SCRATCH.mkdir(exist_ok=True)
cfg.artifacts_dir = SCRATCH
from data.preprocessor import DataPreprocessor, SERIES_KEY
from features.lag_features import LagFeatures
from features.temporal import TemporalFeatures
from features.categorical import CategoricalEncoder
from models.lstm_model import LSTMModel
from models.ensemble import EnsembleModel
from utils.metrics import compute_all_metrics

def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str), encoding='utf-8')

def series(n=120):
    return pd.DataFrame({'report_date': pd.date_range('2025-01-01', periods=n),
        'price_index': np.arange(n, dtype=float)+100,
        'product_category':'Vegetables', 'product_name':'Probe',
        'product_variant':'Standard', 'origin':'Local', 'unit':'kg'})

def probes():
    pre = DataPreprocessor()
    df = series()
    feat = LagFeatures().transform(TemporalFeatures().transform(df))
    changed = df.copy()
    changed.loc[75, 'price_index'] += 1000
    feat2 = LagFeatures().transform(TemporalFeatures().transform(changed))
    changed_features = [c for c in feat if c.startswith('price_') and
        not np.isclose(feat.loc[75,c],feat2.loc[75,c],equal_nan=True)]
    recon = feat.price_expanding_mean * (1+feat.price_deviation_from_mean)
    gap = series(3).iloc[[0,2]].copy()
    gap.price_index = [100.,300.]
    filled = pre._fill_missing(gap)
    gap.price_index = [100.,500.]
    filled2 = pre._fill_missing(gap)
    mixed = pd.concat([series(1),series(1).assign(unit='piece',price_index=10.)])
    merged = pre.validate(mixed)
    model = LSTMModel()
    X, y = model.build_sequences(feat.dropna().reset_index(drop=True))
    inference_df = feat.dropna().reset_index(drop=True)
    Xi, yi, idx, products, anchors = model.build_sequences_inference(inference_df)
    network = __import__('models.lstm_model',fromlist=['_LSTMNetwork'])._LSTMNetwork(input_size=16)
    model._model = network
    model._device = torch.device('cpu')
    try:
        model.predict_future(Xi[-1], products[-1], steps=2)
        recursive_error = None
    except Exception as e:
        recursive_error = type(e).__name__ + ': ' + str(e)
    # Best single model is exact; grid search should select its endpoint.
    ens = EnsembleModel()
    ens.train_blended_ensemble(np.array([10.,20.,30.]),np.array([12.,23.,34.]),np.array([10.,20.,30.]))
    out = {'versions': {'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,
                       'torch':torch.__version__,'lightgbm':lgb.__version__},
        'current_target_mutation_changes':changed_features,
        'target_reconstruction_max_error':float((recon-df.price_index).abs().max()),
        'future_mutation_changes_missing_past_price':[float(filled.iloc[1].price_index),float(filled2.iloc[1].price_index)],
        'mixed_unit_duplicate_result':merged[['price_index','unit']].to_dict('records'),
        'sequence_shapes':{'X':list(X.shape),'y':list(y.shape)},
        'last_inference_window':{'latest_observation':str(inference_df.report_date.max()),
          'first_target':str(inference_df.iloc[idx[-1]].report_date),
          'true_anchor':float(anchors[-1]),'writer_anchor':float(inference_df.iloc[-1].price_index),
          'writer_first_label':str(inference_df.report_date.max()+pd.Timedelta(days=1))},
        'recursive_predict_future_error':recursive_error,
        'ensemble_exact_lstm_case':ens.get_residual_stats(),
        'metric_known_case':compute_all_metrics(np.array([100.,200.]),np.array([110.,180.])),
        'network_parameters':sum(p.numel() for p in network.parameters()),
    }
    # Inspect text without invoking the native parser on invalid byte offsets.
    raw=(ART/'lightgbm_model.txt').read_bytes()
    model_text=raw.decode().replace('\r\n','\n')
    names=re.search(r'^feature_names=(.*)$',model_text,re.M)[1].split()
    gains=np.zeros(len(names)); splits=np.zeros(len(names),dtype=int)
    blocks=re.split(r'^Tree=\d+\n',model_text,flags=re.M)[1:]
    for block in blocks:
        fi=list(map(int,re.search(r'^split_feature=(.*)$',block,re.M)[1].split()))
        fg=list(map(float,re.search(r'^split_gain=(.*)$',block,re.M)[1].split()))
        for f,g in zip(fi,fg): gains[f]+=g; splits[f]+=1
    sizes=list(map(int,re.search(r'^tree_sizes=(.*)$',model_text,re.M)[1].split()))
    raw_starts=[m.start() for m in re.finditer(rb'^Tree=\d+\r?\n',raw,re.M)]
    lf_starts=[m.start() for m in re.finditer(r'^Tree=\d+\n',model_text,re.M)]
    out['saved_lgbm']={'trees':len(blocks),'feature_count':len(names),'features':names,
        'gain_fraction':dict(sorted(zip(names,(gains/gains.sum()).tolist()),key=lambda x:-x[1])),
        'leak_feature_split_count':int(splits[names.index('price_deviation_from_mean')]),
        'crlf_count':raw.count(b'\r\n'), 'declared_first_tree_bytes':sizes[0],
        'actual_first_tree_bytes':raw_starts[1]-raw_starts[0],
        'lf_first_tree_bytes':lf_starts[1]-lf_starts[0]}
    for filename in ['lightgbm_model.txt','lightgbm_residual_model.txt','lstm_model.pt','lstm_meta.npz',
                     'lstm_product_means.pkl','ensemble_residual_stats.pkl']:
        p=ART/filename
        out.setdefault('artifacts',{})[filename]={'bytes':p.stat().st_size,
            'modified_utc':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    h=json.loads((ART/'lstm_history.json').read_text())
    best=int(np.nanargmin(h['val_loss']))
    out['history']={'epochs':len(h['epoch']),'best_epoch':h['epoch'][best],
        'best_train_loss':h['train_loss'][best],'best_val_loss':h['val_loss'][best],
        'last_train_loss':h['train_loss'][-1],'last_val_loss':h['val_loss'][-1]}
    write('probe_results.json',out)
    print(json.dumps(out,indent=2,default=str),flush=True)

def fetch():
    # GET only. Never print credentials, connection strings, or HTTP response bodies on error.
    rows=[]; offset=0
    while True:
        query=urllib.parse.urlencode({'select':'*','order':'report_date.asc,id.asc','offset':offset,'limit':1000})
        req=urllib.request.Request(cfg.supabase_url.rstrip('/')+'/rest/v1/food_prices?'+query,
            headers={'apikey':cfg.supabase_key,'Authorization':'Bearer '+cfg.supabase_key})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                batch=json.load(response)
        except Exception as e:
            print('READ_ONLY_FETCH_FAILED '+type(e).__name__+' '+str(getattr(e,'code','')),flush=True)
            raise SystemExit(2)
        rows.extend(batch)
        if offset%10000==0: print('Fetched rows:',len(rows),flush=True)
        if len(batch)<1000: break
        offset+=1000
    write('food_prices_snapshot.json',rows)
    write('snapshot_metadata.json',{'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
        'rows':len(rows),'order':'report_date.asc,id.asc','atomic_snapshot':False,
        'sha256':hashlib.sha256((OUT/'food_prices_snapshot.json').read_bytes()).hexdigest()})
    print('Saved read-only data snapshot:',len(rows),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--fetch',action='store_true')
    args=parser.parse_args()
    if args.fetch: fetch()
    else: probes()
