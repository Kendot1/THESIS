# Foodcast external context layer

Status: historical acquisition and reconstruction in progress. Verified FAO
features have been tested in isolated research comparisons; none has been
admitted to production training. The broader
MAE <= 5, RMSE <= 5, MAPE <= 5% target has not been achieved.

## Reproducible stages

Run from the repository root with the project Python environment. HTML parsers
use BeautifulSoup; PDF extraction uses the installed Poppler `pdftotext`.

```powershell
python -B model_trainer/external_context/archive_sources.py --source da_damage_20250720 --source da_damage_20250722 --source da_damage_20250724 --source da_cordillera_mapping --output audits/my_capture
python -B model_trainer/external_context/build_context.py --capture audits/my_capture/capture_TIMESTAMP.json --output audits/my_capture/build_v1
python -B model_trainer/external_context/archive_sources.py --source da_vegetable_roadmap --source boc_reference_index --output audits/my_discovery
python -B model_trainer/external_context/build_roadmap_mapping.py --capture audits/my_discovery/capture_TIMESTAMP.json --output audits/my_discovery/mapping_v1.json
python -B model_trainer/external_context/inventory_customs.py --capture audits/my_discovery/capture_TIMESTAMP.json --output audits/my_customs --download-all-rice
python -B model_trainer/external_context/audit_pdf_text.py --capture audits/my_customs/capture_TIMESTAMP.json --output audits/my_customs/text_audit
python -B model_trainer/external_context/ocr_customs.py --capture audits/my_customs/capture_TIMESTAMP.json --text-audit audits/my_customs/text_audit/text_layer_audit.json --output audits/my_customs/ocr --from-year 2017
python -B model_trainer/external_context/extract_customs_candidates.py --ocr-root audits/my_customs/ocr --output audits/my_customs/candidate_review_queue.json
```

Replace `capture_TIMESTAMP.json` with the manifest printed by the preceding
collector. New captures preserve raw bytes by SHA256 and record request URL,
final URL, response headers, UTC capture time, and failures. Offline builders
check source hashes before extraction. Existing changed outputs require a new
version directory. These scripts support repeatable updates; no scheduled job
has been installed and no unreviewed extraction automatically enters training.

OCR resumes completed pages only after checking the original PDF hash, page,
settings and all output hashes. Each page retains a PNG, text and TSV word boxes.
Run `extract_customs_candidates.py --allow-partial` only for a clearly labelled
partial review queue while OCR is ongoing. Recognized currency tokens and nearby
country codes are candidates; merged commodity cells are not assigned grades
automatically. Reviewed numeric observations are built separately with
`build_customs_reviewed.py` and `customs_reviewed_rows.json`.

`customs_publication_sources.json` holds public archive queries and historical
index replays. Pass it as `archive_sources.py --registry ...` to capture evidence.
`verify_archive_availability.py --capture ... --evidence-capture ... --output ...`
matches original PDF payloads to independent archive capture digests. Multiple
evidence captures may be supplied. A match establishes availability by the
archive timestamp, not by the PDF's earlier issue date. Current retrieval time,
historical replay time and original publication time remain distinct.

## Feature engineering and availability

DA damage records retain report date, null assessment cutoff when unstated,
publication and modification metadata, commodity scope, literal geography,
source value/unit, normalized value/unit, approximation or bound, exact match
and article-text offsets. Curated specifications fail on changed quantities or
ambiguous matches. Support budgets and loans are excluded from damage metrics.
Reported damage totals are cumulative event snapshots; never sum successive
updates. A total and its rice/corn components are not independent additive losses.

Current HTML publication metadata alone does not establish that the captured
numerical vintage was available on that date. Historical availability remains
null pending corroboration. Capture establishes current availability only;
it does not refresh an old observation's reference age. No automatic coercion
of these rows into `features.external_vintages.ObservationRelease` occurs.

The roadmap documents cabbage and cauliflower routes from Kabayan, Benguet,
through NVAT to Metro Manila. This supports candidate geographic relationships,
not retail-observation source labels. National highland production shares and
shares shipped to Greater Manila cannot become commodity-specific source
weights. The roadmap's planning years and URL upload folder are not publication
proof. Geography, product match and publication review remain separate checks.

