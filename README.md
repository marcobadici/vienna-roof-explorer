# Vienna Roof Explorer

Interactive proof-of-concept for **rooftop detection and attribute extraction from open geospatial data and aerial imagery in Vienna**.

The application combines authoritative City of Vienna building data with high-resolution orthophoto imagery and two fine-tuned ResNet18 classifiers. A user can select a building directly on the map, inspect official and AI-derived information in a side panel, and export a structured roof record as JSON.

The project was developed for the PropX AI/ML Engineer technical assessment.

For the detailed source rationale, data-fusion approach, confidence semantics, scaling strategy, and design trade-offs, see [`DESIGN.md`](DESIGN.md).

---

## What the application does

For any selectable Vienna building in the supported map area, the application:

1. retrieves the official FMZK building geometry;
2. groups multi-part building geometries where necessary;
3. enriches the selected building with additional official Vienna datasets;
4. downloads the corresponding Vienna orthophoto imagery;
5. crops and masks the imagery using the selected building polygon;
6. runs roof-material and rooftop-feature classifiers;
7. derives roof-level geometric attributes where supported;
8. displays the result in the interactive building drawer;
9. exports a structured JSON roof record.

The application is **not restricted to the fixed submission examples**. The example buildings under `outputs/` are included for reproducibility, comparison and reviewer inspection only; the application itself retrieves selectable Vienna buildings dynamically.

---

## Extracted roof attributes

The assessment-focused roof record includes:

- roof outline / polygon;
- projected roof area;
- estimated roof surface area;
- mean roof slope;
- roof type;
- roof material;
- visible rooftop features;
- photovoltaic-potential attributes;
- per-attribute confidence/provenance information.

### Rooftop feature classes

The multi-label classifier detects:

- `chimney`
- `roof-vegetation`
- `rooftop-hvac`
- `skylight`
- `solar`

Several classes can be present on the same roof.

### Roof material classes

The multiclass roof-material model predicts:

- `gravel`
- `metal`
- `shingle`
- `tile`
- `unknown`

---

## Roof localization

The current implementation uses **geometry-assisted roof localization**.

The official City of Vienna FMZK building footprint is used as a **plan-view approximation of the roof boundary**. The same geometry is used to crop and mask the corresponding orthophoto before ML inference.

This provides a reliable georeferenced building extent without claiming that the polygon is an independently segmented visible-roof boundary.

A dedicated image-segmentation or 3D roof-plane reconstruction component would be a natural future extension.

---

## Data sources

The default workflow uses publicly accessible City of Vienna geospatial services and imagery.

Main sources include:

| Source | Usage |
| --- | --- |
| Stadt Wien – Baukörpermodell / FMZK | building geometry, footprint and geometry/elevation attributes |
| Stadt Wien Orthophoto | visual roof imagery |
| Stadt Wien – Adressen Standorte Wien | address and building identification |
| Stadt Wien – Gebäudeinformation | construction-related metadata |
| Stadt Wien – Bauperioden / Bautypologien | construction periods and typology |
| Stadt Wien – Photovoltaik Potenzial 2022 | roof type, mean slope and PV-potential attributes |
| Stadt Wien – Schutzzonen | protection-zone information |
| Stadt Wien – Generalisierte Flächenwidmung | zoning/planning information |
| Stadt Wien / Wiener Wohnen – Gemeindebauten | municipal-housing information |

An optional local **BEV DLM Bauwerke** GeoPackage can provide additional height/elevation attributes, but it is not required for the default reproducible setup.

High-resolution, top-down orthophoto imagery was selected because it provides substantially more useful building-level detail for rooftop objects than medium-resolution satellite imagery such as Sentinel-2. According to the City of Vienna product information, the current dataset is a **True Orthophoto**, covers the **entire Vienna city area**, and the downloadable orthophoto is provided at **15 cm resolution**. True-orthophoto processing is particularly useful here because building roofs are represented in their corrected planimetric position.

The default workflow uses publicly accessible Vienna services and does not require a paid commercial imagery API or API key. City of Vienna MA 41 Open Government Data is available free of charge under **CC BY 4.0**, with the required attribution `Datenquelle: Stadt Wien - data.wien.gv.at`.

Top-down imagery also simplifies building-to-image alignment and avoids many of the roof-visibility limitations of street-level imagery, although vegetation, shadows and complex roof geometry can still reduce visual interpretability.

