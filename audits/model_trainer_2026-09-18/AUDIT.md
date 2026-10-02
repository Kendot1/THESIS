**FOODCAST model_trainer technical audit — 18 September 2026**

**Verdict: the current implementation does not provide credible evidence of forecasting genuinely unseen future food prices.** Confirmed target leakage invalidates the LightGBM evaluation; future-dependent cleaning affects both models; there is no independent test partition; and production forecasts use a different, temporally misaligned algorithm from the one evaluated. The MAE/RMSE/MAPE formulas are mostly correct, but that does not make the experiments valid. This is not evidence that either algorithm is intrinsically unsuitable.

Production source, models, configuration, database records and existing plots were not modified. This audit added only files under `audits/model_trainer_2026-09-18`. No production training or prediction-writing command was run. Database access was GET-only. Isolated probes exercised existing functions, with logging disabled and artifact writes redirected into the audit directory. A native LightGBM load failed; subsequent diagnostic inference used an LF-normalized string in memory, leaving the saved file unchanged.

Evidence labels: **CONFIRMED** means established from executable code, saved artifacts, logs or an executed probe. **RISK** means the code permits a problem but its occurrence or magnitude has not been established. **NOT VERIFIED** identifies missing evidence. The current database is not the immutable dataset used in May. New diagnostic results must not be presented as a reproduction of that experiment or as a clean test.

Evidence files: [executed probes](probe_results.json), [dataset analysis](data_analysis.json), [calendar baseline and integrity checks](additional_checks.json), [per-series split inventory](current_series_splits.csv), [unit conflicts](current_unit_conflicts.csv), [aligned predictions](diagnostic_predictions_with_calendar_baselines.csv), [category metrics](calendar_category_metrics.csv), [source inventory and hashes](source_inventory.json), and [snapshot provenance](snapshot_metadata.json). Source references below use exact current file lines.

**A. Pipeline map and dataset validation**

The actual training flow is:

