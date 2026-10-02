"""Additional audit-only checks: calendar baselines, provenance and artifact integrity."""
from audit_probe import *
from collections import Counter
raw=pd.DataFrame(json.loads((OUT/'food_prices_snapshot.json').read_text()))
pre=DataPreprocessor()
valid=pre._drop_invalid_rows(pre._coerce_types(raw))
dedup=pre._sort_and_index(pre._handle_duplicates(valid))
pred=pd.read_csv(OUT/'diagnostic_predictions.csv',keep_default_na=False)
pred.report_date=pd.to_datetime(pred.report_date)
baselines=[]
for key,g in dedup.groupby(SERIES_KEY):
    # Causal calendar reindex. No interpolation, outlier deletion, or backward filling.
    daily=g.set_index('report_date').price_index.asfreq('D').ffill()
    frame=pd.DataFrame({'naive_calendar':daily.shift(1),
        'seasonal_calendar':daily.shift(7),'ma7_calendar':daily.shift(1).rolling(7).mean()})
    frame.index.name='report_date'; frame=frame.reset_index()
    for c,v in zip(SERIES_KEY,key): frame[c]=v
    baselines.append(frame)
joined=pred.merge(pd.concat(baselines),on=SERIES_KEY+['report_date'],how='left',validate='one_to_one')
complete=joined.dropna(subset=['naive_calendar','seasonal_calendar','ma7_calendar'])
out={'same_row_calendar_baseline_comparison':{'n':len(complete),'first':str(complete.report_date.min()),'last':str(complete.report_date.max()),
     'metrics':{m:compute_all_metrics(complete.price_index.to_numpy(),complete[m].to_numpy())
        for m in ['lgbm','lstm','ensemble','naive_calendar','seasonal_calendar','ma7_calendar']}}}
per_category=[]
for cat,g in complete.groupby('product_category'):
    for m in ['lgbm','lstm','naive_calendar']:
        per_category.append({'category':cat,'model':m,'n':len(g)}|compute_all_metrics(g.price_index.to_numpy(),g[m].to_numpy()))
pd.DataFrame(per_category).to_csv(OUT/'calendar_category_metrics.csv',index=False)
joined.to_csv(OUT/'diagnostic_predictions_with_calendar_baselines.csv',index=False)
created=pd.to_datetime(raw.created_at,utc=True,errors='coerce')
out['created_by_original_training_time']=int((created<=pd.Timestamp('2026-05-28T11:03:17Z')).sum())
out['created_at_range']=[str(created.min()),str(created.max())]
out['created_at_limitations']='Upstream copying preserves created_at, so this cannot recover the original immutable training snapshot.'
date_pattern=r'([A-Za-z]+)-(\d+)-(\d{4})'
source_dates=[]
for source in raw.source_pdf:
    m=re.search(date_pattern,str(source))
    try: date=pd.Timestamp(datetime.strptime(' '.join(m.groups()),'%B %d %Y')) if m else pd.NaT
    except ValueError: date=pd.NaT
    source_dates.append(date)
sd=pd.Series(source_dates); rd=pd.to_datetime(raw.report_date)
out['source_pdf_date_diagnostics']={'parsable':int(sd.notna().sum()),
    'source_older_than_report':int((sd<rd).sum()),'source_newer_than_report':int((sd>rd).sum()),
    'note':'URL-derived evidence of carried-forward/misdated rows; not a verified observed/imputed label.'}
out['saved_model_integrity']={}
for filename in ['lightgbm_model.txt','lightgbm_residual_model.txt']:
    b=(ART/filename).read_bytes(); t=b.decode().replace('\r\n','\n')
    raw_starts=[m.start() for m in re.finditer(rb'^Tree=\d+\r?\n',b,re.M)]
    lf_starts=[m.start() for m in re.finditer(r'^Tree=\d+\n',t,re.M)]
    sizes=list(map(int,re.search(r'^tree_sizes=(.*)$',t,re.M)[1].split()))
    out['saved_model_integrity'][filename]={'trees':len(raw_starts),
        'original_offsets_match':all(y-x==s for x,y,s in zip(raw_starts,raw_starts[1:],sizes)),
        'lf_offsets_match':all(y-x==s for x,y,s in zip(lf_starts,lf_starts[1:],sizes)),
        'sha256_unchanged_from_probe':hashlib.sha256(b).hexdigest()==json.loads((OUT/'probe_results.json').read_text())['artifacts'][filename]['sha256']}
# Demonstrate that holding future rows fixed versus changing them changes past outlier decisions.
past=series(20); past.price_index=100.; past.loc[19,'price_index']=200.
future=series(20); future.report_date+=pd.Timedelta(days=20); future.price_index=100.
all_a=pd.concat([past,future],ignore_index=True)
all_b=all_a.copy(); all_b.loc[20:,'price_index']=200.
out['outlier_future_dependence']={'past_spike_date':str(past.report_date.iloc[-1]),
    'retained_with_future_100':bool(pre._remove_outliers(all_a).report_date.eq(past.report_date.iloc[-1]).any()),
    'retained_with_future_200':bool(pre._remove_outliers(all_b).report_date.eq(past.report_date.iloc[-1]).any())}
# Inventory all project-owned module files; no dependency packages or compiled caches.
inventory=[]
for p in sorted((ROOT/'model_trainer').rglob('*')):
    if not p.is_file() or any(x in p.parts for x in ['.venv','__pycache__','artifacts','logs','plots']): continue
    if p.name.startswith('.env'): continue
    inventory.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
write('source_inventory.json',inventory)
write('additional_checks.json',out)
print(json.dumps(out,indent=2,default=str),flush=True)
