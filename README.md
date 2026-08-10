# Vienna Roof Explorer

Interactive proof-of-concept for extracting building and rooftop attributes from
open geospatial data and aerial imagery in Vienna.

The application combines official City of Vienna building data with computer
vision models trained on rooftop imagery. A user can select a building directly
from an interactive map, inspect official and automatically derived attributes,
and export a structured roof record as JSON.

The project was developed as an AI/ML engineering take-home assessment focused
on rooftop detection and attribute extraction from open-source data.

For the detailed design rationale, source trade-offs, alignment strategy,
confidence semantics, and scaling approach, see [`DESIGN.md`](DESIGN.md).

---

## Overview

For a selected Vienna building, the application combines:

- official building geometry and attributes from City of Vienna open data;
- Vienna orthophoto imagery;
- a multi-label ResNet18 rooftop-feature classifier;
- a ResNet18 roof-material classifier;
- derived roof geometry attributes such as projected area, roof type, and
  estimated surface area;
- structured JSON output with provenance and confidence information.

The application is not restricted to the fixed example buildings included in
`outputs/`. Any selectable building covered by the configured Vienna data
sources can be analysed dynamically.

The fixed examples are included only for reproducibility and inspection.

---

## Extracted attributes

The generated building record can contain information such as:

### Official building data

Depending on availability from the source datasets:

- building ID and address information;
- building footprint and building-part information;
- elevation and height-related attributes;
- construction year, construction period, architect, and typology;
- zoning and protection-zone information;
- municipal-housing information;
- photovoltaic-potential attributes.

### Roof geometry

Derived from the official building geometry and available official roof data:

- roof outline proxy;
- projected roof area;
- estimated roof surface area;
- mean roof slope;
- official or derived roof type.

### Roof material

The roof-material classifier predicts one of:

- `gravel`
- `metal`
- `shingle`
- `tile`
- `unknown`

### Rooftop features

The multi-label classifier can independently detect:

- `chimney`
- `roof-vegetation`
- `rooftop-hvac`
- `skylight`
- `solar`

Because this is a multi-label task, several rooftop features may be present on
the same building.

### Solar potential

Where available from the City of Vienna photovoltaic-potential dataset, the
record can also contain:

- annual yield;
- medium, good, and very-good PV-suitability areas;
- theoretical PV capacity.

---

## Confidence and provenance

Different attributes have different notions of certainty. The application keeps
these semantics separate rather than treating every value as a model
confidence.

- **Official data** retains its source provenance and is not assigned an
  artificial ML probability.
- **Geometrically derived attributes** use engineering-confidence values where
  appropriate.
- **ML predictions** expose raw neural-network probabilities.
- ML probabilities are **not calibrated statistical confidence estimates**.

This distinction is preserved in the generated JSON records so downstream users
can tell whether a value was retrieved directly, derived from geometry, or
predicted by a model.

---

## Roof localization assumption

The roof outline currently uses the official City of Vienna FMZK building
footprint as a **plan-view approximation of the roof boundary**.

It is therefore a geometry-assisted localization approach rather than an
image-segmentation result.

The same official geometry is used to crop and mask the orthophoto used by the
ML models. This provides a stable georeferenced roof-plan proxy and keeps the
visual inference aligned to the selected building.

More detailed roof geometry, such as explicit roof planes, ridges, valleys, or
plane-level orientation, could be added later using dedicated roof segmentation,
LiDAR, oblique imagery, or higher-detail 3D building data.

---

## Data sources

The default workflow uses publicly accessible City of Vienna geospatial
services and imagery.

| Source | Usage |
| --- | --- |
| Stadt Wien – Baukörpermodell / FMZK | building geometry, footprint, parts, and geometry/elevation fields |
| Stadt Wien Orthophoto | visual roof imagery used for ML inference |
| Stadt Wien – Adressen Standorte Wien | address and building identification |
| Stadt Wien – Straßenverzeichnis | resolution of Vienna street codes to street names |
| Stadt Wien – Gebäudeinformation | construction-related metadata |
| Stadt Wien – Bauperioden / Bautypologien | construction periods and building typology |
| Stadt Wien – Photovoltaik Potenzial 2022 | roof type, mean slope, PV suitability, and theoretical capacity |
| Stadt Wien – Schutzzonen | protection-zone information |
| Stadt Wien – Generalisierte Flächenwidmung | zoning and planning information |
| Stadt Wien / Wiener Wohnen – Gemeindebauten | municipal-housing information |

