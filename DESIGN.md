````
# Design & Reasoning

## 1. Source selection and overall approach

The system uses **official City of Vienna building geometry as the spatial anchor** and combines it with official Vienna attribute datasets and high-resolution Vienna orthophoto imagery. The interactive map provides the building-selection interface, while the backend enriches the selected building with official data and runs the rooftop classifiers on a georeferenced orthophoto crop.

The primary geometry source is the City of Vienna **Baukörpermodell / FMZK**. FMZK was selected because it provides authoritative, georeferenced building geometry together with identifiers that can be reused when combining information from other municipal datasets. Where a building consists of several FMZK parts, the implementation groups those parts using the Vienna building reference and unions their geometries into a single building representation. The footprint area is calculated after transforming the geometry to the metric CRS **EPSG:32633 / UTM Zone 33N**.

The primary visual source is the **Stadt Wien orthophoto service**. A high-resolution top-down image is well suited to roof-level visual analysis because rooftop objects such as chimneys, skylights, HVAC installations and solar panels require substantially finer spatial detail than medium-resolution satellite imagery. According to the City of Vienna product information, the downloadable orthophoto is provided at **15 cm resolution**, covers the **entire Vienna city area**, and is produced as a **True Orthophoto**, so building roofs are represented in corrected planimetric position rather than being displaced by building lean. This is particularly useful when matching imagery to authoritative building polygons. The map and processing pipeline use the Vienna orthophoto directly, with OpenStreetMap available only as an alternative visual basemap and not as an attribute source.

Top-down imagery reduces many of the roof-visibility and alignment problems found in street-level imagery, although vegetation, shadows, roof overhangs and complex multi-plane geometry can still make individual visual attributes ambiguous. These limitations are handled by restricting the extracted attributes to those that can be supported by the selected sources and by keeping provenance and confidence semantics explicit.

Other possible sources were considered conceptually. **Sentinel-2** offers excellent coverage and temporal availability but is too coarse for reliable detection of small building-level rooftop elements. **Street-level imagery** can add useful façade information, but roof visibility is often incomplete and image-to-building alignment is more difficult. **Oblique imagery, LiDAR or detailed 3D city models** would be valuable for explicit roof-plane reconstruction, but were not necessary for the scope of this focused proof of concept.

The default workflow relies on publicly accessible City of Vienna geospatial services and does not require a paid commercial imagery API or API key. City of Vienna MA 41 Open Government Data is available free of charge under **CC BY 4.0**, subject to the required attribution `Datenquelle: Stadt Wien - data.wien.gv.at`.