Customs' archive is mixed commodity coverage, including resin. Its table has
duplicate links and potentially inconsistent year/period labels. The inventory
preserves them; the rice selector only chooses rows explicitly labelled rice.
PDF inspection is still required. Inspected rice references are USD/kg by grade
and country, not imports in metric tons or measured NCR retail prices. Preserve
tariff heading, grade, country and revision date during numeric reconstruction.
Never convert USD reference prices to PHP using future exchange rates.

## Missing data treatment

- Unknown or failed acquisition is missing, never a zero-impact observation.
- An incomplete event inventory does not prove that no disaster occurred.
- Retain approximate amounts and strict bounds; a `more than` value is not exact.
- Do not interpolate disaster losses or allocate aggregate damage to regions.
- No forward fill is enabled yet. Candidate future carry-forward must be bounded
  by publication availability and reference age, with age and missing flags.
- Retain historical vintages separately. Later estimates cannot overwrite data
  visible at an earlier forecast origin.
- Scanned PDFs need OCR and visual number/row checks. A text layer is not proof
  that extracted decimals, dates, percentages or commodity names are correct.

## Evaluation protocol still to execute for the new datasets

Retain a price-only control with exactly the same rows, forecast origins and
horizons as each external experiment. Evaluate A weather, B disasters, C supply,
D fuel/transport, E trade, F economic, G selected combinations, H best validated
features. Investigate availability-respecting lags 0, 1, 3, 7, 14 and 30 days in
training/tuning data only. Compare MAE, RMSE and MAPE overall and by commodity,
category and horizon; include missingness/coverage and origin-level consistency.
Do not call all-missing features an executed ablation. Do not select lags using
final holdout results or compare different validation scopes as improvements.

Earlier exploratory external experiments and their failures remain in
`audits/target5_20261002`. They are prior evidence, not the completed A-H matrix
for this context layer. Final October 2026 food-price holdout labels remain sealed
until the full period closes. Nothing here changes the active model pointer.

## Deliverable status

| Required output | Current authoritative artifact / remaining work |
|---|---|
| External Dataset Inventory | `sources.json`; captured Customs link inventory; expand 2018-2026 coverage |
| Source Reliability Assessment | Registry priority/PIT/coverage notes; verify each extracted historical vintage |
| Commodity-to-Region Mapping | DA broad group and two roadmap routes; remaining commodities and weights pending |
| Point-in-Time Availability Matrix | DA seed timing unverified; Customs/DOE payload matches and 30 verified FAO releases; family coverage remains incomplete |
| External Data Processing Pipeline | Collectors, checked seed builder, mapping builder, PDF text audit; additional parsers pending |
| Feature Engineering Documentation | This document; prospective feature designs must be validated before use |
| Missing Data Report | Seed build `missing_data_report.json`, PDF extraction coverage; full aligned panel pending |
| Feature Ablation Results | Two verified FAO comparisons completed; full common-scope A-H comparisons pending |
| Per-Commodity Performance Comparison | Both FAO experiments include product/category/horizon/origin CSVs; remaining families pending |
| Recommended External Feature Set | No new admissions yet; experiments determine retained set |
| Reproducible dataset-building scripts | This package, raw manifests and extraction specifications |
| Final training recommendation | Pending sufficient PIT-safe data and controlled out-of-sample results |

Completion requires the whole requested context layer and validation outcome;
passing parser tests or producing an inventory does not prove model improvement.

## Reconstruction update

See `audits/external_context_20261004/OCR_AND_AVAILABILITY.md` for the subsequent
OCR work, 26 visually reviewed price rows, independent historical payload
matches for 76 PDFs, and the remaining timing and numerical-review limitations.

The later `audits/external_context_20261004/COMPLETED_OCR_AND_CAUSAL_COVERAGE.md`
records the completed 1,472-page OCR job, full review queue, 146 independently
dated PDF payloads, and the causal research adapter. Use
`customs_reviewed_20240219_v2.json`; its v1 is quarantined for incorrect tariff
groupings. The adapter and six-lag coverage audit do not constitute an executed
forecast ablation or production feature admission.

Additional commands:

```powershell
python -B model_trainer/external_context/build_customs_reviewed.py --capture CAPTURE.json --ocr-root OCR_DIRECTORY --review REVIEW_SPECS.json --output REVIEWED_OUTPUT.json
python -B model_trainer/external_context/inventory_archived_customs.py --capture HISTORICAL_INDEX_CAPTURE.json --output ORIGINAL_LINKS_DIRECTORY
python -B model_trainer/external_context/verify_archive_availability.py --capture CAPTURE.json --evidence-capture CDX_CAPTURE.json --allow-official-migration-matches --output AVAILABILITY.json
python -B model_trainer/external_context/audit_customs_feature_coverage.py --reviewed REVIEWED_OUTPUT.json --availability AVAILABILITY.json --output COVERAGE.json
```