1. `main.py` selects full, incremental or daily training. Full training fetches all rows; incremental also fetches all rows, even when `since_date` is passed. Daily performs a drift check before choosing full versus incremental. [trainer.py:75](../../model_trainer/pipeline/trainer.py#L75), [trainer.py:87](../../model_trainer/pipeline/trainer.py#L87), [trainer.py:112](../../model_trainer/pipeline/trainer.py#L112).
2. `DataFetcher` paginates `food_prices`, ordered only by `report_date`. There is no immutable snapshot, availability cutoff or secondary unique ordering key. [fetcher.py:104](../../model_trainer/data/fetcher.py#L104).
3. `validate()` coerces dates/prices, removes missing dates/prices/names and nonpositive prices, averages duplicate series/date rows, sorts, inserts daily rows, interpolates prices using both endpoints, and removes full-series four-sigma outliers. All this happens **before** splitting. [preprocessor.py:35](../../model_trainer/data/preprocessor.py#L35).
4. Temporal, lag/rolling and categorical features are computed over the whole cleaned dataset. Full mode fits categorical mappings before splitting. News features are instantiated but are not added by `_build_features()`. [trainer.py:377](../../model_trainer/pipeline/trainer.py#L377).
5. The last 15% of unique dates becomes validation; all previous dates become training. Unrestricted `dropna()` then removes rows based on every column, including metadata. There is no third partition. [trainer.py:159](../../model_trainer/pipeline/trainer.py#L159).
6. LightGBM fits contemporaneous `price_index` from the 54 features of that target row, uses validation for early stopping, computes validation metrics and saves the point model. Quantile models are trained but not persisted. [lightgbm_model.py:53](../../model_trainer/models/lightgbm_model.py#L53).
7. LSTM fits per-series means on training rows, builds 30-row feature windows and 30-output return targets, trains with validation early stopping, restores the best weights and reports **only output 1** in original price units. [lstm_model.py:228](../../model_trainer/models/lstm_model.py#L228), [lstm_model.py:374](../../model_trainer/models/lstm_model.py#L374).
8. `_evaluate_hybrid()` searches ensemble weights on the same validation targets and reports the selected blend on those targets. The advertised residual-training function exists but is not called by `_train()`. [trainer.py:190](../../model_trainer/pipeline/trainer.py#L190), [trainer.py:555](../../model_trainer/pipeline/trainer.py#L555).
9. Selected artifact filenames and summary metrics are versioned, the full-data drift reference is overwritten, and validation plots are generated. Artifacts actually needed for current inference are missing from version snapshots. [model_store.py:47](../../model_trainer/models/model_store.py#L47).
10. The independent `evaluate` command reloads existing models, preprocesses the currently available database again, drops missing rows, then takes its last 15% of dates. It neither verifies a saved training cutoff nor guarantees that these rows were unseen. Its drop/split order also differs from training. [main.py:58](../../model_trainer/main.py#L58).
11. Production `predict` fetches and cleans again, groups by name/variant/origin, constructs historical LSTM evaluation windows, takes the last such window, reconstructs its outputs using the latest price, adds an old residual-model correction, stabilizes the point forecast and writes future-dated rows. Failures can silently produce a moving-average/trend fallback. [prediction_writer.py:111](../../model_trainer/pipeline/prediction_writer.py#L111), [prediction_writer.py:211](../../model_trainer/pipeline/prediction_writer.py#L211).
12. GitHub Actions runs scrape → news scrape → download artifacts → daily train → monthly predictions → upload artifacts. It contains no independent evaluation gate. [main.yml:64](../../.github/workflows/main.yml#L64).

The upstream price parser calls an LLM to extract an **average retail price** into the misleadingly named `price_index`; it is not calculating a dimensionless economic index. It accepts variable units, with no numeric unit conversion. [ai_parser.py:114](../../scraper/ai_parser.py#L114). The scraper also fills whole missing dates by copying previous rows, including their `source_pdf` and `created_at`, without an observed/imputed flag. This is causal filling, not future leakage by itself, but copied targets must not be treated as independent measured outcomes. [fill_missing_days.py:41](../../scraper/fill_missing_days.py#L41), [fill_missing_days.py:81](../../scraper/fill_missing_days.py#L81).

The database snapshot was read on 2026-09-18 at 02:29:33 UTC using stable `report_date,id` ordering. It is a paginated extraction, **not** a transactional database snapshot.

| Dataset property | Observed result |
|---|---|
| Columns | `id`, `product_category`, `product_name`, `product_variant`, `unit`, `origin`, `price_index`, `report_date`, `source_pdf`, `created_at` |
| Raw rows / date range | 151,344 / 2019-10-10–2026-09-17 |
| Raw unique dates / configured series | 2,527 / 117 |
| Missing fields | 272 null units; zero nulls in the other fetched columns |
| Date / price checks | 0 invalid dates; 3 nonpositive prices; 0 nonfinite prices |
| Raw price distribution | min 0; median 85.55; 99th percentile 464.7813; max 1,000 |
| After invalid removal | 151,341 |
| After configured-key deduplication | 151,341; no duplicated IDs in the extraction |
| After daily reindex/interpolation | 161,525: 10,184 inserted rows |
| After global outlier deletion | 161,130: 395 removed |
| Units | 21 raw categories including null; kg, piece, liter, ml, bottle, pack and inconsistent spellings |
| Series with multiple unit labels | 60; no same-series/date multiunit collisions in this snapshot |
| Gaps after outlier deletion | 75 intervals longer than one day |
| Gaps after feature-related/all-column row dropping | 1,567 intervals longer than one day |

The four-column series key is category + name + variant + origin. Most cross-product mixing is prevented in preprocessing and feature engineering. **Unit is omitted everywhere in that key.** Several variations are synonyms, but examples such as Papaya (`kg`, `per kg`, `piece`) and Yellow Sweet Corn (`kg`, `piece`) need source verification and conversion or separation. Oils contain especially inconsistent labels. The probe demonstrates that same-day prices of 100/kg and 10/piece would be averaged into 55 and labelled kg. This hypothetical collision was reproduced; it was not found on the same day in the current snapshot. Cross-date unit changes are present. [preprocessor.py:17](../../model_trainer/data/preprocessor.py#L17), [preprocessor.py:93](../../model_trainer/data/preprocessor.py#L93).

Of 151,089 parseable source URLs, 37,079 contain a date earlier than the row's report date and 31 a later date. This supports a substantial copied/misdated-data concern, but URL dates are not a verified provenance label. Do not equate every repeated price with an error. PDF-to-row price accuracy, physical unit equivalence, publication times and the true proportion of independently observed prices are **NOT VERIFIED**.

**B. Critical issues**

**B1 — Direct target leakage in LightGBM. CONFIRMED.**

- **File/function/lines:** `features/lag_features.py`, `LagFeatures.transform`, 104–114; `pipeline/trainer.py`, `_get_feature_columns`, 392–409; LightGBM target assignment at 180–183.
- **Problem:** `price_deviation_from_mean = (price_index - price_expanding_mean) / price_expanding_mean` uses today's actual target. Both deviation and expanding mean enter LightGBM.
- **Why leakage:** `price_index = price_expanding_mean * (1 + price_deviation_from_mean)`. The input contains an exact algebraic encoding of the answer, unavailable before that price is observed.
- **Evidence:** changing only the target at one date changes the same-date deviation; target reconstruction error was at most 2.84e-14. The saved model includes this feature and splits on it 5,726 times. It has 0.322% of total gain, so it is **not** the dominant gain feature; small gain does not make it permissible.
- **Severity:** critical; invalidates LightGBM and blends containing it as clean forecast evaluations.
- **Fix:** remove it or compute a strictly historical version from `price_lag_1d` and a compatible historical mean. Enforce a forecast-origin feature contract and retrain. Do not merely remove it from inference for an already-trained model.
- **Reference:** [lag_features.py:104](../../model_trainer/features/lag_features.py#L104), [trainer.py:392](../../model_trainer/pipeline/trainer.py#L392).

**B2 — Future-dependent interpolation before the split. CONFIRMED.**

- **File/function/lines:** `data/preprocessor.py`, `_fill_missing`, 127–165; called by `validate` at 55 before splitting at `trainer.py:161`.
- **Problem:** time interpolation uses the next observed price to fill an earlier date. This can span the training/validation boundary. Lagged features inherit those synthetic values.
- **Why leakage:** a price at a future date changes what would supposedly have been known in the past. With day 1 = 100, changing day 3 from 300 to 500 changes filled day 2 from 200 to 300. Shifted rolling functions cannot undo this earlier contamination.
- **Severity:** critical for the claim of a causal forecasting experiment; actual effect size on the reported scores is not isolated.
- **Fix:** decide forecast origins first; use past-only imputation with explicit missingness/provenance and maximum fill duration. Never interpolate or fabricate evaluation truth. Keep observed targets separately.
- **Nuance:** price edge `bfill()` is generally redundant here because invalid endpoint prices are removed before reindexing from each series' first to last valid date. The interior interpolation is the confirmed active problem, not proof that every backward-fill call crosses a partition.
- **Reference:** [preprocessor.py:127](../../model_trainer/data/preprocessor.py#L127).

**B3 — No untouched test; validation is also used to fit the ensemble. CONFIRMED.**

- **File/function/lines:** `trainer.py`, `_train`, 159–198; `_evaluate_hybrid`, 555–584; `ensemble.py`, `train_blended_ensemble`, 50–105; `main.py`, `cmd_evaluate`, 73–140.
- **Problem:** the final 15% chooses LightGBM iterations, LSTM checkpoints and blend weights, then supplies reported scores. CLI evaluation just derives another latest-15% slice of the current database and loads existing artifacts.
- **Why leakage/contamination:** validation labels legitimately guide selection, but those same scores are not independent test estimates. Blend weights are explicitly fitted to the evaluated targets. No stored cutoff proves that the CLI slice avoids previous model fitting or selection. Because `dropna()` occurs before the CLI split and after the training split, the two slices need not be identical, but they are not guaranteed independent.
- **Severity:** critical to generalization claims.
- **Fix:** chronological training, tuning/calibration and untouched final test periods; persist all boundaries and target row IDs. For rolling evaluation, every fitted state and selection decision must precede the evaluated origin.
- **Reference:** [trainer.py:159](../../model_trainer/pipeline/trainer.py#L159), [ensemble.py:50](../../model_trainer/models/ensemble.py#L50), [main.py:89](../../model_trainer/main.py#L89).

**B4 — Production LSTM windows and anchors do not forecast the labelled future dates. CONFIRMED.**

- **File/function/lines:** `lstm_model.py`, `build_sequences_inference`, 342–357; `prediction_writer.py`, `_predict_series`, 256–290.
- **Problem:** the inference builder requires 30 actual future targets and stops its origin at `len(features)-30`. The writer takes this last *historical evaluation* sequence and anchors it on the latest observed price, ignoring the builder's returned anchor and target indices.
- **Evidence:** with history ending 2025-04-30, the last sequence is aligned to targets 2025-04-01–2025-04-30 and anchor price 189 on March 31. The writer instead uses 219 on April 30 and labels output 1 as May 1. On a regular daily series this is a 30-day shift; gaps make the calendar misalignment variable.
- **Severity:** critical production correctness error; the evaluated LSTM is not the published forecast process.
- **Fix:** a separate label-free live builder must construct features for target date `T+1`, using observations through `T`, and build the 30-row window ending on that target feature row. Reconstruct all 30 returns using `p_T`. Assert exact origin/target dates and never require unknown future targets to make a live forecast.
- **Reference:** [lstm_model.py:342](../../model_trainer/models/lstm_model.py#L342), [prediction_writer.py:256](../../model_trainer/pipeline/prediction_writer.py#L256).

**B5 — Training evaluates a weighted blend; serving adds a stale residual correction. CONFIRMED.**

- **File/function/lines:** `trainer.py`, `_train`, 178–198 and unused `_train_lgbm_residual`, 448–535; `prediction_writer.py`, `_predict_series`, 268–280; `ensemble.py`, `predict_with_intervals`, 121–137.
- **Problem:** training fits two standalone models and selects weighted averaging. Serving loads `lightgbm_residual_model.txt` and computes `LSTM + shrinkage * residual`, defaulting to 0.5. Current blend statistics do not set `shrinkage`. The writer supplies `lstm_prediction=current_price`, rather than an LSTM prediction, and repeats one residual value over all 30 horizons.
- **Evidence:** the residual artifact is a one-tree model dated May 2; current manifest metrics are from May 28. The current `_train()` does not update that file. Timestamps alone are not lineage, but the uncalled residual stage and incompatible formulas are conclusive.
- **Severity:** critical; reported hybrid metrics do not validate production hybrid forecasts.
- **Fix:** choose one architecture and share its prediction function across validation and serving. If stacking/residual learning is retained, train it on temporally out-of-fold base predictions and calibrate horizon-specific corrections; do not restore the dormant in-sample residual routine unchanged.
- **Reference:** [trainer.py:190](../../model_trainer/pipeline/trainer.py#L190), [prediction_writer.py:268](../../model_trainer/pipeline/prediction_writer.py#L268), [ensemble.py:121](../../model_trainer/models/ensemble.py#L121).

**C. High-priority issues**

**C1 — Future-dependent outlier selection and removal of difficult evaluation targets. CONFIRMED.** File: `data/preprocessor.py`, `_remove_outliers`, 167–192. Mean and standard deviation are calculated from the complete series, including validation. Thus future prices determine which past rows survive; test/validation spikes may be removed before scoring. A synthetic past spike is deleted when future values are 100 and retained when they are 200. This is preprocessing leakage plus target-dependent evaluation selection. Fix: use training-only robust thresholds or causal flags, investigate data errors using independent evidence, and report scores on all valid observed evaluation prices, including genuine spikes. [preprocessor.py:176](../../model_trainer/data/preprocessor.py#L176).

**C2 — Rows are no longer daily when LSTM windows/targets are built. CONFIRMED.** File: `trainer.py:164–165`, `preprocessor.py:188`, `lstm_model.py:285–294`. Removing outliers and unrestricted all-column `dropna()` creates gaps after daily reindexing. Inserted rows have missing IDs and are dropped even when their interpolated prices have already affected feature values. Thirty rows then mean thirty retained observations, not thirty days. The LSTM anchor is the previous retained row; it disagreed with the engineered lag-1 value on 198 of the 30,044 matched diagnostic rows. Fix: maintain an explicit daily index, mask missing targets, retain causal feature context and select valid targets without compressing time. Verify elapsed calendar days for every output.

**C3 — Incomplete model bundles make rollback and reproducibility invalid. CONFIRMED.** `ModelStore.create_version()` copies obsolete `lstm_scaler.npz` and `ensemble_meta_model.pkl`, but omits active `lstm_product_means.pkl`, `lstm_meta.npz`, `ensemble_residual_stats.pkl`, residual model and quantile models. Rollback copies only what exists and does not update the manifest; newer omitted files remain mixed with old weights. LSTM metadata records only input names/count, not hidden size, layers, sequence length, horizon, target convention or training cutoff. Fix: immutable, complete, hashed bundles with a schema/config/run ID; verify completeness and load round-trip before promotion. [model_store.py:59](../../model_trainer/models/model_store.py#L59), [model_store.py:93](../../model_trainer/models/model_store.py#L93), [lstm_model.py:671](../../model_trainer/models/lstm_model.py#L671).

**C4 — The checked-out LightGBM artifact fails normal loading. CONFIRMED in this environment.** `LightGBMModel.load()` at 359–365 calls the native file loader. It emitted `Model format error, expect a tree here` and terminated the probe process. Git reports `i/lf w/crlf` for `artifacts/lightgbm_model.txt`. Declared first-tree length is 5,425 bytes; CRLF content occupies 5,446. All inter-tree offsets agree after LF normalization; loading that normalized string succeeds. This establishes a local line-ending integrity failure. Cloud copies and Linux deployment behavior are **NOT VERIFIED**. Fix: preserve model bytes through Git/storage (`-text` or enforced LF as appropriate), checksum bundles, and test loads in deployment environments. No saved artifact was repaired during this audit.

**C5 — Ensemble weight search can fail to choose an existing best candidate. CONFIRMED.** `ensemble.py:54–71` initializes the best RMSE to the lower endpoint RMSE and best direction score to the higher endpoint direction score, but initializes the weight to 0.5. Those two best statistics may not describe the same candidate. Strict comparisons may never update the weight. Probe: exact LSTM `[10,20,30]`, imperfect LightGBM `[12,23,34]`, truth `[10,20,30]` leaves 50/50 weights and RMSE 1.5546 despite an available zero-error endpoint. Fix: evaluate every candidate, including endpoints, and select the actual candidate attaining a predeclared objective; calibrate on validation and score on separate test data. [ensemble.py:54](../../model_trainer/models/ensemble.py#L54).

**C6 — Directional accuracy is not forecast-direction accuracy and mixes series. CONFIRMED.** `utils/metrics.py:43–57` compares `diff(predicted)` with `diff(actual)` across concatenated rows, including transitions between unrelated products. It compares consecutive forecasts rather than each forecast's change from its known origin price. It excludes flat actual changes and returns 100% for all-flat truth. This erroneous statistic also drives ensemble selection. Fix: compare `sign(prediction - observed_origin_price)` with `sign(actual_target - observed_origin_price)` for each series/origin/horizon; declare handling of flat moves and ties; aggregate only after per-sample alignment. [metrics.py:43](../../model_trainer/utils/metrics.py#L43), [evaluator.py:42](../../model_trainer/pipeline/evaluator.py#L42).

**C7 — LightGBM/LSTM summary scores use different samples and learning objectives. CONFIRMED.** May logs show 6,637 LightGBM validation rows versus 3,982 LSTM windows. LSTM needs complete 30-target windows and trained series means, so it omits the last 29 retained rows of each eligible series plus short/unseen series. LightGBM is scored on all validation rows. LSTM's checkpoint loss covers 30 outputs, its reported price metrics only the first. The model-comparison plot simply places these incompatible summaries side by side. Fix: report common-origin comparisons as well as coverage, and evaluate all advertised horizons. [trainer.py:411](../../model_trainer/pipeline/trainer.py#L411), [lstm_model.py:329](../../model_trainer/models/lstm_model.py#L329), [lstm_model.py:506](../../model_trainer/models/lstm_model.py#L506), [plotting.py:361](../../model_trainer/utils/plotting.py#L361).

**C8 — Feature and identity definitions drift between training and serving. CONFIRMED design mismatches; collision consequences depend on data.** Training groups by category/name/variant/origin; serving omits category; all omit unit. `days_since_start` uses the minimum date of each DataFrame: global dataset during training, individual product history during serving, and a different global minimum after historical backfills. Generic numeric-column inclusion can accept future-added numeric fields without availability review. Fix: shared canonical series IDs including normalized unit, fixed persisted calendar epoch, explicit feature schema and a single point-in-time feature builder. [prediction_writer.py:135](../../model_trainer/pipeline/prediction_writer.py#L135), [temporal.py:55](../../model_trainer/features/temporal.py#L55), [trainer.py:392](../../model_trainer/pipeline/trainer.py#L392).

**C9 — Published points, uncertainty intervals and fallback outputs are not evaluated. CONFIRMED.** Serving mixes an estimated recent trend into predictions, caps daily changes at 5%, clips levels to ±20% of a seven-row mean and rounds; validation does none of these. Bounds are not adjusted to contain stabilized points. Loaded LightGBM quantiles disappear because persistence saves only point models; fallback bands are arbitrary ±10% for prices or ±50% of predicted residual magnitude. LSTM bands are dropout-plus-input-noise percentiles, without empirical calibration. Exceptions can switch silently to a trend/SMA forecast while the run counts the series as successful. Fix: backtest the exact deployed function; tag algorithm/fallback status; persist quantiles; measure horizon-specific coverage, width and quantile loss; enforce coherent nonnegative ordered bounds. [prediction_writer.py:47](../../model_trainer/pipeline/prediction_writer.py#L47), [prediction_writer.py:288](../../model_trainer/pipeline/prediction_writer.py#L288), [lightgbm_model.py:273](../../model_trainer/models/lightgbm_model.py#L273), [lstm_model.py:545](../../model_trainer/models/lstm_model.py#L545).

**C10 — Synthetic/unversioned truth and destructive forecast replacement prevent prospective validation. CONFIRMED design problem.** Upstream copied prices have no reliable flag; `created_at` is preserved by copying. Prediction rows record no origin time, model version, input cutoff, horizon or fallback identity. Every prediction run deletes previous predictions before nontransactional batch writes; errors are logged but the result still reports attempted row counts and success. Fix: append immutable forecast vintages and observed-price provenance, then publish a complete successful run atomically. Score forecasts after their target dates, using outcomes actually observed. [prediction_writer.py:181](../../model_trainer/pipeline/prediction_writer.py#L181), [prediction_writer.py:323](../../model_trainer/pipeline/prediction_writer.py#L323), [003_metadata_and_lean_predictions.sql:36](../../model_trainer/migrations/003_metadata_and_lean_predictions.sql#L36).

**D. Medium/low-priority issues and conditional risks**

| Finding | Status / consequence / fix | Exact reference |
|---|---|---|
| Categorical vocabulary fitted before splitting | Confirmed validation-distribution exposure, not direct target leakage. Fit mappings on training only; retain explicit unknown codes. Usually much less severe than B1/B2. | `trainer.py:157,383`; `categorical.py:35–47` |
| LSTM raw-target fallback | Conditional **critical leakage** if no expected feature exists: it selects `price_index` and the window includes row `i` while predicting `price_index[i]`. Normal pipeline supplies 16 features, so not active in that path. Fail closed on absent features. | `lstm_model.py:242–244,285–294` |
| LSTM backward filling | Potential within-partition future exposure if called directly on incomplete features. Standard training already calls all-column `dropna`, so this is dormant there. Replace with causal fill and schema validation. | `lstm_model.py:250–254` |
| LSTM training/inference missing-feature policy differs | Train uses ffill/bfill; inference fills missing columns/values with zero. Silently shrinking feature sets or zero-creating missing features can mask schema errors. | `lstm_model.py:236–254,313–317` |
| RSI is divided by product mean | Confirmed: any feature containing `price` but not `pct` is divided by mean price, including dimensionless RSI. Use explicit dimensional feature lists; retain RSI on a fixed scale. | `lstm_model.py:259–281,322–339` |
| Incremental scaling and state | Means are refitted on the current training subset before old weights are loaded; input scale can change under a warm-start network. Optimizer/scheduler state is not restored. `since_date` is ignored and all training data is reused. This is continued training, not new-data-only learning. | `trainer.py:87–110`; `lstm_model.py:257,391–425` |
| Incremental history can contaminate a newly moved cutoff | Risk if historical backfills, revised data or rollback make the current training cutoff earlier than a previous model's exposure. No cutoff/lineage check exists. Never warm-start from a model that has seen the new evaluation period. | `lightgbm_model.py:80–102`; `trainer.py:157–161` |
| `predict_future` is broken and obsolete | Confirmed probe raises `ValueError: setting an array element with a sequence`: a 30-output vector is assigned into one scalar feature. Even if repaired, other rolling/calendar features are not updated and the inverse transform multiplies returns by the mean rather than reconstructing prices from an anchor. Not called by the active writer. Remove or reimplement after choosing direct vs recursive design. | `lstm_model.py:595–634` |
| Loss reporting with dropped batches | `drop_last=True` discards the final batch but training loss divides by total dataset size; slightly understates loss. Fewer than 64 sequences gives zero training batches. Require minimum sample coverage and divide by processed count. | `lstm_model.py:407–410,439–454` |
| Version sorting is wrong | Version number uses current directory count, which repeats after pruning; lexicographic ordering prefers old `v015_2026-04-28` over newer `v011_2026-05-28`. `get_latest_metrics()` ignores manifest latest; pruning also uses this order. Use immutable IDs and timestamp/manifest ordering. | `model_store.py:52,110–122,142–147` |
| Quantile crossings and unbounded returns | No constraints guarantee lower ≤ point ≤ upper or positive prices; LSTM's linear return head can output below −1. Detect invalid outputs and evaluate any constraints as part of the model. | `lstm_model.py:115–123,587–593`; `lightgbm_model.py:300–306` |
| Weak numeric/data validation | Positive infinity would pass `price_index > 0`; null category rows can disappear in groupby; schema does not require variant/origin/unit though later code assumes them. No immutable row IDs are propagated into evaluation. Current snapshot had no infinities/null categories. | `preprocessor.py:28–33,84–87,115` |
| Pagination is not stable or atomic | Date-only ordering has ties; offset pagination can duplicate/omit rows during mutations or nondeterministic tie ordering. Some helper fetches and metadata seeding do not paginate at all. Use stable keys and consistent snapshots/keyset paging. | `fetcher.py:90–99,120–123`; `seed_metadata.py:67` |
| Drift monitoring is weak | Compares all accumulated history with an old full-history distribution, diluting recent changes. Values outside reference histogram bounds are discarded; constant reference can always give PSI 0. Performance drift helper is not called. Use recent windows, overflow bins and actual forecast-outcome monitoring. | `drift_detector.py:36–80,82,147–162`; `trainer.py:119–129` |
| Failures can be promoted as success | LSTM/ensemble exceptions return `{}`; training can still version artifacts and CLI can finish successfully. Partial/stale files can survive. Validate complete run state before promotion. | `trainer.py:200–214,442–446,586–590`; `main.py:43` |
| Registry is not actually thread-safe | No lock protects singleton/loading; model fallback state is incomplete after some load failures, and non-file exceptions are not caught. MC dropout toggles shared model train/eval state. Relevant if reused concurrently. | `registry.py:31–70`; `lstm_model.py:559–574` |
| Scheduler/news mismatch | Imports nonexistent source `data.news_scraper`, catches failure, continues. `.at()` has no timezone argument although logs say UTC. Current news features are not used by training. | `scheduler.py:61–82` |
| Dormant news feature risk | If enabled, same-day articles are included through normalized date ≤ target date, which may expose articles unavailable at forecast time. Ninety-day fetch relative to execution time is unsuitable for historical reconstruction. Currently excluded, so not an explanation for active model leakage. | `news_sentiment.py:60,104–109,139–152`; `trainer.py:387–389` |
| Dormant residual training is in-sample stacking | Base-model predictions on their training rows produce residual targets, rather than temporal out-of-fold predictions. This is not active current validation leakage; enabling it would create an optimistic/unrepresentative meta-training distribution. | `trainer.py:465–492` |
| Legacy files/docs conflict | `.keras`, old scaler files and old meta-model coexist with active PyTorch artifacts. README claims FastAPI/Ridge stacking; comments claim residual training. None establishes current behavior. Remove obsolete artifacts and update documentation after architecture decisions. | `README.md:19–34,67–73`; `trainer.py:2–9` |
| Confidence explanations lack calibration | Reasoning calls confidence “strong” based on number of textual factors, not empirical reliability. It is not part of the active numerical training/writer call chain. | `reasoning.py:230–255` |
| R2 sync is not an atomic bundle protocol | Broad recursive upload/download, no manifest/hash verification or removal of stale local files; download errors continue. Enforce immutable run prefixes and complete-bundle verification. | `r2_sync.py:30–79` |
| Reproducibility dependencies | Only lower version bounds, no lockfile; current venv launchers point to missing Python 3.11. Installed audit runtime differs from the original run. | `requirements.txt:1–31` |
| Migration includes anonymous write policies | If applied, anonymous users are allowed ALL actions on product/prediction tables. Actual deployed RLS is **NOT VERIFIED**. Remove public write access while preserving intended read access. | `003_metadata_and_lean_predictions.sql:33,52` |

**E. Data leakage verdict and complete feature availability inventory**

**Leakage found:** current-target deviation (LightGBM and blends), future-dependent price interpolation (both models' input pipeline), full-dataset outlier fitting/filtering (both), pre-split category fitting (minor distribution exposure), and reuse of selection/calibration data as performance evidence. Conditional leakage paths are separately identified in D. No random `train_test_split`, negative target shift or learned feature-selection stage was found in active source. Shuffling already-constructed LSTM training windows is not itself time-split leakage.

The saved LightGBM has exactly **54 inputs: 19 calendar/trend + 31 price-derived + 4 categorical**. The LSTM uses the marked subset, 16 inputs. Availability below assumes causal, correctly keyed, daily source prices; the current preprocessing violates that assumption even for correctly shifted features.

| Feature names (all inputs enumerated) | Class / LSTM use | Available at origin just before target date t? |
|---|---|---|
| `day_of_week`, `day_of_month`, `day_of_year`, `week_of_year`, `month`, `quarter`, `year`, `is_weekend`, `is_month_start`, `is_month_end` | Calendar / no | Yes, deterministic target-date calendar. |
| `month_sin`, `month_cos`, `dow_sin`, `dow_cos` | Calendar / all four | Yes. |
| `doy_sin`, `doy_cos`, `is_wet_season`, `is_christmas_season` | Calendar / no | Yes; seasonal flags encode fixed assumptions rather than measured future conditions. |
| `days_since_start` | Calendar trend / no | Yes only with a fixed epoch; current transform resets the epoch by input frame. |
| `price_lag_1d`, `price_lag_2d`, `price_lag_3d`, `price_lag_7d`, `price_lag_8d`, `price_lag_14d`, `price_lag_30d` | Lag/target-derived / 1,7,30 | Yes if causal prices; `shift(k)` is grouped correctly, but k is row count after outlier deletion, not always days. |
| `price_rolling_mean_3d`, `price_rolling_std_3d`, `price_rolling_min_3d`, `price_rolling_max_3d` | Rolling/target-derived / none | Correctly uses `shift(1)` before rolling. |
| `price_rolling_mean_7d`, `price_rolling_std_7d`, `price_rolling_min_7d`, `price_rolling_max_7d` | Rolling/target-derived / mean,std | Correctly shifted, with the same source/gap caveat. |
| `price_rolling_mean_14d`, `price_rolling_std_14d`, `price_rolling_min_14d`, `price_rolling_max_14d` | Rolling/target-derived / none | Correctly shifted. |
| `price_rolling_mean_30d`, `price_rolling_std_30d`, `price_rolling_min_30d`, `price_rolling_max_30d` | Rolling/target-derived / mean,std | Correctly shifted. |
| `price_volatility_14d` | Rolling/target-derived / no | Yes: historical std/mean from shifted prices. |
| `price_pct_change_1d`, `price_pct_change_7d` | Momentum/target-derived / both | Yes: `(lag1-lag2)/lag2` and `(lag1-lag8)/lag8`. |
| `price_expanding_mean` | Expanding/target-derived / no | Yes: explicitly shifted before expanding. |
| `price_deviation_from_mean` | Current-target-derived / no | **No: directly uses p_t.** |
| `price_rsi_14d`, `price_macd`, `price_macd_signal` | Technical/target-derived / all three | Shifted RSI/MACD are causal on causal data; signal is an EMA of already-shifted MACD. |
| `product_category_encoded`, `product_name_encoded`, `product_variant_encoded`, `origin_encoded` | Categorical / none | Identity is known; vocabularies must be fitted on training and units must be resolved. |
| Raw `price_index` | Target / absent from normal X | Not available at forecast time; excluded from normal X but used in the unsafe LSTM fallback. |
| News, sentiment, external weather/supply/inflation | External / none active | Not used by the active model path. Do not infer explanatory predictive value from the existence of helper files. |

Sources: [temporal.py:25](../../model_trainer/features/temporal.py#L25), [lag_features.py:50](../../model_trainer/features/lag_features.py#L50), [categorical.py:25](../../model_trainer/features/categorical.py#L25), [lstm_model.py:37](../../model_trainer/models/lstm_model.py#L37). The feature-count log messages themselves are inaccurate: temporal logs 15 for 19 and lag logs 30 for 31.

**F. LightGBM validation**

The implementation genuinely uses `lgb.train` with a chronological validation dataset. Categorical `*_encoded` columns are explicitly declared as categorical in training and validation. The objective is squared-error regression (`regression`), with RMSE and MAE monitoring; no scaling is required for the tree inputs. Early stopping is registered when validation is supplied; it is not merely monitoring the training set. The validation set is nevertheless contaminated by preprocessing/features and reused for selection.

| Configuration | Verified value |
|---|---|
| Boosting / random thresholds | GBDT / `extra_trees=True` |
| Learning rate / maximum rounds | 0.01 / 1,500 |
| Saved point-model trees | 1,472 |
| Leaves / depth / minimum leaf samples | 63 / −1 (unlimited) / 20 |
| Feature / row sampling | 0.8 / 0.8, bagging every 5 rounds |
| L1 / L2 | 0.05 / 0.2 |
| Early stopping patience | 100 rounds; RMSE and MAE are supplied |
| Seeds | No explicit application seed; saved native defaults include seed 0, bagging seed 3, feature seed 2, extra seed 6 |
| Deterministic flag | false in saved parameters |

Sources: [settings.py:64](../../model_trainer/config/settings.py#L64), [lightgbm_model.py:68](../../model_trainer/models/lightgbm_model.py#L68), and the artifact's parameter section beginning at line 30,959. Multiple supplied validation metrics are considered by default, per [LightGBM's official training documentation](https://lightgbm.readthedocs.io/en/stable/Python-Intro.html).

These are plausible starting parameters for tens of thousands of pooled rows, but effective independent sample size is much smaller because products are autocorrelated, sequences overlap and prices are copied. Sixty-three leaves and 1,500 rounds are not validated choices without clean backtesting. Maximum depth is unrestricted. No fair claim about overfitting can be made from the aggregate validation R² or a low error alone. Training RMSE/MAE traces for the saved LightGBM were **NOT VERIFIED**: the saved application log gives validation scores, not a complete retained native training curve.

Saved gain importance begins with rolling mean 3d (17.82%), rolling min 7d (8.08%), rolling max 7d (7.20%), lag 2d (6.84%) and rolling min 3d (6.73%). This is consistent with persistent price levels and correlated inputs; it is not proof of forecasting skill. The leak is rank 22 by gain (0.322%) yet appears in 5,726 splits. Its quantitative contribution requires a clean retrained ablation, not feature-importance speculation.

**Conclusion:** the estimator plumbing is largely conventional; the surrounding experiment is not technically valid as evidence of unseen forecasting performance.

**G. LSTM validation, scaling and horizon**

The active implementation is **PyTorch**, not TensorFlow/Keras. The `.keras` file is a legacy artifact; the active source does not use it.

| Property | Verified implementation |
|---|---|
| Input | batch × 30 retained rows × 16 engineered features |
| Recurrent layers | 2 unidirectional LSTM layers, 128 hidden units |
| Attention | 128→64→1 with tanh and softmax over time |
| Head | concatenate attention context and last hidden state (256); LayerNorm; 256→64 GELU/dropout→32 GELU→30 linear outputs |
| Dropout | 0.2 recurrent inter-layer and head dropout |
| Parameter count | 235,199 with 16 inputs |
| Target | 30 cumulative simple returns relative to price immediately before window's final feature row |
| Optimizer / loss | AdamW, LR 0.001, weight decay 1e−5 / L1 loss on returns |
| Training | batch 64; maximum 200 epochs; patience 35; norm clipping 1.0 |
| Schedule | CosineAnnealingWarmRestarts, T0=20, Tmult=2, minimum LR 1e−6 |
| Incremental | reload weights; LR 0.0001; 66 epochs maximum; fresh optimizer/scheduler |
| Checkpoint | save improved validation loss, then reload best weights |

For target-row index `i`, the implemented sample is:

```text
X = features[i-29 : i+1]       # includes feature row i
anchor = price[i-1]
y[h] = (price[i+h] - anchor) / anchor, h=0..29
```

Including feature row `i` is **not itself leakage**: the normal 16 inputs contain only shifted prices and known calendar values. Their latest raw-price dependence is `i−1`. They do not contain `price_deviation_from_mean` or the same-date raw target. Correctly causal history from training may be used as validation context; that boundary overlap is valid. Training windows are built within training groups, and the 30-label loop stops before training ends, so their targets do not directly cross into validation. Validation prepends up to 29 training rows, then includes later observed validation history for subsequent origins. This is rolling-origin evaluation, not a single 30-day forecast from one fixed cutoff.

Per-series scaling means are fitted from `train_df` only and reused for validation. **No active full-dataset scaler fitting was found.** The means still depend on already-leaky cleaning. Fitting one scalar on all training rows is normal training preprocessing; it should not be mislabeled test leakage. Outputs are returns, not mean-scaled price targets. `predict()` correctly converts output 1 using `anchor * (1 + return)` and training reconstructs actuals identically before MAE/RMSE/MAPE. The unused `targets_scaled` variables and old inverse-transform helper obscure this otherwise valid path.

Saved history: 42 epochs; best epoch 7; best training loss 0.049744 and validation loss 0.034507. At epoch 42 training loss is 0.024784 while validation loss is 0.043274. This is evidence of deterioration after the early optimum; best-checkpoint restoration is appropriate. Losses are average absolute return errors over 30 outputs, not peso MAE. Training loss includes dropout and a denominator issue, so do not directly equate it with validation price metrics.

The primary LSTM design is **direct 30-output prediction**, with weekly/daily modes slicing its first 7/1 outputs. It does not recursively feed each LSTM output back into the model. The serving stabilizer is sequential, but that does not turn the neural model into recursive forecasting. The separate `predict_future()` attempts recursion and is broken. Calendar gaps and the stale serving window invalidate the advertised day alignment; only one output is reported in current training metrics. [lstm_model.py:193](../../model_trainer/models/lstm_model.py#L193), [lstm_model.py:285](../../model_trainer/models/lstm_model.py#L285), [lstm_model.py:506](../../model_trainer/models/lstm_model.py#L506).

**Conclusion:** train-only mean scaling, grouped windows, target reconstruction and best-checkpoint loading have correct elements. The complete LSTM system is not validated because cleaning leaks, rows do not remain daily, testing is absent and serving is misaligned.

**H. Splitting and metric validation**

`time_split()` globally sorts unique dates and uses `floor(0.85 * number_of_dates)` as the validation boundary. All series share that date; it is not a per-series 85/15 row split. This common calendar cutoff is a defensible panel-forecast design and prevents one product's later training date from crossing another's earlier test period. Short/new series need explicit coverage policies.

**Current-snapshot replay, without training:**

| Partition | Actual retained date range | Observations | Share of retained train+validation rows |
|---|---|---:|---:|
| Training | 2019-11-09–2025-09-01 | 114,881 | 77.57% |
| Validation | 2025-09-02–2026-09-17 | 33,217 | 22.43% |
| Independent test | None | 0 | 0% |

Before all-column `dropna`, training is 126,059 rows across 2,154 unique dates (2019-10-10–2025-09-01), and validation is 35,071 across 381 dates. After dropping, training has 2,116 unique dates. The 15% setting refers to **dates**, explaining the 22.43% validation row share. Per-series dates/counts are supplied in `current_series_splits.csv`; the current retained partitions have 101 series each. Analytically the current LSTM training builder would yield 109,308 windows; it was not trained during this audit. Frozen saved-model diagnostic scoring covers 95 series and 30,044 origins through August 19, omitting the latest 29 target rows by construction.

**Original May 28 saved run:** logs record 42,639 fetched rows; 44,974 cleaned rows; 32,940 training rows; 6,637 validation rows (83.23%/16.77% of 39,577 retained rows); 27,225/3,982 LSTM train/validation windows. Independent test rows: zero. **Exact original train/validation date ranges are NOT VERIFIED**, because they were not persisted with the model and no immutable original dataset is available. Do not substitute today's replay dates. Filtering today's data to dates through May 28 produces 141,035 raw rows, not 42,639: historical backfills have materially changed the dataset. A `created_at` filter happens to return 42,639 rows, but copying preserves timestamps and mutations are not versioned, so that is not proof of snapshot identity. [trainer_2026-05-28.log:3](../../model_trainer/logs/trainer_2026-05-28.log#L3), [trainer_2026-05-28.log:20](../../model_trainer/logs/trainer_2026-05-28.log#L20).

MAE is `mean(abs(y−prediction))`; RMSE is `sqrt(mean((y−prediction)^2))`; MAPE is `100*mean(abs((y−prediction)/y))` over nonzero actuals. These formulas are correct for aligned finite one-dimensional inputs. A known-case probe `[100,200]` vs `[110,180]` yields MAE 15, RMSE 15.8113883 and MAPE 10%. LightGBM uses unscaled prices; LSTM's active evaluation restores price units correctly. [metrics.py:9](../../model_trainer/utils/metrics.py#L9).

Limitations:

- Metrics are validation/selection metrics, not independently unseen-test estimates.
- No shape, finite-value or empty-array assertions exist; `(n,1)` vs `(n,)` can broadcast into erroneous matrices. Normal examined callers supply matched 1D arrays.
- MAPE ignores exactly-zero targets; an all-zero set returns 0%, which misleadingly suggests perfect performance. Near-zero prices are not guarded. Active cleaning excludes nonpositive targets, but the utility can still be called elsewhere.
- Price units are original stored prices, nominally PHP per each row's unit. Pooling kg/piece/liter errors is not a single economically uniform price unit. Report normalized-unit per-series metrics and macro summaries in addition to micro averages.
- Overall R² is dominated partly by between-product price levels. A persistence model can have an excellent pooled R² without predicting changes well.
- `evaluate_per_product` combines variants/origins under name alone. Direction metrics and per-product interpretation suffer; MAE/RMSE remain mathematically computable but describe a mixture.
- Historical plots use sample index labelled “Forecast Step (Days)” for a sequence of separate rolling origins; the plotted interval need not be daily or one multi-step trajectory. Some plot limits use only actual extrema and can hide forecast errors. These plots are not additional independent evidence.

**I. Baseline comparison and fair LightGBM-versus-LSTM assessment**

No naive, seasonal-naive or moving-average scoring stage was found in the production trainer. Calling the LightGBM model a “baseline” does not substitute for these forecasting baselines.

The latest **reported validation scores**, preserved in the May 28 metadata, are:

| Model | MAE | RMSE | MAPE | Reported evaluation population |
|---|---:|---:|---:|---|
| LightGBM | 1.9863 | 3.9564 | 1.5864% | 6,637 validation rows |
| LSTM output 1 | 1.2021 | 2.9512 | 0.8870% | 3,982 validation windows |
| Selected blend | 1.3349 | 2.7148 | 1.0484% | Shared LSTM-aligned validation subset, also used for weight selection |
| Naive / seasonal naive / moving average | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | No original aligned baseline predictions saved |

Source: [May 28 metadata](../../model_trainer/artifacts/versions/v011_2026-05-28T11-11-50/metadata.json). The log separately reports LightGBM RMSE **3.0364** on the LSTM-aligned subset versus **3.9564** on all LightGBM validation rows. This demonstrates why the summary cannot establish algorithm superiority.

To add actual evidence, the audit loaded the saved models and compared them with causal calendar baselines on **exactly the same 30,044 target rows, 95 series, 2025-09-02–2026-08-19**. Baseline histories use raw valid per-series prices, reindexed daily with past-only forward fill: naive = previous calendar day's available price; seasonal naive = seven calendar days earlier; moving average = previous seven calendar days. No baseline is fitted on test targets.

**The following is a diagnostic comparison, NOT an unseen-test result or corrected benchmark.** ML features preserve the existing contaminated preprocessing; some dates precede the saved model's May training; missing unit/provenance/cutoff guarantees remain; and the saved LightGBM required in-memory LF normalization. The comparison measures the existing implementation on a common population, not intrinsic algorithm quality.

| Model | MAE | RMSE | MAPE |
|---|---:|---:|---:|
| Naive, calendar persistence | **1.8202** | 6.9773 | 1.1565% |
| Seasonal naive, 7 days | 5.5707 | 16.3548 | 3.3391% |
| Moving average, previous 7 days | 3.5277 | 10.4294 | 2.1315% |
| Saved LightGBM | 3.4201 | 6.2042 | 2.4443% |
| Saved LSTM, output 1 | 1.8335 | 6.2618 | **1.1475%** |
| Saved weighted blend | 2.3615 | **5.4470** | 1.6125% |

LSTM's MAE is slightly worse than calendar persistence while its RMSE is lower and MAPE marginally lower. LightGBM and the blend improve RMSE over persistence in this diagnostic but have substantially worse MAE and MAPE. Thus there is no across-metric dominance even before fixing leakage. Persistence using the LSTM's previous-retained-row anchor yields MAE 1.7824, RMSE 6.2751 and MAPE 1.1202%; this separate variant shows that baseline details matter. It is not the strict calendar baseline above.

On matched category subsets, LSTM has lower MAE than LightGBM in all nine categories; LightGBM has lower RMSE for Corn, Fish, Fruits, Oils, Rice and Vegetables, while LSTM has lower RMSE for Livestock, Poultry and Sugar. These describe saved-model diagnostics only. The models use different information: LightGBM has 54 features including a leak and explicit identities; LSTM has 16 safe-by-formula sequential inputs, 30-row context and a 30-output loss. They are not controlled experiments isolating the algorithm. Full figures are in `calendar_category_metrics.csv`.

An extra diagnostic reconstructed LSTM outputs 7 and 30 on the same origins: LSTM RMSE 14.1319/30.8115 versus flat-anchor persistence 15.3625/36.3821. These are **retained-row horizons**, not guaranteed seven/thirty calendar days, and share the same contamination. They must not be advertised as validated weekly/monthly performance.

**J. Generalization and reproducibility**

Current evidence does not demonstrate generalization to unseen, actually observed future prices. The chronological split is a good foundation, but cannot rescue target leakage, future-dependent cleaning, reused validation labels, copied targets, incomparable coverage and a different serving algorithm. The current results could be inflated; the amount attributable to each issue is **NOT VERIFIED** without corrected retraining and independent testing.

Reproducibility is partial. NumPy and PyTorch CPU/CUDA seeds are set to 42 at module import. Python `random` is not seeded, although no active training use of it was found. Import-time seeding is not reset for each run in a long-lived scheduler. cuDNN deterministic settings and deterministic-algorithm enforcement are absent; LightGBM uses fixed native default seeds but no explicit deterministic policy. Defaults do not imply every run is random, but do not establish reproducibility across versions/hardware. TensorFlow/Keras seeding is not applicable to the active pipeline. Repeated-training variation was **NOT VERIFIED**; no retraining was authorized for this initial audit.

Audit runtime: Python 3.14.3, NumPy 2.4.2, pandas 3.0.1, PyTorch 2.11.0+cpu, LightGBM 4.6.0. Existing project venv launchers fail because their Python 3.11 interpreter path no longer exists. Requirements use lower bounds, and original package/hardware versions were not recorded. Therefore current-snapshot replay is tied to this documented audit environment. Determinism settings and version sensitivity are described in [LightGBM's primary parameter documentation](https://github.com/lightgbm-org/LightGBM/blob/main/docs/Parameters.rst).

Additional **NOT VERIFIED** items: exact original split row identities/dates, original prediction arrays, historical PDF extraction accuracy, whether each stored target was independently observed, actual source-publication availability, deployed R2 bundle integrity and RLS state, calibrated interval coverage, full training-versus-test curves, repeated-seed stability, and unseen-product performance. The audit did not inspect third-party dependency source recursively; it inspected all project-owned module source/configuration/helpers, their relevant upstream ingestion and scheduled execution, local model artifacts, metadata and logs. The source inventory records the inspected module files; bytecode and legacy binaries are not treated as evidence of current source behavior.

**K. Required fixes, in implementation order**

1. Preserve the current code/model/data evidence and label all existing numbers as validation diagnostics. Establish an immutable input snapshot with stable series keys, normalized units, observed/imputed provenance and publication/availability timestamps.
2. Define the deployment contract explicitly: price at target calendar date, forecast origin, permitted history, target units, horizons 1/7/30 and missing/stale-series rules. Resolve blend versus residual architecture before changing individual functions.
3. Remove same-target deviation and unsafe raw-target fallback. Replace interpolation/global outlier selection with point-in-time processing. Fit mappings/scalers/thresholds on training only. Preserve the daily grid and mask missing targets rather than compressing rows.
4. Create chronological train/tuning/final-test partitions and persist boundaries/row IDs. Ensure every 30-output training label ends before the validation/test boundary. Historical context may cross from past into a later partition; target information must not cross backward.
5. Implement shared historical and live feature construction, with an explicit label-free live window for `T+1`. Fix fixed calendar epoch, group keys, feature ordering, scaling and anchor/date alignment. Assert parity between offline-origin and live-origin inputs.
6. Train clean standalone models and naive/seasonal/moving-average baselines. Use identical observed targets/origins, report coverage and per-horizon/per-series/macro metrics. Use temporally out-of-fold predictions if an ensemble is justified.
7. Fix blend selection and directional accuracy. Calibrate any postprocessing and uncertainty on tuning data; freeze the whole prediction function before final testing. Report real-price errors after inverse conversion.
8. Replace loose files with atomic complete model bundles: weights, feature schema, means, mappings, architecture, target transform, split dates, code/dependency versions, quantiles, ensemble state and hashes. Resolve line-ending corruption and correct version sorting/rollback.
9. Fail closed on schema/load failures; label intentionally supported fallbacks. Append forecast vintages with origin, target date and model ID; publish atomically and verify writes. Monitor measured future outcomes and interval coverage.
10. Run the experiments below, document uncertainty and only then decide whether LSTM, LightGBM or an ensemble improves the intended operational objective. Obtain approval before implementing these production changes.

**L. Experiments required before validation can be claimed**

These are recommendations, not completed training experiments. A single split is insufficient evidence of stability across seasons and regime changes in this seven-year panel. Use global **date** folds rather than applying a row-count splitter directly to interleaved products. Expanding-window splitting is the relevant pattern; scikit-learn documents the temporal ordering and equal-spacing assumptions in [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Training-only fitting of preprocessing state follows [scikit-learn's leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).

An initial plan adapted to the actual 2019-10-10–2026-09-17 data is:

| Fold | Model-fit history ends | Inner tuning/calibration target period | Outer evaluation target period |
|---|---|---|---|
| 1 | 2021-12-31 | 2022-01-01–2022-03-31 | 2022-04-01–2022-06-30 |
| 2 | 2022-12-31 | 2023-01-01–2023-03-31 | 2023-04-01–2023-06-30 |
| 3 | 2023-12-31 | 2024-01-01–2024-03-31 | 2024-04-01–2024-06-30 |
| 4 | 2024-12-31 | 2025-01-01–2025-03-31 | 2025-04-01–2025-06-30 |
| 5 | 2025-12-31 | 2026-01-01–2026-03-31 | 2026-04-01–2026-05-31 |
| Locked final retrospective period | Recipe frozen using earlier development data | No selection using final labels | 2026-06-01–2026-09-17 |

These dates are a concrete starting protocol, not a guarantee of adequate observed history for every product. Audit per-series coverage and add shifted/quarterly folds to cover wet/dry and holiday periods. Each origin may only use prices already available. For a 30-day forecast, require its full label interval to stay within the named scored period; do not borrow target labels across its end. For end-of-period scoring through September 17, a 30-day origin must be no later than August 18. Fit/calibration must finish before the scored origin, not merely before its last target. Backfilled historical data can test statistical generalization but cannot reconstruct operational availability without source vintages. Because this audit has already inspected current data and diagnostic scores, retain a genuinely prospective post-audit period after the corrected recipe is frozen for the strongest final claim.

Required checks and acceptance evidence:

1. **Future-invariance tests:** alter every price after an origin and prove its available features/forecast do not change. Alter `p_t` and prove X for forecasting t does not change. Run these through the full preprocessor, not just lag functions. Existing probes deliberately show failures.
2. **Calendar, identity and boundary tests:** synthetic distinct-valued products/units; missing days; new series; long gaps; outlier spikes; duplicate reports. Assert correct `t−1`, `t−7`, `t−14`, `t−30`, exact 30-calendar-day input/output dates, no mixed series and no training target beyond its cutoff.
3. **Offline/live parity and load round-trip:** at the same origin, compare full feature tensors, anchors, all 30 outputs, final stabilized points and intervals before and after bundle reload/rollback. Verify that current-origin inference needs no future labels. Include Windows/Linux byte integrity.
4. **Clean baseline tournament:** naive, seasonal naive, MA7, standalone LightGBM, standalone LSTM and any ensemble on the identical observed origin/target keys; report MAE/RMSE/MAPE, MASE or scale-normalized error, coverage and per-category/unit/series summaries. Define horizon-specific seasonal recursion using only data available at the origin.
5. **Leakage and provenance ablations:** retrain with/without the invalid deviation under otherwise fixed data; compare causal versus existing interpolation and outlier selection; compare independently observed targets versus copied/synthetic rows. Use these only to quantify contamination, not to tune against the final test.
6. **Complete horizon evaluation:** score 1–30 days, especially 1/7/30, using the exact production procedure. Compare direct LSTM outputs with persistence and any correctly implemented recursive LightGBM strategy. Keep fixed-origin and rolling-origin evaluations separate.
7. **Stability and uncertainty:** repeat at least several independent seeds (for example 5), summarize fold distributions and worst-series behavior, and use time-block/series-aware uncertainty estimates instead of treating overlapping windows as independent. Report interval coverage and width by horizon and regime.
8. **Operational replay and prospective audit:** use publication-time data snapshots, append immutable forecasts before outcomes arrive, score every eligible observed outcome including shocks, record fallbacks, and verify retraining cannot use the evaluation future. No model should be promoted solely because a validation score improved.

The resulting evidence must show an economically relevant, stable gain over persistence on clean common future targets. Until then, the implementation supports neither a credible generalization claim nor a fair conclusion that LightGBM or LSTM is the better forecasting algorithm.