Official source information:
- [Stadt Wien – Orthofoto product information](https://www.wien.gv.at/stadtplanung/orthofoto-produktinformation)
- [Stadt Wien – Orthofoto data and usage conditions](https://www.wien.gv.at/stadtentwicklung/stadtvermessung/geodaten/orthofoto/daten.html)

---

## 2. Official data fusion

The application does more than classify the orthophoto. After a building is selected, several City of Vienna datasets are queried and combined into a building-level profile.

The implemented official sources include:

| Source | Information used |
| --- | --- |
| Stadt Wien – Baukörpermodell / FMZK | building geometry, footprint, building parts, height/elevation-related fields |
| Stadt Wien – Adressen Standorte Wien | address, street, postal code, district, building/address identifiers and status |
| Stadt Wien – Straßenverzeichnis | resolution of numeric Vienna street codes to street names |
| Stadt Wien – Gebäudeinformation | construction year, architect and building/complex information |
| Stadt Wien – Bauperioden / Bautypologien | construction periods and building typology |
| Stadt Wien – Photovoltaik Potenzial 2022 | roof type, mean roof slope, annual solar yield, PV suitability areas and theoretical PV capacity |
| Stadt Wien – Schutzzonen | protection-zone information |
| Stadt Wien – Generalisierte Flächenwidmung | zoning and planning information |
| Stadt Wien / Wiener Wohnen – Gemeindebauten | municipal-housing information |
| BEV – DLM Bauwerke | optional local enrichment for elevation/height attributes |

These lookups are independent and are executed concurrently to reduce the waiting time after a building is selected. The returned source objects retain their individual match/error status so that provenance is preserved rather than flattening everything into values without origin.

The optional BEV GeoPackage is deliberately not required for the default repository. If it is absent, that source is returned as `not_configured` while the rest of the workflow continues normally.

---

## 3. Alignment and geolocation

The **building geometry and building identifiers are the primary alignment mechanism**. Address text is mainly used for presentation and supplementary matching rather than as the spatial anchor.

For official datasets, records are first matched through available Vienna identifiers where possible. If an identifier match is unavailable, the implementation uses spatial matching: polygon or line features are selected according to intersection with the selected building, while point-based data can be matched using distance in a metric CRS.

Address handling includes an additional step because a single building can legitimately have several entrance addresses. Nearby official address records are therefore collected and deduplicated, and Vienna street codes can be resolved through the official street-name register.

For the visual pipeline, the selected FMZK polygon is transformed to **EPSG:3857**, buffered by 1 metre and used to request the corresponding orthophoto area. The building polygon is subsequently transformed into the raster CRS and used to mask all pixels outside the selected building.

The processing chain is therefore:

```text
Selected FMZK building
        |
        +--------------------+
        |                    |
        v                    v
Official data          Orthophoto crop
lookups                      |
        |                    v
        |             Building mask
        |                    |
        |              Masked roof image
        |               /          \
        |              v            v
        |       Feature model   Material model
        |               \          /
        +-----------------\--------/
                           v
                 Unified roof record
```

The orthophoto crop and mask are generated only once and reused by both ML models. Official-data enrichment and rooftop AI inference are also run concurrently because the two branches are independent.

---

## 4. Information supported by the selected sources

The selected source combination is well suited to the main objectives of this proof of concept. It supports reliable building-level localization, plan-view roof geometry, official roof-slope and photovoltaic-potential attributes, broader building metadata, and visual classification of roof material and rooftop elements from RGB orthophoto imagery.

The approach is particularly strong for attributes that can be derived from top-down geometry or are directly visible in the orthophoto, including:

- building and roof-plan footprint;
- projected roof area;
- mean roof slope;
- coarse roof type;
- roof material;
- visible rooftop elements such as chimneys, skylights, HVAC units, vegetation and solar panels;
- official photovoltaic-potential indicators.

Some attributes naturally require additional data modalities when a higher level of geometric detail is needed. For example, reconstruction of individual roof planes, ridges, valleys or plane-specific orientation would benefit from LiDAR, oblique imagery or higher-detail 3D building models. Likewise, physical properties such as insulation performance are better addressed with thermal or other dedicated sensing modalities rather than RGB imagery alone.

For roof surface area, the current implementation combines the official projected footprint with the official mean roof slope. This provides a practical building-level surface-area estimate while keeping the derivation transparent. For complex roofs with several differently oriented planes, a future 3D reconstruction stage could further refine this value.

---

## 5. Roof detection and attribute extraction

The current implementation uses **geometry-assisted roof localization**.

The official FMZK building geometry is used as the plan-view approximation of the roof boundary. This geometry is also drawn over the orthophoto to make the selected roof extent visually inspectable and is used to create the masked image passed to the classifiers. The code explicitly distinguishes this approach from image-based semantic segmentation.

The resulting roof attributes are produced as follows:

| Attribute | Implementation |
| --- | --- |
| **Roof outline** | Official FMZK building geometry used as a plan-view roof approximation |
| **Projected roof area** | Area of the FMZK geometry calculated in EPSG:32633 |
| **Mean roof slope** | Direct matched value from Stadt Wien Photovoltaik Potenzial 2022 |
| **Roof type** | Official `DACHTYP` when available; otherwise derived from mean slope |
| **Estimated surface area** | Projected area corrected using mean slope |
| **Roof material** | Fine-tuned ResNet18 multiclass classifier |
| **Rooftop features** | Fine-tuned ResNet18 multilabel classifier |
| **Solar potential** | Official annual yield, suitability areas and theoretical PV capacity |

If an official roof type is available from the Vienna PV dataset, it is retained directly. Otherwise a transparent rule is used:

```text
mean slope <= 5°       -> Flat
5° < mean slope <=15°  -> Low-slope
mean slope > 15°       -> Pitched
```

The surface-area estimate is calculated as:

```text
estimated surface area
    =
projected footprint area / cos(mean roof slope)
```

for sensible slope values below 85°.

This is intentionally a building-level estimate based on the available official mean slope rather than an implicit claim that individual roof planes have been reconstructed.

**Roof orientation is not currently extracted.** No independent roof-plane orientation estimator is implemented in the backend, so it is preferable to leave this attribute absent rather than infer it without sufficient evidence.

---

## 6. Rooftop machine-learning models

Two separately trained **ResNet18** classifiers are used.

The labelled rooftop datasets were created manually using **Roboflow** as the annotation and dataset-management interface. Roboflow was used to create and organise the rooftop-feature and roof-material labels; the underlying roof imagery was derived from the Vienna orthophoto workflow used in this project. The labels were therefore manually assigned rather than generated automatically.

### Rooftop features

The rooftop-feature task is formulated as **multi-label classification**, because several elements can occur on the same roof simultaneously.

The model predicts:

- chimney;
- roof vegetation;
- rooftop HVAC;
- skylight;
- solar panels.

Each output receives its own sigmoid probability and is considered detected when it passes the threshold stored in the model checkpoint.

### Roof material

The material task is formulated as **single-label multiclass classification**. The model applies softmax across the available material classes and selects the class with the highest probability. The complete class distribution is retained internally as well.

Both models receive the same masked roof image. Their deployment preprocessing is reconstructed directly from checkpoint metadata and consists of:

```text
pad to square
→ resize to checkpoint image size
→ convert to tensor
→ ImageNet normalization
```

The checkpoints contain their architecture, class definitions and preprocessing values, reducing the risk of training/serving preprocessing mismatch. Models and transforms are cached in memory after the first request so that repeated building selections do not reload the weights from disk.

---

## 7. Output structure and provenance

The backend retains two complementary forms of output.

The broader `official.profile` drives the interactive side panel and contains:

```text
identification
geometry_elevation
history_typology
roof_solar
planning_status
```

The raw source results remain available separately, preserving their source name, status, data and errors.

For the assessment-focused export, the application builds a compact `roof_record` containing approximately:

```text
building_id
address_code
address

sources_used

roof
├── outline
├── outline_method
├── projected_area_m2
├── estimated_surface_area_m2
├── type
├── type_basis
├── mean_slope_deg
└── material

solar_potential
├── annual_yield_kwh_m2a
├── pv_area_medium_m2
├── pv_area_good_m2
├── pv_area_very_good_m2
└── theoretical_pv_capacity_kwp

rooftop_features

confidence

score_semantics
```

The application exposes this record through the **Generate JSON** action in the building panel, allowing the result for a selected building to be downloaded directly.

---

## 8. Confidence representation

Because the application combines official data, engineering estimates and ML predictions, a single generic definition of “confidence” would be misleading. The output therefore explicitly records the **kind and basis of a score**.

Three categories are used.

**Official source**

Direct values such as mean roof slope are identified as official-source values. The score describes the provenance of the attribute rather than pretending that the value is a neural-network probability.

**Engineering confidence**

Approximate or derived attributes use engineering-confidence values. In the current implementation:

- roof outline / projected-area proxy: **0.95**;
- estimated surface area: **0.75**;
- slope-derived roof type: **0.95** for flat or pitched and **0.85** for low-slope.

These engineering-confidence values are **heuristic reliability indicators for the proof of concept rather than empirically calibrated probabilities**. Their purpose is to communicate the expected reliability of a transparent geometric approximation, and the basis for each value is included with the result.

**Model probability**

Roof-material and rooftop-feature values retain the raw classifier probability. These are explicitly described as **model probabilities rather than calibrated statistical confidence estimates**.

This distinction is useful for downstream systems. For example, a low-probability ML prediction could be flagged for manual review, while an engineering estimate could be retained but propagated as an uncertain input into a later energy or carbon calculation.

---

## 9. Scaling from individual buildings to city-wide processing

The current application intentionally processes buildings interactively because that makes the complete workflow easy to inspect during the proof of concept.

Several implementation choices already reduce unnecessary work:

- model weights are cached in memory;
- one orthophoto/masked image is reused by both classifiers;
- official-data enrichment and AI inference run concurrently;
- independent official-data queries are executed concurrently;
- only buildings within the visible map extent are requested, and very large WFS requests are rejected.

Scaling the same approach to thousands of buildings would primarily require changing the execution architecture rather than redesigning the attribute extraction logic.

A city-scale workflow could use:

```text
bulk building geometry retrieval
        |
        v
cached orthophoto tiles
        |
        v
parallel crop/mask generation
        |
        v
batched GPU inference
        |
        v
official-data enrichment
        |
        v
persistent building database
```

The main production changes would include:

- bulk retrieval of building geometries instead of per-viewport WFS requests;
- caching orthophoto tiles because nearby buildings reuse the same source imagery;
- parallel image-preparation workers;
- batched GPU inference instead of one building at a time;
- a persistent database keyed by stable building ID;
- object storage for imagery and generated overlays;
- model and source-data versioning;
- retries and monitoring for external services;
- request- or job-specific temporary storage instead of the current shared runtime filenames.

For a city-wide deployment, most attributes could be precomputed. The interactive application would then primarily retrieve existing building records, with recomputation triggered only when the source imagery, official datasets or ML model versions change.

---

## 10. Scope and future extensions

The implementation prioritizes a transparent and reproducible end-to-end pipeline: a real building can be selected, aligned to authoritative geometry, enriched from multiple official sources, analysed visually by two trained models and exported as one structured building-level roof record.

The fixed buildings included under `outputs/` provide a reproducible set for comparison, but the application itself is **not restricted to those examples**. Buildings are retrieved dynamically from the Vienna FMZK service for the visible map area.

With additional development time, the most valuable extensions would be:

- dedicated roof segmentation for an image-derived visible roof polygon;
- roof-plane reconstruction using LiDAR or higher-detail 3D data;
- larger and more balanced training datasets;
- calibrated model probabilities;
- explicit plane-level orientation;
- batch/city-wide inference infrastructure;
- persistent model and data version tracking.

These extensions build naturally on the current component while retaining the same principle used throughout the proof of concept: **combine the source best suited to each attribute instead of forcing one data source or model to provide information it does not directly support.**
````