The optional migration match requires the same official publisher, filename and
payload; it preserves both URLs. `NA` in reviewed Customs tables is stored as
null with a source-missing reason, never zero. Research quote freshness is
measured from the applicability period's start, not its recent archive discovery.

## Fuel and FAO acquisition

See `audits/external_context_20261004/FUEL_AND_FAO_RECONSTRUCTION.md` for the
548-link DOE inventory, 18-PDF format pilot, 56 archived FAO newsletters and 40
corroborated declared-date release records. The subsequent verification recovered
30 historical values with matched payload digests and exact archive timestamps.
Use `fao/dated_releases_v3/releases.json`; earlier versions are superseded.
`fao/context_v1.json` attaches the visually reviewed post-July-2020 index
definition and audits 288 causal lookups. These records are eligible for isolated
research comparisons; production admission requires predictive evidence. DOE
numeric extraction and the broader A-H comparisons remain incomplete.

```powershell
python -B model_trainer/external_context/inventory_fuel_economic.py --capture CAPTURE.json --source INDEX_SOURCE_ID --kind doe --sample-per-year 2 --output INVENTORY_DIRECTORY
python -B model_trainer/external_context/extract_fao_newsletters.py --capture NEWSLETTER_CAPTURE.json --output CANDIDATES_DIRECTORY
python -B model_trainer/external_context/extract_fao_releases.py --capture RELEASE_CAPTURE.json --newsletters CANDIDATES_DIRECTORY/candidates.json --output RELEASES_DIRECTORY
python -B model_trainer/external_context/prepare_fao_replays.py --capture CDX_CAPTURE.json --output REPLAY_SOURCES.json
python -B model_trainer/external_context/archive_sources.py --registry REPLAY_SOURCES.json --output REPLAY_DIRECTORY
python -B model_trainer/external_context/verify_fao_replays.py --capture REPLAY_CAPTURE.json --releases RELEASES_DIRECTORY/releases.json --output VERIFIED_REPLAYS.json
python -B model_trainer/external_context/build_fao_context.py --verified VERIFIED_REPLAYS.json --verified SECOND_VERIFIED_BATCH.json --methodology-capture METHODOLOGY_CAPTURE.json --output CONTEXT.json
```

Execution access was restored. All 177 trainer tests passed, including 34 fuel/FAO
tests. The authoritative verification outputs are `fao/verified_replays_v2.json`
and `fao/verified_replays_retry_v1.json`. One digest mismatch remains excluded.
The historical parser explicitly records malformed original Article metadata
when a unique date literal matches the visible date. It does not repair source
bytes or suppress mismatches. The research adapter delays availability by the
requested lag, measures age from the reference month end at the actual origin,
and retains missing values and indicators.

The completed `audits/external_context_20261004/fao_ablation_v1.py` comparison
chose six candidate lags on early tuning only, using a fixed 60-day age limit.
Its matched calibrated control scored MAE/RMSE/MAPE 7.577679 / 21.349366 /
4.866177%; the FAO variant scored 7.612994 / 21.690576 / 4.885012%. Reject this
tested global-index feature set. See `FAO_ABLATION_FINDINGS.md` and the saved
per-product/category/horizon CSVs. This single experiment does not complete the
requested A-H comparisons or achieve the <=5 accuracy targets.

## DOE historical reconstruction

`audits/external_context_20261004/DOE_RECONSTRUCTION_FINDINGS.md` records the
completed acquisition of 517 North Luzon PDFs and 300 identical historical
payload matches. `verify_doe_availability.py` checks official legacy hosts and
payload identity across the CMS migration. Available-by times are archive
capture times, never filenames or monitoring dates.