An optional local **BEV DLM Bauwerke** GeoPackage can provide additional
height/elevation attributes, but it is not required for the default reproducible
setup.

High-resolution orthophoto imagery was selected because it provides useful
building-level detail for rooftop objects that would be difficult to recover
from medium-resolution satellite imagery.

Detailed source selection and trade-offs are documented in
[`DESIGN.md`](DESIGN.md).

---

## Machine-learning models

Two separately trained **ResNet18** classifiers are deployed.

### Rooftop-feature classifier

Checkpoint:

```text
models/roof_multilabel_resnet18.pth
```

Task:

```text
multi-label classification
```

Each class receives an independent sigmoid probability. The detection threshold
is stored in the exported checkpoint.

Training notebook:

```text
training/notebooks/roof_multilabel_classification.ipynb
```

### Roof-material classifier

Checkpoint:

```text
models/roof_material_resnet18.pth
```

Task:

```text
single-label multiclass classification
```

The model applies softmax across the material classes and returns the
highest-probability class together with the class distribution.

Training notebook:

```text
training/notebooks/roof_material_classification.ipynb
```

Both models use the same masked roof image and checkpoint-defined evaluation
preprocessing. Model weights and transforms are cached in memory after the
first inference call.

---

## Project structure

```text
vienna-roof-explorer/
├── app/                                  # Flask application and inference pipeline
│   ├── static/
│   │   └── map/
│   │       └── vienna_dynamic_buildings_map.html
│   ├── __init__.py                       # Flask application factory
│   ├── common.py                         # Shared model loading, preprocessing, and cache
│   ├── config.py                         # Paths, CRS, service URLs, and app configuration
│   ├── features.py                       # Rooftop-feature ResNet18 inference
│   ├── map_builder.py                    # Folium UI and building interaction
│   ├── material.py                       # Roof-material ResNet18 inference
│   ├── official_data.py                  # Official Vienna data retrieval and matching
│   ├── roof_imagery.py                   # Orthophoto retrieval, crop, mask, and overlay
│   └── routes.py                         # Flask endpoints and roof-record creation
│
├── data/
│   └── runtime/                          # Temporary per-selection processing artifacts
│       └── .gitkeep
│
├── models/                               # Frozen checkpoints required for serving
│   ├── .gitkeep
│   ├── roof_material_resnet18.pth
│   └── roof_multilabel_resnet18.pth
│
├── outputs/                              # Fixed reproducible submission results
│   ├── buildings/                        # One JSON record per example building
│   ├── overlays/                         # Roof-outline visual examples
│   ├── roof_attributes.json              # Combined structured result set
│   └── roof_attributes_summary.csv       # Compact tabular summary
│
├── tests/                                # Automated application/data-processing tests
│   ├── conftest.py                       # Isolated Flask app and client fixtures
│   ├── test_official_data.py             # Cleaning, identifiers, addresses, and matching
│   └── test_routes.py                    # API, geometry, derivation, confidence, and export
│
├── training/                             # Model-development workflow
│   ├── data/                             # Local labelled data; excluded from Git
│   │   ├── metadata/
│   │   ├── raw/
│   │   │   └── roofs/
│   │   ├── roof_elements/
│   │   │   ├── annotations/
│   │   │   └── images/
│   │   └── roof_material/
│   │       ├── annotations/
│   │       └── images/
│   ├── notebooks/
│   │   ├── roof_material_classification.ipynb
│   │   └── roof_multilabel_classification.ipynb
│   └── outputs/                          # Generated training artifacts; excluded from Git
│
├── .dockerignore
├── .env.example                          # Optional environment overrides
├── .gitignore
├── build_map.py                          # Generates the interactive Folium map
├── compose.yaml                          # Docker Compose configuration
├── DESIGN.md                             # Detailed design and reasoning
├── Dockerfile                            # Reproducible application image
├── pytest.ini                            # Pytest configuration
├── requirements-dev.txt                  # Testing/development dependencies
├── requirements.txt                      # Runtime dependencies
├── run.py                                # Flask application entry point
└── README.md
```

