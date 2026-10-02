"""Replay current preprocessing and frozen models for diagnostic comparison only.
These are NOT clean held-out test results: known pipeline leakage is preserved.
All writes are audit files. No model is trained or production artifact changed.
"""
from audit_probe import *
import joblib
torch.set_num_threads(4)

def span(df):
    return {'rows':len(df),'start':str(df.report_date.min().date()) if len(df) else None,
            'end':str(df.report_date.max().date()) if len(df) else None,
            'unique_dates':int(df.report_date.nunique()),
            'series':len(df.groupby(SERIES_KEY))}

def prepare(raw, tag):
    pre=DataPreprocessor()
    typed=pre._coerce_types(raw)
    valid=pre._drop_invalid_rows(typed)
    dedup=pre._sort_and_index(pre._handle_duplicates(valid))
    filled=pre._fill_missing(dedup)
    clean=pre._remove_outliers(filled)
    featured=LagFeatures().transform(TemporalFeatures().transform(clean))
    encoder=CategoricalEncoder()
    encoder._save_mappings=lambda:None
    featured=encoder.fit_transform(featured)
    train0,val0=pre.time_split(featured)
    train=train0.dropna().reset_index(drop=True)
    val=val0.dropna().reset_index(drop=True)
    details={'raw':span(typed),'valid':span(valid),'dedup':span(dedup),'filled':span(filled),
        'clean':span(clean),'train_before_dropna':span(train0),'val_before_dropna':span(val0),
        'train':span(train),'validation':span(val),'independent_test_rows':0,
        'train_row_percent':100*len(train)/(len(train)+len(val)),
        'validation_row_percent':100*len(val)/(len(train)+len(val)),
        'missing_values':raw.isna().sum().to_dict(),
        'units':raw.unit.value_counts(dropna=False).to_dict(),
        'multiunit_series':int((valid.groupby(SERIES_KEY).unit.nunique()>1).sum()),
        'same_day_multiunit_groups':int((valid.groupby(SERIES_KEY+['report_date']).unit.nunique()>1).sum()),
        'clean_gaps_gt_1_day':int((clean.groupby(SERIES_KEY).report_date.diff()>pd.Timedelta(days=1)).sum()),
        'retained_gaps_gt_1_day':int((pd.concat([train,val]).sort_values(SERIES_KEY+['report_date']).groupby(SERIES_KEY).report_date.diff()>pd.Timedelta(days=1)).sum()),
        'training_sequence_count':int(sum(max(0,len(g)-58) for _,g in train.groupby(SERIES_KEY))),
        'category_counts':raw.product_category.value_counts(dropna=False).to_dict(),
        'invalid_dates':int(typed.report_date.isna().sum()),
        'invalid_or_nonpositive_prices':int((typed.price_index.isna()|(typed.price_index<=0)).sum()),
        'nonfinite_prices':int((~np.isfinite(typed.price_index)).sum()),
        'price_quantiles':typed.price_index.quantile([0,.01,.5,.99,1]).to_dict()}
    unit_conflicts=valid.groupby(SERIES_KEY).agg(units=('unit',lambda s:','.join(sorted(s.dropna().unique()))),unit_count=('unit','nunique'))
    unit_conflicts[unit_conflicts.unit_count>1].to_csv(OUT/f'{tag}_unit_conflicts.csv')
    split_rows=[]
    for label,data in [('train',train),('validation',val)]:
        for key,g in data.groupby(SERIES_KEY):
            split_rows.append(dict(zip(SERIES_KEY,key))|{'split':label}|span(g))
    pd.DataFrame(split_rows).to_csv(OUT/f'{tag}_series_splits.csv',index=False)
    return details,train,val,clean

raw=pd.DataFrame(json.loads((OUT/'food_prices_snapshot.json').read_text()))
raw['report_date']=pd.to_datetime(raw.report_date)
summary={'snapshot_rows':len(raw),'raw_columns':list(raw.columns),'raw_dtypes':raw.dtypes.astype(str).to_dict(),
         'snapshot_duplicate_ids':int(raw.id.duplicated().sum())}
summary['current'],train,val,clean=prepare(raw,'current')
hist_raw=raw[raw.report_date<=pd.Timestamp('2026-05-28')].copy()
summary['historical_replay_not_original_snapshot'],_,_,_=prepare(hist_raw,'historical_replay')
write('data_analysis.json',summary)
print('PROFILE '+json.dumps(summary,default=str),flush=True)

