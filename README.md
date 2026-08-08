# Vienna Roof Explorer

Interactive proof-of-concept for extracting building and rooftop attributes from
open geospatial data and aerial imagery in Vienna.

The application combines official City of Vienna building data with computer
vision models trained on rooftop imagery. A user can select a building directly
from an interactive map and inspect both official building information and
automatically derived rooftop attributes.

The project was developed as an AI/ML engineering take-home assessment focused
on rooftop detection and attribute extraction from open-source data.

---

## Overview

For a selected Vienna building, the application combines:

- official building geometry and attributes from City of Vienna open data;
- Vienna orthophoto imagery;
- a multi-label ResNet18 rooftop-feature classifier;
- a ResNet18 roof-material classifier;
- derived roof geometry attributes such as slope, roof type, and estimated
  surface area;
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

- building ID;
- address;
- building footprint;
- construction-related information;
- zoning / building metadata;
- photovoltaic potential;
- other available Vienna open-data attributes.

### Roof geometry

Derived from the official building footprint and available geometric
information:

- roof outline proxy;
- projected roof area;
- estimated roof surface area;
- mean roof slope;
- derived roof type.

### Roof material

The material classifier predicts one of:

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

---

## Confidence and provenance

Different attributes have different notions of certainty. The application keeps
these semantics separate rather than treating every value as a model
confidence.

- **Official data** retains its source provenance and is not assigned an
  artificial ML probability.
- **Geometrically derived attributes** use engineering confidence values where
  appropriate.
- **ML predictions** expose the raw neural-network probability.
- ML probabilities are **not calibrated probabilities** and should not be
  interpreted as formal statistical confidence.

This distinction is also preserved in the generated JSON records.

---

## Important geometry assumption

The roof outline currently uses the official City of Vienna building footprint
as a **plan-view approximation of the roof boundary**.

It is therefore not an image-segmentation result.

The same official footprint is used to crop/mask the orthophoto used by the ML
models. Consequently, the resulting roof geometry should be interpreted as an
official-geometry proxy rather than an independently detected roof polygon.

This approximation works well for a proof of concept but can differ from the
visible roof boundary because of:

- roof overhang;
- orthophoto parallax;
- complex roof structures;
- neighbouring structures;
- differences between cadastral/building geometry and the visible roof.

A production system could replace this component with dedicated roof
segmentation or higher-detail 3D building data.

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
│   ├── roof_inference.py
│   ├── routes.py
│   └── static/
│       └── map/
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
│   ├── buildings/
│   ├── overlays/
│   ├── roof_attributes.json
│   └── roof_attributes_summary.csv
│
├── tests/
│   ├── conftest.py
│   ├── test_official_data.py
│   └── test_routes.py
│
├── training/
│   ├── data/                 # local training data, excluded from Git
│   └── notebooks/
│       ├── roof_material_classification.ipynb
│       └── roof_multilabel_classification.ipynb
│
├── .dockerignore
├── .env.example
├── .gitignore
├── build_map.py
├── compose.yaml
├── Dockerfile
├── pytest.ini
├── requirements-dev.txt
├── requirements.txt
├── run.py
└── README.md
