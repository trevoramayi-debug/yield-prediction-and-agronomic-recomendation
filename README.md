Maize Yield Advisor — Kenya

A yield model and an agronomic recommendation layer for smallholder maize — so investment decisions and input advice stop being guesses.

Built for One Acre Fund's maize programme in Kenya, using the OAF 2021 Agronomic Survey (2016–2020).

Live demo: https://frontend-production-f5fb.up.railway.app/

The problem

One Acre Fund lends inputs to smallholder farmers and backs that loan with training and advisory. Both halves of that model rest on a number nobody has: how much a particular farm will actually harvest.

	The blind decision	Erring low	Erring high
Who to fund	No forecast exists for an applicant plot before the season starts.	A profitable, repayable plot is rejected — the prospect and its margin are lost.	Inputs are advanced against a harvest that never arrives — the loan goes unrepaid.
How much to give	The right input dose for a given farm is unknown.	Fertiliser and seed fall below what the field needs — yield disappoints.	Inputs are pushed past the point of response — capital is spent on kilograms the soil was never going to convert.

A yield model that is honest about its own uncertainty narrows all four cells at once — it scores the applicant farm before the season, and tells the agronomist where the response curve actually flattens.

Objectives
Predict maize yield (kg/ha) for a plot/district given planting inputs — fertiliser rates, seed type, planting date, household characteristics.
Recommend which specific change — planting date, fertiliser, seed, lime, compost, intercropping — would most improve a given plot's yield, and by how much.
Data
	
Source	One Acre Fund 2021 Agronomic Survey — enumerator-collected, farmer-reported, one row per farm-season
Raw scope	81,411 rows × 117 columns, 7 countries, 4 crops
This project's scope	Kenya · maize · long rains · 2016–2020 → 23,674 rows
Districts / sites	51 districts, 2,133 sites
Target	yield_kg_ph — dry maize grain, kg/ha (median 2,930, IQR 1,951–4,109, max 10,131)

Feature families (226 candidate columns, screened down to a validated set):

Family	Kept	Examples
Levers (farmer-controlled)	37	dap_kg_ph, can_kg_ph, n_kg_ph, hybrid_seed_share, plant_date_doy, intercrop_type
Conditions (given to the farm)	94	district, plot_acres, fertility, slope, wealth_index
Weather (CHIRPS + ERA5-Land, joined by grid cell)	90	rain_mm_season, gdd10_feb…oct, tmean_c_*
Shocks (mid-season events)	6	FAW, striga, stemborer, drought, flood, pest_disease

Features are additionally tagged ex-ante (83 — known at planting, the only inputs a pre-season score may use) vs. mid-season (69 — weather already fallen, pests already seen).

Pipeline
data/raw/                        One Acre Fund survey workbook
        │
scripts/clean_kenya_maize.py     → data/cleaned/kenya_maize_cleaned.csv
        │                          Kenya-maize filter, unit standardisation, outlier
        │                          flagging (not deletion), zero-yield → crop-failure flag
        │
scripts/weather_locations.py     → data/weather/weather_points.csv
scripts/fetch_gee_weather.py     → data/weather/monthly_weather_panel.csv
scripts/build_weather_features.py→ data/weather/kenya_maize_weather_features.csv
        │                          CHIRPS rainfall + ERA5-Land temperature, gridded to
        │                          ~950 cells, fetched via Google Earth Engine
        │
scripts/build_features.py        → data/features/kenya_maize_features_full.csv
        │                          data/features/kenya_maize_feature_manifest.csv
        │                          Leakage screening, 4-gate stability check
        │                          (holdout coverage, train-year coverage, the 2016
        │                          reduced-instrument trade-off, holdout variance),
        │                          role + availability-tier tagging per column
        │
scripts/train_district_model.py  → data/models/district_v1/, district_v2/
        │                          5-family ensemble (LightGBM, XGBoost, RandomForest,
        │                          ExtraTrees, entity-embedding NN), plot predictions
        │                          aggregated to district-season means, calibrated
        │                          prediction intervals
        │
scripts/build_lever_curves.py    → data/api/lever_curves.json
        │                          Fixed-effects response curve per controllable lever
        │                          (district × season absorbed), independent of the
        │                          yield model
        │
api/                              FastAPI service — /predict, /recommend, /reference
frontend/                         Deployed demo (Railway)
Notebooks (in order)
#	Notebook	Covers
01	data_understanding_and_cleaning	Structural audit, unit standardisation, outlier handling
02	eda_and_feature_engineering	First-pass features, weather merge
03	feature_analysis_and_importance	Six leakage traps found and fixed, the feature manifest, SHAP, the planting-window finding
04	baseline_gbm	Honest baseline evaluation — calibration, practical accuracy, the district-vs-plot verdict
05	model_tuning	Four-family hyperparameter search, PCA experiments, the district-oracle R² ceiling
06	advanced_models	Neural network member, final 5-model ensemble, the R²≥0.70 rejection table
Results

Model comparison, 2020 holdout (out-of-time):

Model	Holdout R²	MAE (kg/ha)
Ensemble — 5 families (shipped)	0.164	1,120
XGBoost	0.164	1,120
RandomForest	0.156	1,129
ExtraTrees	0.152	1,135
LightGBM (tuned)	0.140	1,133
NeuralNet	0.138	1,130
LightGBM — stock baseline	0.103	1,151
Ridge	0.086	1,169

At the plot level, this is weak — an MAE of 1,120 kg/ha is 38% of the 2,930 kg/ha median harvest. This number cannot underwrite one farmer's loan, and the model does not ship a per-farm figure for that reason.

Aggregated to the district, it works — the unit the model is actually deployed and validated at:

Districts with	Count	R²	MAE (kg/ha)	corr
≥30 plots	50	0.586	329	0.767
≥50 plots	47	0.607	301	0.779
≥100 plots	29	0.661	284	0.821

Why not higher? Tested directly, not assumed — eight separate alternative approaches (geographic re-zoning, panel/history-only models, recalibration, equal-weighting) were tried against a R²≥0.70 target; none held up out-of-time. The mathematical reason: R² can't exceed correlation² for a calibrated predictor, and the feature-to-yield correlation runs 0.56–0.77 across seasons — reaching 0.70 needs ~0.84. Closing that gap needs better inputs (soil tests, GPS-verified plot area, crop-cut yields instead of farmer recall), not a better estimator.

The recommendation layer

The advice does not come from the yield model. Per-plot R² (~0.16) is too weak to trust an inverted search over it. Instead, each controllable lever gets its own fixed-effects response curve — the same district×season-absorbed method that produced the planting-window finding — answering "how does yield move when one decision moves?" rather than "what will the yield be?" This means /recommend still answers correctly even on a deployment where the 125 MB yield-model artifact hasn't loaded.

Three gates stand between a fitted curve and a recommendation:

Support — the target needs ≥200 comparable plots observed near it (only 4% of plots apply lime, 16% any compost — a fitted optimum in that thin a region is a shape drawn through noise).
Evidence — lift ≥25 kg/ha and one-sided t≥1.645, clustered by district. "Do nothing" is a legitimate, returned answer for a plot already near its district's optimum.
Domain — targets are clamped to the fitted 1st–99th percentile; no recommendation is ever an extrapolation.

Selection uses a plateau rule, not an argmax: among targets statistically indistinguishable from the best, the one closest to what the plot already does wins — advice that reads as agronomy, not optimiser output.

API
POST /api/v1/predict      District-scale yield estimate. Unknown fields fall back to
                           survey defaults, so a partial form still scores.
POST /api/v1/recommend     Ranked levers with an expected lift (kg/ha) and a confidence
                           flag each, assembled so a bundle never double-counts one input.
GET  /api/v1/model/summary Training seasons, validation metrics, and stated limits —
                           read from the artifact's own metadata, not hardcoded.
GET  /api/v1/reference/*   districts · seed-types · levers · input-schema
GET  /health · /ready      Liveness / readiness (readiness requires the model artifact)

Interactive docs at /docs once running.

Running locally
bash
pip install -r requirements.txt
uvicorn api.main:app --reload

The service boots even without the (large, not-committed) model artifact present — prediction endpoints return 503 with an actionable message; /recommend, /health, and the reference endpoints keep working, since they depend only on the small, committed lever_curves.json / feature_defaults.json artifacts.

Model artifact: data/models/district_v2/pipeline.joblib is not committed (exceeds GitHub's file-size limit). Set MODEL_URL to an archive to fetch it on first use, or point MODEL_DIR at a locally unpacked copy. Retrain with:

bash
python scripts/train_district_model.py --train 2016-2020 --val 2019,2020 --out data/models/district_v2
Honest limitations
Per-plot predictions are not reliable enough to act on individually — R²≈0.16, deliberately shrunk toward the mean. Only district-season aggregates are surfaced as a confident number.
Districts absent from training carry roughly double the error (543 vs. 271 kg/ha MAE on the 2020 test).
Prediction intervals are conservative — the nominal 80% band covered ~92% of districts in 2020 (75.3% at a mean width of 3,229 kg/ha on a stricter internal check) — treat as a rarely-wrong bound, not a sharp interval; conformal calibration is a planned improvement.
No soil covariate. The single biggest missing input for this model — specified early, never built. Everything else being tuned further would move the ceiling less than adding this would.
Recommendations are associations, not trial effect sizes. District×season fixed effects absorb the place-and-year part of farmers' own input choices, not the unobserved part — each recommendation reports its own uncontrolled contrast alongside the controlled one, so the size of that gap is visible rather than assumed away.
No price data. Advice is expressed entirely in kg/ha; there is no cost or budget layer, because the source survey carries no fertiliser or farm-gate price data to build one on.
What this recommends to One Acre Fund
Fund by district, not by plot — allocate on the district model (R²=0.586, MAE 329 kg/ha) for season-ahead planning; rank cohorts for review rather than auto-deciding a single loan. If a per-plot figure is ever shown, show its interval beside it, labelled indicative.
Dose to the plateau, not the peak — target ~120 kg/ha DAP and ~120 kg/ha CAN, where the response curve flattens, not where it peaks. Close the 16% of plots using no hybrid seed. Do not push lime or intercropping on the evidence gathered so far.
Move planting date first — it costs nothing, and roughly a third of plots sit on the wrong side of it.
Team
	
Wekesa Godwin	Weather pipeline, deployment & front-end
Mohammed Ismail	Data cleaning pipeline & backend API
Ibrahim George	Feature engineering
Mary G. Kahiga	Modelling
Trevor Amayi	Modelling, documentation & presentation deck
Alvin Maina	Data cleaning, documentation & presentation deck
Repo layout
data/
  raw/            source survey workbook (not committed — large)
  cleaned/        output of clean_kenya_maize.py
  weather/        CHIRPS/ERA5 panel, climatology, joined weather features
  features/       modelling-ready feature files + manifest
  models/         saved DistrictPipeline artifacts (district_v1, district_v2)
  api/            lever_curves.json, feature_defaults.json — small, committed
scripts/          the full pipeline, cleaning through training and scoring
notebooks/        01–06, the full analysis in order
api/              FastAPI service
frontend/         demo UI
Documentation/    deployment guide, feature-engineering writeup, this project's CRISP-DM report