# Stored categorical mappings are used for frozen inference, rather than newly fitted codes.
encoder=CategoricalEncoder(); encoder._save_path=ART/'categorical_mappings.json'
train=encoder.transform(train); val=encoder.transform(val)
lstm=LSTMModel()
lstm._model_path=ART/'lstm_model.pt'; lstm._product_means_path=ART/'lstm_product_means.pkl'
lstm._meta_path=ART/'lstm_meta.npz'
lstm.load()
model_text=(ART/'lightgbm_model.txt').read_text()
bm=lgb.Booster(model_str=model_text)
print('Loaded frozen LSTM and in-memory LF-normalized LightGBM; no file repaired.',flush=True)
summary['normalized_lgbm_load']='success (original bytes unchanged)'
stats=joblib.load(ART/'ensemble_residual_stats.pkl')
summary['stored_ensemble_stats']=stats
pred_frames=[]; horizons=[]
for key,g in val.groupby(SERIES_KEY):
    mask=np.ones(len(train),dtype=bool)
    for c,k in zip(SERIES_KEY,key): mask &= train[c].eq(k).to_numpy()
    full=pd.concat([train[mask].tail(29),g]).sort_values(SERIES_KEY+['report_date']).reset_index(drop=True)
    X,y,idx,products,anchors=lstm.build_sequences_inference(full)
    if not len(X): continue
    pred_norm=np.concatenate([lstm._predict_raw(X[j:j+256]) for j in range(0,len(X),256)])
    pred=anchors[:,None]*(1+pred_norm)
    actual=anchors[:,None]*(1+y)
    selected=full.iloc[idx].copy()
    lp=bm.predict(selected[bm.feature_name()],num_threads=4)
    selected['lstm']=pred[:,0]; selected['lgbm']=lp
    selected['ensemble']=stats.get('lstm_weight',.5)*pred[:,0]+stats.get('lgbm_weight',.5)*lp
    selected['naive_anchor']=anchors
    selected['seasonal_naive']=selected.price_lag_7d
    selected['moving_average_7']=selected.price_rolling_mean_7d
    pred_frames.append(selected)
    for h in [1,7,30]:
        horizons.append({'h':h,'actual':actual[:,h-1], 'lstm':pred[:,h-1], 'naive':anchors})
matched=pd.concat(pred_frames,ignore_index=True)
metrics={name:compute_all_metrics(matched.price_index.to_numpy(),matched[name].to_numpy())
         for name in ['lgbm','lstm','ensemble','naive_anchor','seasonal_naive','moving_average_7']}
summary['diagnostic_comparison']={'WARNING':'Known leaky pipeline; frozen artifacts lack verifiable training cutoff. Not a valid unseen test.',
        'matched_span':span(matched),'metrics':metrics,
        'naive_anchor_differs_from_engineered_lag1':int((abs(matched.naive_anchor-matched.price_lag_1d)>1e-8).sum())}
for h in [1,7,30]:
    subset=[r for r in horizons if r['h']==h]
    a=np.concatenate([r['actual'] for r in subset])
    summary.setdefault('diagnostic_lstm_by_horizon',{})[h]={name:compute_all_metrics(a,np.concatenate([r[name] for r in subset])) for name in ['lstm','naive']}
cols=SERIES_KEY+['report_date','price_index','lgbm','lstm','ensemble','naive_anchor','seasonal_naive','moving_average_7']
matched[cols].to_csv(OUT/'diagnostic_predictions.csv',index=False)
percat=[]
for cat,g in matched.groupby('product_category'):
    for name in ['lgbm','lstm','naive_anchor']:
        percat.append({'category':cat,'model':name,'n':len(g)}|compute_all_metrics(g.price_index.to_numpy(),g[name].to_numpy()))
pd.DataFrame(percat).to_csv(OUT/'diagnostic_category_metrics.csv',index=False)
write('data_analysis.json',summary)
print('DIAGNOSTIC '+json.dumps(summary['diagnostic_comparison'],default=str),flush=True)
print('HORIZONS '+json.dumps(summary['diagnostic_lstm_by_horizon'],default=str),flush=True)