More detailed source-selection reasoning, including the considered alternatives and their trade-offs, is documented in [`DESIGN.md`](DESIGN.md).

---

## Machine-learning models

Two ImageNet-pretrained **ResNet18** models are deployed.

### Rooftop feature classifier

Checkpoint:

```text
models/roof_multilabel_resnet18.pth
```

Task:

```text
multi-label classification
```

The model uses independent sigmoid probabilities for each rooftop feature and applies the threshold stored in the exported checkpoint.

Training workflow:

```text
training/notebooks/roof_multilabel_classification.ipynb
```

### Roof material classifier

Checkpoint:

```text
models/roof_material_resnet18.pth
```

Task:

```text
single-label multiclass classification
```

The model uses softmax probabilities and returns the highest-probability material class.

Training workflow:

```text
training/notebooks/roof_material_classification.ipynb
```

Both deployment models use the same masked roof image and checkpoint-defined evaluation preprocessing.

---

## Confidence and provenance

The application separates three different concepts rather than treating all scores as interchangeable:

- **official source** — a value directly matched from an authoritative dataset;
- **engineering confidence** — a reliability score attached to an approximation or derived value;
- **model probability** — a raw neural-network output.

Raw ML probabilities are **not presented as calibrated statistical confidence estimates**.

Examples:

- mean roof slope: direct official-source value;
- projected roof area: FMZK plan-view proxy with engineering confidence;
- estimated surface area: derived from projected area and official mean slope;
- roof material: raw model probability;
- rooftop features: per-class raw model probabilities.

Full rationale is documented in [`DESIGN.md`](DESIGN.md).

---

## Example buildings

Eight fixed examples are included for reproducibility:

| Building | Building ID |
| --- | ---: |
| Ferdinandstraße 25 | 25537828 |
| Greyledergasse 2 | 25538424 |
| Laverangasse 62 | 25649228 |
| Postgasse 19 | 25682816 |
| Rosenhügelstraße 192 | 25688838 |
| Laverangasse 58 | 25723786 |
| Winkelbreiten 7 | 25743295 |
| Prater 119 | 25769050 |

Their individual records are stored under:

```text
outputs/buildings/
```

The combined machine-readable output is:

```text
outputs/roof_attributes.json
```

A compact tabular overview is available as:

```text
outputs/roof_attributes_summary.csv
```

A small index of the fixed examples and their available visual artifacts is stored as:

```text
outputs/example_buildings.csv
```

Five of the eight buildings also include paired visual artifacts. The exact masked orthophoto images passed to the ML models are stored under:

```text
outputs/model_input/
```

The corresponding roof-plan inspection overlays, showing the official FMZK footprint over the orthophoto, are stored under:

```text
outputs/overlays/
```

The shared building ID in each filename links the JSON record, model input and overlay for the same building.

---

## Project structure

```text
vienna-roof-explorer/
├── app/
│   ├── __init__.py
│   ├── common.py
│   ├── config.py
│   ├── features.py
│   ├── map_builder.py
│   ├── material.py
│   ├── official_data.py
│   ├── roof_imagery.py
│   └── routes.py
│
├── data/
│   └── runtime/
│       └── .gitkeep
│
├── models/
│   ├── roof_material_resnet18.pth
│   └── roof_multilabel_resnet18.pth
│
├── outputs/
│   ├── buildings/                        # 8 individual building JSON records
│   ├── model_input/                      # 5 masked images used for ML inference
│   ├── overlays/                         # 5 matching FMZK roof-plan overlays
│   ├── example_buildings.csv             # Example index and artifact availability
│   ├── roof_attributes.json              # Combined structured result set
│   └── roof_attributes_summary.csv       # Compact tabular summary
│
├── tests/
│   ├── conftest.py
│   ├── test_official_data.py
│   └── test_routes.py
│
├── training/
│   ├── data/                             # Local labelled data; excluded from Git
│   ├── notebooks/
│   │   ├── roof_material_classification.ipynb
│   │   └── roof_multilabel_classification.ipynb
│   └── outputs/                          # Generated training artifacts; excluded from Git
│
├── .dockerignore
├── .env.example
├── .gitignore
├── build_map.py
├── compose.yaml
├── DESIGN.md
├── Dockerfile
├── pytest.ini
├── requirements-dev.txt
├── requirements.txt
├── run.py
└── README.md
```