The repository separates **serving**, **model development**, and **submission
outputs**:

- `app/` contains the production-facing Flask application, geospatial
  processing, data-enrichment, and inference code.
- `models/` contains the frozen model checkpoints required by the running
  application.
- `training/` contains the model-development workflow. Raw labelled data and
  generated training outputs are local working data and are excluded from
  version control; the notebooks remain in the repository for methodological
  review and reproducibility.
- `outputs/` contains the fixed building examples used for the submission,
  including structured JSON results and roof overlays.
- `tests/` contains deterministic tests for the main application and
  data-processing logic.
- `data/runtime/` contains temporary files generated while a building is being
  processed and is not part of the persistent result set.

---

## Example buildings and submission outputs

Eight fixed examples are included for reproducibility:

| Building | Building ID |
| --- | ---: |
| Björnsongasse 8 | 25543567 |
| Riedelgasse 8 | 25577993 |
| Gallgasse 76 | 25585094 |
| Griepenkerlgasse 14 | 25604333 |
| Björnsongasse 23 | 25679482 |
| Furtwänglerplatz 44A | 25721841 |
| Klitschgasse 7 | 25743292 |
| Hermesstraße 2 | 25752801 |

Individual building records:

```text
outputs/buildings/
```

Combined structured output:

```text
outputs/roof_attributes.json
```

Tabular summary:

```text
outputs/roof_attributes_summary.csv
```

Visual roof overlays:

```text
outputs/overlays/
```

The application itself remains dynamic; these files provide a fixed set that can
be inspected without rerunning every building manually.

---

## Quick start with Docker

Docker is the recommended way to run the project.

### Requirements

- Docker
- Docker Compose
- internet access for the configured Vienna open-data services and orthophoto
  tiles

Clone the repository:

```bash
git clone https://github.com/marcobadici/vienna-roof-explorer.git
cd vienna-roof-explorer
```

Build and start the application:

```bash
docker compose up --build
```

Open:

```text
http://localhost:5000
```

Stop the application with:

```bash
docker compose down
```

The Docker workflow has been verified from a **fresh repository clone on a
separate machine**.

The first build can take several minutes because the image contains PyTorch and
geospatial Python dependencies.

---

## Local Python setup

Python 3.11 is recommended.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python build_map.py
python run.py
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build_map.py
python run.py
```

Open:

```text
http://127.0.0.1:5000
```

Optional environment overrides are documented in `.env.example`.

---

## Application flow

```text
Interactive Vienna map
        |
        v
Selected FMZK building
        |
        +-------------------------+
        |                         |
        v                         v
Official Vienna data       Orthophoto retrieval
        |                         |
        |                    crop + mask
        |                         |
        |                 +-------+-------+
        |                 |               |
        |                 v               v
        |          Feature ResNet18  Material ResNet18
        |                 |               |
        +-----------------+-------+-------+
                                  |
                                  v
                         Unified roof record
                                  |
                     +------------+------------+
                     |                         |
                     v                         v
                UI side panel             JSON export