`extract_doe_diesel.py` produces a coordinate-preserving review queue for
supported vertical product tables. The authoritative v5 queue has 3,314
candidates: 2,962 numeric ranges and 352 missing placeholders. It rejects
ambiguous city alignment, unsupported layouts and company-extrema mismatches.
`build_doe_reviewed.py` pins sixteen visually reviewed ranges across four documents
to their original PDF hash, page and dates. Wrapped 2024–2025 headers and merged
product/price extraction lines are supported; literal province labels are
preserved for review. The printed RAINGE header and merged adjacent header cells
are explicitly handled. All earlier 2,753 v3 candidates retain identical core values.
`audit_doe_candidate_coverage.py` checks 288 timing combinations without reading
target prices. Coverage now reaches all three early-tuning dates at 90-day
freshness, but no fixed origin has 14/30-day candidates. Freshness is not widened
to optimize development coverage. The OCR runner processed 84 pages in 16
historically matched PDFs; `audit_doe_ocr.py` validates their provenance and
indexes literal dates/diesel lines, without certifying OCR values.
Unit mapping, broader numerical/geographic review and the fuel model
comparison remain incomplete. No DOE values are currently admitted to training.

## FAO commodity-specific momentum comparison

`audits/external_context_20261004/FAO_SECTOR_ABLATION_FINDINGS.md` records the
completed follow-up using the same 30 verified historical release payloads.
`extract_fao_sectors.py` checks original bytes and release metadata;
`build_fao_sector_context.py` applies the hash-pinned `fao_sector_review.json`.
The authoritative `fao/sector_context_v2.json` contains 128 reported monthly
percentage changes and 22 explicit missing values across five sectors. Point
changes, annual comparisons and component-commodity percentages are not
substituted for the selected sector's monthly change.

`fao_sector_features.py` enforces historical availability, six candidate lags,
and a fixed 60-day reference-age limit. A newer explicit missing value prevents
backfilling an older number. Category mappings are documented economic context;
they are not shipment weights or domestic price transmission estimates.

The completed `fao_sector_ablation_v1.py` ran 45 fits with lag selection on early
tuning only. Calibrated MAE/RMSE/MAPE were **7.570389 / 21.344533 / 4.875605%**,
versus the matched control's **7.577679 / 21.349366 / 4.866177%**. Results are
mixed and this feature design is **LOW PRIORITY**, with no production admission.
The independent verifier reproduced 384 metric tuples, 45 model hashes and
1,836 historical lookups. All 221 trainer tests passed in
`reconstruction_tests_20261004_v10.log`.

Vegetables account for 93.54% of squared error in this evaluation and have no
new external feature in this experiment. The next research priority is dated
vegetable supply, crop damage and source-region conditions. Full A-H comparisons
and the requested accuracy targets remain incomplete.

## Regional vegetable source pilot

`audits/external_context_20261004/DA_CAR_VEGETABLE_FINDINGS.md` documents 19
archived DA-CAR articles, 21 successful annual public search pages and the linked
public price-folder inventory. The captured 2025 listing exposes only
October-December, after the development forecast origins. Six exact-URL archive
queries returned no historical captures through 2025. This is a partial source
inventory with no newly admitted training observations. Geographic group routes,
aid totals and ambiguous shipment dates are preserved without inventing crop
weights or assigning aggregate damage to individual vegetables.

`inventory_public_drive.py` decodes the captured public listing without executing
website scripts. `inventory_car_search.py` extracts only main-content official
article/page links. Both retain source hashes and mark historical availability
unverified. The full suite passed 228 tests, followed by 11 focused inventory
tests after four further search-parser checks were added.

The later regional pagination pass recovered all three failed search queries and
expanded discovery to 45 distinct URLs. Thirty-eight are now archived; seven
article requests timed out. Consult the acquisition update at the top of the
regional findings report for current counts and capture manifests.

## NDRRMC historical report pilot

`audits/external_context_20261004/NDRRMC_RECONSTRUCTION_FINDINGS.md` records three
verified original historical PDF payloads (576 pages) and 18 visually reviewed
values in three Ilocos Norte crop rows. `ndrrmc_replays.py` verifies exact archive
timestamps and payload hashes; `build_ndrrmc_reviewed.py` applies the pinned
visual-review specification. Current original PDF requests returned 403, while
three independent historical copies were recovered without changing origin URLs.

The reviewed August 2024 crop rows were first verified available in March 2025,
229 days later. They are unsuitable for the recent-disruption freshness limits
being investigated. High-value crops remain a combined group, with no invented
individual vegetable allocation. No feature is admitted and no forecast ablation
is claimed from these rows. The complete suite passed 241 tests, followed by 14
focused replay/row tests after five additional extraction checks were added.
