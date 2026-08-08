# Vienna Roof Explorer

Interactive map of Vienna buildings, enriched with official city open-data
(addresses, construction history, zoning, PV potential, ...) and a
fine-tuned rooftop-feature classifier.

## Project layout

```
run.py                      entry point - python run.py
build_map.py                regenerates the map - python build_map.py
requirements.txt            serving dependencies
requirements-training.txt   training-only dependencies (on top of the above)
.env.example                copy to .env to override defaults

app/                        the served application
├── __init__.py             create_app() factory
├── config.py                single source of truth for every path/URL/constant
├── routes.py                 /, /api/buildings, /select-building, /health
├── map_builder.py            builds the Folium map (was generate_map.py)
├── official_data.py          Vienna WFS lookups (was official_building_data.py)
├── roof_imagery.py           download/crop/mask roof imagery (was process_roof_imagery.py)
├── roof_inference.py         runs the fine-tuned classifier
└── static/map/               generated map HTML lives here

models/                      drop a frozen model copy here for deployment
data/runtime/                generated per building-selection (gitignored)
data/bev_bauwerke_vienna.gpkg  optional local BEV dataset (gitignored, absent by default)
training/                    NOT part of the served app - own dependencies, own lifecycle
├── notebooks/
├── data/
├── outputs/
└── scripts/
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # optional, only if you need to override defaults
```

If you'll also be retraining the model:

```bash
pip install -r requirements-training.txt
```

## Running

```bash
python build_map.py    # once, and again whenever app/map_builder.py changes
python run.py
```

Open the URL it prints (defaults to `http://127.0.0.1:5000`).

## Where the model comes from

`app/config.py` checks two locations, in order:

1. `models/roof_multilabel_resnet18.pth` - a frozen copy for deployment
2. `training/outputs/models/roof_multilabel_resnet18.pth` - wherever the
   training notebook's export cell saves it

You don't need to copy anything during development - retrain, and the app
picks up the new weights on its next restart.

---

## Migrating from the old flat layout

If you're moving from the old `app.py` / `generate_map.py` / ... flat
layout, here's what changed and what to do with each old file.

**Old file → new location (already done for you in this package):**

| Old | New |
|---|---|
| `app.py` | split into `run.py` (entry point) + `app/routes.py` (routes) |
| `generate_map.py` | split into `build_map.py` (script) + `app/map_builder.py` (logic) |
| `official_building_data.py` | `app/official_data.py` |
| `process_roof_imagery.py` | `app/roof_imagery.py` |
| `roof_inference.py` | `app/roof_inference.py` |

All the actual logic (the WFS queries, the Leaflet/JS in the map, the
model inference code) is unchanged - only where things live and how they
find their config changed.

**Generated files - don't bother moving these, just delete them.** They
regenerate automatically on the next build/click:
- `vienna_dynamic_buildings_map.html` → recreated by `build_map.py`
- `selected_building.geojson`, `selected_roof*.tif`, `selected_roof_masked.*`
  → recreated on your next building click, now under `data/runtime/`
- `__pycache__/` → recreated automatically

**Your `model_training/` folder** - copy (or move) its contents into
`training/`, matching subfolder names: `data/`, `outputs/`, `scripts/`,
and both notebooks into `notebooks/` (this package only includes
`yolo_finetune.ipynb`, since that's the only one that was shared here -
`roof_multilabel_classification.ipynb` needs to come from your existing
`model_training/notebooks/`).

**Two files I can't account for**, since I never saw their contents -
decide what to do with them yourself before deleting anything:
- `official_data_side_drawer.zip`
- `README_official_data_poc.txt` (might be worth folding into this
  README, or keeping as historical notes in `training/` or a `docs/`
  folder)

**`lod2_cache/` and `backup/`** from your old `app` folder weren't part
of anything I've built with you in this conversation - if they're still
in active use by something, bring them across too; otherwise they look
like leftovers from earlier experiments.