```

Official-data enrichment and rooftop inference run independently and are
executed concurrently. The masked orthophoto image is generated once and reused
by both ML models.

---

## Output format

The assessment-focused downloadable record follows this general structure:

```json
{
  "building_id": "25604333",
  "address_code": "...",
  "address": "Griepenkerlgasse 14",
  "sources_used": {
    "roof_outline": "Stadt Wien – Baukörpermodell / FMZK",
    "roof_slope_and_solar": "Stadt Wien – Photovoltaik Potenzial 2022",
    "imagery": "Stadt Wien Orthophoto",
    "rooftop_features": "Fine-tuned ResNet18",
    "roof_material": "Fine-tuned ResNet18"
  },
  "roof": {
    "outline": {},
    "outline_method": "...",
    "projected_area_m2": 0.0,
    "estimated_surface_area_m2": 0.0,
    "type": "...",
    "type_basis": "...",
    "mean_slope_deg": 0.0,
    "material": "..."
  },
  "solar_potential": {
    "annual_yield_kwh_m2a": 0.0,
    "pv_area_medium_m2": 0.0,
    "pv_area_good_m2": 0.0,
    "pv_area_very_good_m2": 0.0,
    "theoretical_pv_capacity_kwp": 0.0
  },
  "rooftop_features": {},
  "confidence": {},
  "score_semantics": "..."
}
```

The interactive application additionally retains a broader official building
profile containing identification, geometry/elevation, building
history/typology, roof/PV information, and planning/status fields.

---

## Tests

Install the development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the test suite:

```bash
python -m pytest
```

The automated tests cover:

- FMZK multi-part building grouping;
- metric footprint and derived geometry calculations;
- API input and bounding-box validation;
- application health checks;
- roof-type and roof-surface-area derivation;
- confidence and provenance fields in exported records;
- filtering of rooftop-feature predictions;
- `/select-building` request processing and saved selection geometry;
- official-data value cleaning;
- identifier normalization;
- Vienna address parsing and address-code matching.

External processing is mocked where appropriate so the tests focus on
deterministic application logic.

---

## Runtime data

Temporary building-selection and imagery-processing artifacts are written to:

```text
data/runtime/
```

These files include the selected building geometry, downloaded/cropped
orthophoto data, masked imagery, and the generated inspection overlay.

Runtime artifacts are intentionally excluded from version control.

The current proof of concept uses shared runtime filenames and targets a
single-user interactive workflow. A multi-user production deployment would use
request- or job-specific temporary storage.

---

## Training workflow

The two model-development notebooks are included under:

```text
training/notebooks/
```

Local training data is organised beneath:

```text
training/data/
```

The local workflow contains:

- source roof images;
- rooftop-element labels/images;
- roof-material labels/images;
- dataset-selection metadata.

Generated training metrics, figures, predictions, and intermediate checkpoints
are written beneath:

```text
training/outputs/
```

Raw training data and generated training outputs are excluded from Git. The
frozen checkpoints required to run the application are committed separately
under:

```text
models/
```

Therefore, **training data is not required to run the submitted application**.

---

## Scaling

The current component is intentionally interactive, but the extraction logic can
be extended to city-wide processing.

A production-scale architecture would use:

- bulk building-geometry retrieval;
- cached orthophoto tiles;
- parallel crop/mask generation;
- batched GPU inference;
- asynchronous job processing;
- persistent building-level records;
- object storage for imagery and overlays;
- model and source-data versioning;
- retries and monitoring around external services.

For larger deployments, many building records could be precomputed and refreshed
only when imagery, source datasets, or model versions change.

See [`DESIGN.md`](DESIGN.md) for the detailed scaling rationale.

---

## Reproducibility

The repository contains the components required to run and inspect the submitted
application:

- application source code;
- Docker configuration;
- dependency specifications;
- trained deployment checkpoints;
- training notebooks;
- automated tests;
- fixed example outputs;
- roof overlays;
- design and reasoning documentation.

A fresh clone has been successfully built and run on a separate machine using:

```bash
docker compose up --build
```

No machine-specific paths or manually copied local files are required for the
default application.

---

## Scope and future work

The proof of concept prioritizes a transparent end-to-end workflow and explicit
source provenance.

Natural extensions include:

- dedicated image-based roof segmentation;
- roof-plane reconstruction using LiDAR or detailed 3D data;
- plane-level orientation;
- larger and more balanced labelled datasets;
- calibrated model probabilities;
- persistent city-wide storage;
- batched GPU inference;
- automated model/data version tracking.

The current architecture is designed so that these components can be introduced
without changing the core building-selection and data-fusion workflow.

---

## Development tools and AI assistance

The project was implemented in Python using Flask, GeoPandas, Rasterio,
Shapely, PyTorch, Torchvision, Folium, and related geospatial libraries.

OpenAI ChatGPT was used during development for code review, debugging support,
implementation discussion, and documentation refinement. Data-source selection,
model-training decisions, validation, system integration, and final verification
were reviewed as part of the submission.

---