Raw training data, generated training outputs and runtime artifacts are intentionally excluded from version control.

---

## Quick start with Docker

Docker is the recommended way to run the project.

### Requirements

- Docker
- Docker Compose
- internet access to retrieve the configured Vienna open-data services and orthophoto tiles

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

The Docker workflow has been verified from a **fresh repository clone on a separate machine**.

The first build can take several minutes because the image contains PyTorch and geospatial Python dependencies.

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

Configuration can optionally be overridden through environment variables documented in `.env.example`.

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

Official-data enrichment and rooftop inference are independent and are executed concurrently. The masked orthophoto is generated once and reused by both ML models.

---

## Output format

The compact downloadable result has the general structure:

```json
{
  "building_id": "25743295",
  "address_code": "239339",
  "address": "Winkelbreiten 7",
  "sources_used": {},
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
  "solar_potential": {},
  "rooftop_features": {},
  "confidence": {},
  "score_semantics": "..."
}
```

The exported record keeps source provenance and score semantics explicit: direct official values, engineering-confidence estimates and raw model probabilities are represented separately. The interactive application also retains a broader official building profile containing identification, geometry/elevation, building history/typology, roof/PV information, and planning/status fields.

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

The tests cover important API behavior and official-data processing logic.

---

## Runtime data

Temporary building-selection and imagery-processing artifacts are written to:

```text
data/runtime/
```

These include the selected building geometry, orthophoto crop, masked imagery and generated overlay.

They are intentionally excluded from Git.

The current proof of concept uses shared runtime filenames and is designed for a single-user interactive workflow. At production scale, these would be replaced by request- or job-specific storage.

---

## Training data

The raw labelled training imagery is not stored in the repository.

The rooftop training images were **manually labelled using Roboflow** as the annotation and dataset-management interface. Roboflow was used to create and organise the labels; the underlying roof imagery was derived from the Vienna orthophoto workflow used for the project.

The training notebooks use repository-relative paths and expect local training data beneath:

```text
training/data/
```

Generated training artifacts are written beneath:

```text
training/outputs/
```

and are excluded from Git.

The final deployment checkpoints required to run the application are committed separately under:

```text
models/
```

Therefore **training data is not required to run the submitted application**.

---

## Scaling

The current component is intentionally interactive, but the same extraction logic can be scaled to city-wide processing.

A production-scale implementation would use:

- bulk building-geometry retrieval;
- cached orthophoto tiles;
- parallel crop/mask generation;
- batched GPU inference;
- asynchronous job processing;
- persistent building-level records;
- object storage for imagery and overlays;
- model and source-data versioning;
- retries and monitoring for external services.

Many building records could be precomputed and refreshed only when imagery, source data or model versions change.

See [`DESIGN.md`](DESIGN.md) for the detailed scaling rationale.

---

## Scope and future work

The proof of concept prioritizes a transparent end-to-end workflow and explicit provenance.

Natural extensions include:

- dedicated roof segmentation;
- roof-plane reconstruction from LiDAR or detailed 3D data;
- plane-level orientation;
- larger and more balanced labelled datasets;
- probability calibration;
- persistent city-wide storage;
- batch GPU inference;
- automated model/data version tracking.

---

## Reproducibility

The repository contains everything required to run the submitted application:

- application source code;
- Docker configuration;
- dependency specifications;
- trained deployment checkpoints;
- training notebooks;
- tests;
- fixed example JSON outputs;
- compact summary and example-building index files;
- paired masked model-input images and roof-plan overlays for five examples;
- design and reasoning documentation.

A fresh clone has been successfully built and run using:

```bash
docker compose up --build
```

No machine-specific paths or manually copied local files are required for the default application.

---

## Development tools and AI assistance

The project was implemented in Python using Flask, GeoPandas, Rasterio, Shapely, PyTorch, Torchvision, Folium and related geospatial tooling. **Roboflow** was used for manual training-data annotation and dataset organisation.

OpenAI ChatGPT was used during development for code review, debugging support, implementation discussion and documentation refinement. Data-source selection, modelling choices, validation decisions, integration of the final pipeline and final verification were reviewed as part of the submission.

---

## Repository

https://github.com/marcobadici/vienna-roof-explorer
