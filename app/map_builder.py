import folium
from branca.element import Element

from .config import Config


# ================================================================
# CONFIGURATION
#
# MAP_CENTER is aliased from the central Config - see app/config.py.
# Where to save the built map is build_map.py's concern, not this
# module's; this module only builds the folium.Map object and returns it.
# ================================================================

MAP_CENTER = Config.MAP_CENTER


# ================================================================
# BUILD MAP
# ================================================================


def build_map() -> folium.Map:
    vienna_map = folium.Map(
        location=MAP_CENTER,
        zoom_start=17,
        tiles=None,
    )

    # ------------------------------------------------------------
    # Vienna orthophoto
    # ------------------------------------------------------------

    folium.TileLayer(
        tiles=(
            "https://mapsneu.wien.gv.at/wmts/lb/farbe/"
            "google3857/{z}/{y}/{x}.jpeg"
        ),
        attr="Datenquelle: Stadt Wien – data.wien.gv.at",
        name="Vienna Orthophoto",
        max_zoom=20,
        overlay=False,
        control=True,
        show=True,
    ).add_to(vienna_map)

    # ------------------------------------------------------------
    # OpenStreetMap
    # ------------------------------------------------------------

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap",
        overlay=False,
        control=True,
        show=False,
    ).add_to(vienna_map)

    folium.LayerControl().add_to(vienna_map)

    map_name = vienna_map.get_name()

    # ============================================================
    # BUILDING INFORMATION DRAWER
    # ============================================================

    drawer_styles = """
    <style>
        .building-info-drawer {
            position: fixed;
            top: 0;
            right: 0;
            width: 700px;
            max-width: calc(100vw - 40px);
            height: 100vh;
            background: #ffffff;
            border-left: 1px solid #d9d9d9;
            box-shadow: -4px 0 18px rgba(0, 0, 0, 0.18);
            z-index: 2000;
            transform: translateX(102%);
            transition: transform 180ms ease;
            font-family: Arial, sans-serif;
            color: #222;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        .building-info-drawer.is-open {
            transform: translateX(0);
        }

        .building-info-drawer,
        .building-info-drawer * {
            box-sizing: border-box;
        }

        .bid-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 18px;
            border-bottom: 1px solid #e2e2e2;
            background: #fff;
            flex: 0 0 auto;
            min-width: 0;
        }

        .bid-topbar-title {
            font-size: 20px;
            font-weight: 700;
            line-height: 1.25;
            min-width: 0;
            overflow-wrap: anywhere;
        }

        .bid-close {
            appearance: none;
            border: 1px solid #d5d5d5;
            background: #fff;
            color: #333;
            width: 34px;
            height: 34px;
            border-radius: 6px;
            font-size: 22px;
            line-height: 28px;
            cursor: pointer;
            flex: 0 0 auto;
        }

        .bid-close:hover {
            background: #f3f3f3;
        }

        .bid-body {
            overflow-y: auto;
            overflow-x: hidden;
            overscroll-behavior: contain;
            padding: 18px;
            flex: 1 1 auto;
            background: #fafafa;
            width: 100%;
            min-width: 0;
        }

        .official-building-profile {
            width: 100%;
            max-width: 100%;
            min-width: 0;
            color: #222;
            overflow-x: hidden;
        }

        .obp-header {
            margin-bottom: 14px;
            min-width: 0;
        }

        .obp-title {
            font-size: 23px;
            font-weight: 700;
            margin-bottom: 4px;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-subtitle {
            font-size: 14px;
            color: #666;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-loading,
        .obp-error {
            margin: 10px 0 14px;
            padding: 10px 11px;
            border-radius: 6px;
            font-size: 14px;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-loading {
            background: #eef2f5;
            color: #555;
        }

        .obp-error {
            background: #fff1f1;
            color: #8a1f1f;
        }

        .obp-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 12px;
            width: 100%;
            min-width: 0;
        }

        .obp-section {
            width: 100%;
            min-width: 0;
            border: 1px solid #dedede;
            border-radius: 7px;
            overflow: hidden;
            background: #fff;
        }

        .obp-section-wide {
            grid-column: auto;
        }

        .obp-section-ai {
            border: 1px solid #d7cdf5;
        }

        .obp-section-ai .obp-section-head {
            background: #f4f0fd;
            border-bottom: 1px solid #e2d9fa;
        }

        .obp-ai-badge {
            display: inline-block;
            margin-left: 6px;
            padding: 1px 6px;
            border-radius: 8px;
            background: #7c4dff;
            color: #fff;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.03em;
            vertical-align: middle;
        }

        .obp-section-head {
            padding: 8px 10px;
            background: #f5f5f5;
            border-bottom: 1px solid #e4e4e4;
            min-width: 0;
        }

        .obp-section-title {
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-source {
            margin-top: 3px;
            font-size: 11px;
            color: #777;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-table {
            width: 100%;
            max-width: 100%;
            table-layout: fixed;
            border-collapse: collapse;
            font-size: 14px;
        }

        .obp-table tr + tr {
            border-top: 1px solid #f0f0f0;
        }

        .obp-table td {
            padding: 7px 10px;
            vertical-align: top;
            min-width: 0;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-label {
            width: 42%;
            color: #666;
        }

        .obp-value {
            width: 58%;
            text-align: right;
            font-weight: 600;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-na {
            color: #999;
            font-weight: 400;
        }

        .obp-sources {
            margin-top: 14px;
            padding-top: 10px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #666;
            max-width: 100%;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .obp-export {
            margin-top: 14px;
            padding-top: 12px;
            border-top: 1px solid #ddd;
        }

        .obp-json-button {
            width: 100%;
            border: 0;
            border-radius: 7px;
            padding: 11px 14px;
            background: #222;
            color: #fff;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
        }

        .obp-json-button:hover {
            background: #3b3b3b;
        }

        .obp-export-note {
            margin-top: 6px;
            color: #777;
            font-size: 11px;
            line-height: 1.35;
        }

        .obp-source-chip {
            display: inline-block;
            max-width: 100%;
            margin: 3px 4px 0 0;
            padding: 3px 6px;
            border: 1px solid #ddd;
            border-radius: 10px;
            background: #fff;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .building-info-drawer img {
            display: block;
            max-width: 100%;
            height: auto;
        }

        .building-info-drawer a,
        .building-info-drawer pre,
        .building-info-drawer code {
            max-width: 100%;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        @media (max-width: 800px) {
            .building-info-drawer {
                width: 96vw;
                max-width: 96vw;
            }

            .bid-body {
                padding: 12px;
            }

            .obp-table {
                font-size: 13px;
            }
        }
    </style>
    """

    drawer_markup = """
    <aside
        id="building-info-drawer"
        class="building-info-drawer"
        aria-hidden="true"
        aria-label="Official building information"
    >
        <div class="bid-topbar">
            <div class="bid-topbar-title">Official Building Data</div>
            <button
                id="building-info-close"
                class="bid-close"
                type="button"
                aria-label="Close building information"
            >×</button>
        </div>
        <div id="building-info-body" class="bid-body"></div>
    </aside>
    """

    vienna_map.get_root().html.add_child(Element(drawer_styles))
    vienna_map.get_root().html.add_child(Element(drawer_markup))

    # ============================================================
    # JAVASCRIPT
    # ============================================================

    dynamic_javascript = r"""
    <script>
    window.addEventListener("load", function () {
        const map = __MAP_NAME__;

        let selectedLayer = null;
        let requestNumber = 0;
        let reloadTimer = null;
        let currentRoofRecord = null;

        const buildingDrawer = document.getElementById(
            "building-info-drawer"
        );
        const buildingDrawerBody = document.getElementById(
            "building-info-body"
        );
        const buildingDrawerClose = document.getElementById(
            "building-info-close"
        );

        function setBuildingPanelContent(html) {
            if (buildingDrawerBody) {
                buildingDrawerBody.innerHTML = html;
                buildingDrawerBody.scrollTop = 0;
            }
        }

        function openBuildingPanel(html) {
            setBuildingPanelContent(html);

            if (buildingDrawer) {
                buildingDrawer.classList.add("is-open");
                buildingDrawer.setAttribute("aria-hidden", "false");
            }
        }

        function downloadRoofRecord(record) {
            if (!record) {
                return;
            }

            const jsonText = JSON.stringify(record, null, 2);
            const blob = new Blob(
                [jsonText],
                { type: "application/json;charset=utf-8" }
            );

            const objectUrl = URL.createObjectURL(blob);
            const link = document.createElement("a");

            const rawId =
                record.building_id
                || record.address_code
                || "building";

            const safeId = String(rawId).replace(
                /[^a-zA-Z0-9_-]+/g,
                "_"
            );

            link.href = objectUrl;
            link.download = `roof_attributes_${safeId}.json`;

            document.body.appendChild(link);
            link.click();
            link.remove();

            URL.revokeObjectURL(objectUrl);
        }

        if (buildingDrawerBody) {
            buildingDrawerBody.addEventListener(
                "click",
                function (event) {
                    const button = event.target.closest(
                        "#generate-json-button"
                    );

                    if (!button || !currentRoofRecord) {
                        return;
                    }

                    downloadRoofRecord(currentRoofRecord);
                }
            );
        }

        function closeBuildingPanel() {
            if (buildingDrawer) {
                buildingDrawer.classList.remove("is-open");
                buildingDrawer.setAttribute("aria-hidden", "true");
            }

            if (selectedLayer) {
                buildingLayer.resetStyle(selectedLayer);
                selectedLayer = null;
            }

            currentRoofRecord = null;
        }

        if (buildingDrawerClose) {
            buildingDrawerClose.addEventListener(
                "click",
                closeBuildingPanel
            );
        }

        // ========================================================
        // STATUS CONTROL
        // ========================================================

        const statusControl = L.control({
            position: "bottomleft"
        });

        statusControl.onAdd = function () {
            const container = L.DomUtil.create(
                "div",
                "building-load-status"
            );

            container.style.background = "white";
            container.style.padding = "6px 10px";
            container.style.borderRadius = "4px";
            container.style.boxShadow =
                "0 1px 5px rgba(0,0,0,0.35)";
            container.style.fontFamily = "Arial, sans-serif";
            container.style.fontSize = "13px";
            container.textContent = "Loading buildings...";

            return container;
        };

        statusControl.addTo(map);

        function setStatus(message) {
            const element = document.querySelector(
                ".building-load-status"
            );

            if (element) {
                element.textContent = message;
            }
        }

        // ========================================================
        // BUILDING STYLES
        // ========================================================

        function normalStyle() {
            return {
                color: "red",
                weight: 2,
                fillColor: "red",
                fillOpacity: 0.10
            };
        }

        function selectedStyle() {
            return {
                color: "#00ffff",
                weight: 4,
                fillColor: "#00ffff",
                fillOpacity: 0.30
            };
        }

        // ========================================================
        // VALUE / HTML HELPERS
        // ========================================================

        function escapeHtml(value) {
            if (value === null || value === undefined) {
                return "";
            }

            return String(value)
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        }

        // Vienna's own datasets sometimes return a German "no data" marker
        // instead of leaving the field empty - these should be treated as
        // unavailable too, not displayed as if they were real values.
        const NO_DATA_MARKERS = new Set([
            "keine angabe",
            "ohne angabe",
            "k.a.",
            "unbekannt"
        ]);

        function isAvailable(value) {
            if (
                value === null
                || value === undefined
                || value === ""
                || value === "Not available"
            ) {
                return false;
            }

            if (
                typeof value === "string"
                && NO_DATA_MARKERS.has(value.trim().toLowerCase())
            ) {
                return false;
            }

            return true;
        }

        function formatNumber(value, decimals, unit) {
            if (!isAvailable(value)) {
                return null;
            }

            const number = Number(value);

            if (Number.isNaN(number)) {
                return String(value);
            }

            return `${number.toFixed(decimals)}${unit ? " " + unit : ""}`;
        }

        function yesNo(value) {
            if (value === true) {
                return "Yes";
            }

            if (value === false) {
                return "No";
            }

            if (!isAvailable(value)) {
                return null;
            }

            return String(value);
        }

        function displayValue(value) {
            if (!isAvailable(value)) {
                return '<span class="obp-na">Not available</span>';
            }

            return escapeHtml(value);
        }

        function hasAnyValue(...values) {
            return values.some((value) => isAvailable(value));
        }

        function withEngineeringConfidence(value, confidenceScore, qualifier = "derived") {
            if (!isAvailable(value)) {
                return value;
            }

            // Direct official values are shown without an artificial percentage.
            // Scores below 1 are engineering/provenance confidence values used
            // for derived or approximate attributes; they are NOT ML probabilities.
            if (!isAvailable(confidenceScore) || confidenceScore >= 1) {
                return value;
            }

            const percent = Math.round(confidenceScore * 100);
            return `${value} (${qualifier}; ${percent}% confidence)`;
        }

        function dataRow(label, value) {
            if (!isAvailable(value)) {
                return "";
            }

            return `
                <tr>
                    <td class="obp-label">${escapeHtml(label)}</td>
                    <td class="obp-value">${displayValue(value)}</td>
                </tr>
            `;
        }

        function dataSection(title, source, rows, wide = false, variant = null) {
            const visibleRows = rows.filter(Boolean);

            if (visibleRows.length === 0) {
                return "";
            }

            const variantClass = variant ? ` obp-section-${variant}` : "";
            const badge = variant === "ai"
                ? '<span class="obp-ai-badge">AI</span>'
                : "";

            return `
                <section class="obp-section ${wide ? "obp-section-wide" : ""}${variantClass}">
                    <div class="obp-section-head">
                        <div class="obp-section-title">${escapeHtml(title)}${badge}</div>
                        <div class="obp-source">${escapeHtml(source)}</div>
                    </div>
                    <table class="obp-table">
                        ${visibleRows.join("")}
                    </table>
                </section>
            `;
        }

        function sourceSummary(sources) {
            if (!sources) {
                return "";
            }

            return Object.values(sources)
                .map((source) => {
                    const status = source.status || "unknown";
                    const name = source.source || "Official source";
                    return `
                        <span class="obp-source-chip">
                            ${escapeHtml(name)}: ${escapeHtml(status)}
                        </span>
                    `;
                })
                .join("");
        }

        // ========================================================
        // OFFICIAL-DATA POPUP
        // ========================================================

        function buildingPanelContent(
            properties,
            official,
            stateMessage,
            error,
            roofFeaturesAi,
            roofMaterialAi,
            roofRecord = null
        ) {
            const immediateAddressCode =
                properties.address_code
                || properties.official_building_id
                || null;

            const area = formatNumber(
                properties.footprint_area_m2,
                1,
                "m²"
            );

            if (!official) {
                return `
                    <div class="official-building-profile">
                        <div class="obp-header">
                            <div class="obp-title">Official Building Data</div>
                            <div class="obp-subtitle">
                                Vienna address code: ${displayValue(immediateAddressCode)}
                            </div>
                        </div>

                        ${error
                            ? `<div class="obp-error">${escapeHtml(error)}</div>`
                            : `<div class="obp-loading">${escapeHtml(stateMessage || "Loading official datasets...")}</div>`
                        }

                        ${dataSection(
                            "FMZK geometry",
                            "Stadt Wien – Baukörpermodell / FMZK",
                            [
                                dataRow("Address code", immediateAddressCode),
                                dataRow("Building type", properties.LAYER),
                                dataRow("Building parts", properties.part_count),
                                dataRow("Footprint", area),
                                dataRow(
                                    "Eave elevation (Wiener Null)",
                                    formatNumber(properties.eave_elevation_m, 2, "m")
                                ),
                                dataRow(
                                    "Terrain elevation (Wiener Null)",
                                    formatNumber(properties.terrain_elevation_m, 2, "m")
                                )
                            ],
                            true
                        )}
                    </div>
                `;
            }

            const profile = official.profile || {};
            const id = profile.identification || {};
            const geo = profile.geometry_elevation || {};
            const history = profile.history_typology || {};
            const roof = profile.roof_solar || {};
            const planning = profile.planning_status || {};
            const confidence = official.confidence || {};

            const title = id.address || "Official Building Data";
            const subtitleParts = [];

            if (id.postal_code) {
                subtitleParts.push(id.postal_code);
            }

            if (id.district) {
                subtitleParts.push(`District ${id.district}`);
            }

            const subtitle = subtitleParts.length
                ? subtitleParts.join(" · ")
                : `Vienna address code: ${id.address_code || immediateAddressCode || "Not available"}`;

            const allAddresses = Array.isArray(id.addresses)
                ? id.addresses
                : [];

            const identificationSection = dataSection(
                "Identification",
                "Stadt Wien – Adressen Standorte Wien",
                [
                    dataRow("Address", id.address),
                    allAddresses.length > 1
                        ? dataRow(
                            "All addresses",
                            allAddresses.join(", ")
                        )
                        : "",
                    dataRow("Street", id.street),
                    dataRow("Postal code", id.postal_code),
                    dataRow("District", id.district),
                    dataRow("Address code", id.address_code || immediateAddressCode),
                    dataRow("Building object ID", id.building_object_id),
                    dataRow("Building status", id.building_status),
                    dataRow("Building block", id.building_block)
                ]
            );

            const hasBevData = hasAnyValue(
                geo.bev_ground_elevation_m,
                geo.bev_mean_height_m,
                geo.bev_max_height_m,
                geo.agwr_object_number
            );

            const geometrySection = dataSection(
                "Geometry & elevation",
                "Stadt Wien – Baukörpermodell / FMZK"
                    + (hasBevData ? " + optional BEV DLM Bauwerke" : ""),
                [
                    dataRow("Building parts", geo.part_count || properties.part_count),
                    dataRow("FMZK polygon IDs", geo.polygon_ids),
                    dataRow(
                        "Footprint",
                        formatNumber(
                            geo.footprint_area_m2 || properties.footprint_area_m2,
                            1,
                            "m²"
                        )
                    ),
                    dataRow("Height class", geo.height_class),
                    dataRow(
                        "Eave elevation (Wiener Null)",
                        formatNumber(geo.eave_elevation_m, 2, "m")
                    ),
                    dataRow(
                        "Lower overbuild elevation (Wiener Null)",
                        formatNumber(geo.lower_overbuild_elevation_m, 2, "m")
                    ),
                    dataRow(
                        "Terrain elevation (Wiener Null)",
                        formatNumber(geo.terrain_elevation_m, 2, "m")
                    ),
                    dataRow(
                        "Lowest terrain edge (Wiener Null)",
                        formatNumber(geo.lowest_terrain_edge_m, 2, "m")
                    ),
                    dataRow(
                        "Approx. eave height",
                        formatNumber(geo.approx_eave_height_m, 2, "m")
                    ),
                    dataRow(
                        "BEV ground elevation",
                        formatNumber(geo.bev_ground_elevation_m, 2, "m")
                    ),
                    dataRow(
                        "BEV mean height",
                        formatNumber(geo.bev_mean_height_m, 2, "m")
                    ),
                    dataRow(
                        "BEV maximum height",
                        formatNumber(geo.bev_max_height_m, 2, "m")
                    ),
                    dataRow("AGWR object number", geo.agwr_object_number)
                ]
            );

            const historySection = dataSection(
                "History & typology",
                "Stadt Wien – Gebäudeinformation / Bauperioden / Bautypologien",
                [
                    dataRow("Construction year", history.construction_year),
                    dataRow("Construction period", history.construction_period_broad),
                    dataRow("Detailed period", history.construction_period_detail),
                    dataRow("Typology", history.typology),
                    dataRow("Typology code", history.typology_code),
                    dataRow("Architect", history.architect),
                    dataRow("Building / complex", history.complex_name)
                ]
            );

            // --------------------------------------------------------
            // DERIVED ROOF TYPE + AREA
            // --------------------------------------------------------

            const meanRoofSlope = isAvailable(roof.mean_roof_slope_deg)
                ? Number(roof.mean_roof_slope_deg)
                : null;

            const projectedRoofArea = isAvailable(geo.footprint_area_m2)
                ? Number(geo.footprint_area_m2)
                : (
                    isAvailable(properties.footprint_area_m2)
                        ? Number(properties.footprint_area_m2)
                        : null
                );

            let derivedRoofType = roof.roof_type || null;
            let roofTypeConfidence = 1.0;
            let roofTypeBasis = null;

            // If Vienna does not provide DACHTYP, derive a coarse type
            // from the official mean roof slope.
            if (!isAvailable(derivedRoofType) && meanRoofSlope !== null) {
                if (meanRoofSlope <= 5) {
                    derivedRoofType = "Flat";
                    roofTypeConfidence = 0.95;
                } else if (meanRoofSlope <= 15) {
                    derivedRoofType = "Low-slope";
                    roofTypeConfidence = 0.85;
                } else {
                    derivedRoofType = "Pitched";
                    roofTypeConfidence = 0.95;
                }

                roofTypeBasis =
                    `Derived from mean roof slope (${meanRoofSlope.toFixed(1)}°)`;
            } else if (isAvailable(derivedRoofType)) {
                roofTypeBasis = "Official roof type from Vienna PV dataset";
            }

            // The FMZK footprint is used as the planimetric/projected roof area.
            // This does not include roof overhangs.
            const projectedRoofAreaConfidence =
                projectedRoofArea !== null ? 0.95 : null;

            // Approximate true roof surface area by correcting the projected
            // area with the official mean slope. This is only an approximation
            // for multi-plane or complex roofs.
            let estimatedRoofSurfaceArea = null;
            let estimatedRoofSurfaceAreaConfidence = null;

            if (
                projectedRoofArea !== null
                && meanRoofSlope !== null
                && meanRoofSlope >= 0
                && meanRoofSlope < 85
            ) {
                const slopeRadians = meanRoofSlope * Math.PI / 180.0;
                estimatedRoofSurfaceArea =
                    projectedRoofArea / Math.cos(slopeRadians);

                estimatedRoofSurfaceAreaConfidence = 0.75;
            }

            const roofSection = dataSection(
                "Roof & solar potential",
                "Stadt Wien – Photovoltaik Potenzial 2022 + FMZK"
                    + " · derived values use engineering confidence",
                [
                    dataRow(
                        "Roof type",
                        withEngineeringConfidence(
                            derivedRoofType,
                            roofTypeConfidence,
                            "derived"
                        )
                    ),
                    dataRow(
                        "Roof type basis",
                        roofTypeBasis
                    ),
                    dataRow(
                        "Projected roof area",
                        withEngineeringConfidence(
                            formatNumber(
                                projectedRoofArea,
                                1,
                                "m²"
                            ),
                            projectedRoofAreaConfidence,
                            "FMZK proxy"
                        )
                    ),
                    dataRow(
                        "Estimated roof surface area",
                        withEngineeringConfidence(
                            formatNumber(
                                estimatedRoofSurfaceArea,
                                1,
                                "m²"
                            ),
                            estimatedRoofSurfaceAreaConfidence,
                            "derived"
                        )
                    ),
                    dataRow(
                        "Orientation",
                        withEngineeringConfidence(
                            roof.orientation,
                            confidence.orientation,
                            "derived"
                        )
                    ),
                    dataRow(
                        "Mean roof slope",
                        formatNumber(roof.mean_roof_slope_deg, 1, "°")
                    ),
                    dataRow(
                        "Annual solar yield",
                        formatNumber(roof.annual_yield_kwh_m2a, 0, "kWh/m²a")
                    ),
                    dataRow(
                        "PV area – medium",
                        formatNumber(roof.pv_area_medium_m2, 1, "m²")
                    ),
                    dataRow(
                        "PV area – good",
                        formatNumber(roof.pv_area_good_m2, 1, "m²")
                    ),
                    dataRow(
                        "PV area – very good",
                        formatNumber(roof.pv_area_very_good_m2, 1, "m²")
                    ),
                    dataRow(
                        "Theoretical PV capacity",
                        formatNumber(roof.theoretical_pv_capacity_kwp, 1, "kWp")
                    )
                ]
            );

            const planningSection = dataSection(
                "Planning & status",
                "Stadt Wien – Schutzzonen / Flächenwidmung / Gemeindebauten",
                [
                    dataRow("Protection zone", yesNo(planning.in_protection_zone)),
                    dataRow("Protection-zone name", planning.protection_zone_name),
                    dataRow(
                        "Monument protection (PV dataset)",
                        planning.monument_protection_2020
                    ),
                    dataRow("Zoning class", planning.zoning_class),
                    dataRow("Zoning", planning.zoning),
                    dataRow("Zoning detail", planning.zoning_detail),
                    dataRow("Temporary plan document", planning.temporary_plan_document),
                    dataRow("Temporary until", planning.temporary_until),
                    dataRow("Municipal housing", yesNo(planning.municipal_housing)),
                    dataRow("Municipal estate", planning.municipal_estate_name),
                    dataRow("Municipal dwellings", planning.municipal_dwellings)
                ],
                true
            );

            let roofFeaturesSection = "";

            if (roofFeaturesAi && roofFeaturesAi.status === "error") {
                roofFeaturesSection = `
                    <div class="obp-error">
                        Rooftop feature detection failed: ${escapeHtml(roofFeaturesAi.message || "unknown error")}
                    </div>
                `;
            } else if (
                roofFeaturesAi
                && roofFeaturesAi.status === "success"
                && roofFeaturesAi.predictions
            ) {
                const featureRows = Object.values(roofFeaturesAi.predictions)
                    .filter((prediction) => prediction.detected)
                    .map((prediction) => {
                        const percent = Math.round(
                            (prediction.probability || 0) * 100
                        );

                        return dataRow(prediction.label, `${percent}%`);
                    });

                const rows = featureRows.length
                    ? featureRows
                    : [dataRow("Result", "No rooftop features detected")];

                roofFeaturesSection = dataSection(
                    "Rooftop features",
                    "Fine-tuned ResNet18 classifier — percentages are model probabilities",
                    rows,
                    true,
                    "ai"
                );
            }

            let roofMaterialSection = "";

            if (roofMaterialAi && roofMaterialAi.status === "error") {
                roofMaterialSection = `
                    <div class="obp-error">
                        Roof material detection failed: ${escapeHtml(roofMaterialAi.message || "unknown error")}
                    </div>
                `;
            } else if (
                roofMaterialAi
                && roofMaterialAi.status === "success"
                && roofMaterialAi.material
            ) {
                const percent = Math.round(
                    (roofMaterialAi.confidence || 0) * 100
                );

                roofMaterialSection = dataSection(
                    "Roof material",
                    "Fine-tuned ResNet18 classifier — probability is not calibrated confidence",
                    [
                        dataRow(
                            "Predicted material",
                            roofMaterialAi.material
                        ),
                        dataRow(
                            "Model probability",
                            `${percent}%`
                        )
                    ],
                    true,
                    "ai"
                );
            }

            const jsonExportSection = roofRecord
                ? `
                    <div class="obp-export">
                        <button
                            id="generate-json-button"
                            class="obp-json-button"
                            type="button"
                        >
                            Generate JSON
                        </button>
                        <div class="obp-export-note">
                            Download the structured roof attributes for this building.
                        </div>
                    </div>
                `
                : "";

            return `
                <div class="official-building-profile">
                    <div class="obp-header">
                        <div class="obp-title">${escapeHtml(title)}</div>
                        <div class="obp-subtitle">${escapeHtml(subtitle)}</div>
                    </div>

                    <div class="obp-grid">
                        ${identificationSection}
                        ${geometrySection}
                        ${historySection}
                        ${roofSection}
                        ${roofFeaturesSection}
                        ${roofMaterialSection}
                        ${planningSection}
                    </div>

                    <div class="obp-sources">
                        <strong>Official source status:</strong><br>
                        ${sourceSummary(official.sources)}
                    </div>

                    ${jsonExportSection}
                </div>
            `;
        }

        // ========================================================
        // BUILDING LAYER
        // ========================================================

        const buildingLayer = L.geoJSON(null, {
            style: normalStyle,

            onEachFeature: function (feature, layer) {
                const properties = feature.properties;

                layer.bindTooltip(`
                    <strong>Address code:</strong>
                    ${escapeHtml(
                        properties.address_code
                        || properties.official_building_id
                        || "Not available"
                    )}
                    <br>
                    <strong>Footprint:</strong>
                    ${displayValue(
                        formatNumber(
                            properties.footprint_area_m2,
                            1,
                            "m²"
                        )
                    )}
                `);

                layer.on("mouseover", function () {
                    if (selectedLayer !== layer) {
                        layer.setStyle({
                            color: "yellow",
                            weight: 4,
                            fillColor: "yellow",
                            fillOpacity: 0.30
                        });
                    }
                });

                layer.on("mouseout", function () {
                    if (selectedLayer !== layer) {
                        buildingLayer.resetStyle(layer);
                    }
                });

                layer.on("click", async function () {
                    if (selectedLayer) {
                        buildingLayer.resetStyle(selectedLayer);
                    }

                    selectedLayer = layer;
                    layer.setStyle(selectedStyle());
                    currentRoofRecord = null;

                    openBuildingPanel(
                        buildingPanelContent(
                            properties,
                            null,
                            "Loading official datasets...",
                            null
                        )
                    );

                    try {
                        const response = await fetch(
                            "/select-building",
                            {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json"
                                },
                                body: JSON.stringify({
                                    building_key: properties.building_key,
                                    official_building_id: properties.official_building_id,
                                    address_code: properties.address_code,
                                    polygon_ids: properties.polygon_id,
                                    part_count: properties.part_count,
                                    building_type: properties.LAYER,
                                    footprint_area_m2: properties.footprint_area_m2,
                                    height_class: properties.height_class,
                                    feature_class: properties.feature_class,
                                    subclass: properties.subclass,
                                    reference_code: properties.reference_code,
                                    eave_elevation_m: properties.eave_elevation_m,
                                    lower_overbuild_elevation_m: properties.lower_overbuild_elevation_m,
                                    terrain_elevation_m: properties.terrain_elevation_m,
                                    lowest_terrain_edge_m: properties.lowest_terrain_edge_m,
                                    approx_eave_height_m: properties.approx_eave_height_m,
                                    geometry: feature.geometry
                                })
                            }
                        );

                        const result = await response.json();

                        if (!response.ok) {
                            throw new Error(
                                result.message
                                || "Official-data request failed."
                            );
                        }

                        currentRoofRecord =
                            result.roof_record || null;

                        setBuildingPanelContent(
                            buildingPanelContent(
                                properties,
                                result.official,
                                null,
                                null,
                                result.roof_features_ai,
                                result.roof_material_ai,
                                currentRoofRecord
                            )
                        );

                    } catch (error) {
                        currentRoofRecord = null;

                        setBuildingPanelContent(
                            buildingPanelContent(
                                properties,
                                null,
                                null,
                                `Official-data lookup failed: ${error.message}`
                            )
                        );
                    }
                });
            }
        }).addTo(map);

        // ========================================================
        // LOAD BUILDINGS VISIBLE ON SCREEN
        // ========================================================

        async function loadVisibleBuildings() {
            const zoom = map.getZoom();

            if (zoom < 15) {
                buildingLayer.clearLayers();
                selectedLayer = null;
                setStatus("Zoom in to load building polygons.");
                return;
            }

            const bounds = map.getBounds();
            const currentRequest = ++requestNumber;

            const parameters = new URLSearchParams({
                west: bounds.getWest(),
                south: bounds.getSouth(),
                east: bounds.getEast(),
                north: bounds.getNorth()
            });

            setStatus("Loading official Vienna buildings...");

            try {
                const response = await fetch(
                    `/api/buildings?${parameters.toString()}`
                );

                const data = await response.json();

                if (currentRequest !== requestNumber) {
                    return;
                }

                if (!response.ok) {
                    throw new Error(
                        data.message
                        || "Building request failed."
                    );
                }

                buildingLayer.clearLayers();
                selectedLayer = null;
                buildingLayer.addData(data);

                setStatus(
                    `${data.features.length} official buildings loaded`
                );

            } catch (error) {
                if (currentRequest !== requestNumber) {
                    return;
                }

                buildingLayer.clearLayers();

                setStatus(
                    `Could not load buildings: ${error.message}`
                );

                console.error(error);
            }
        }

        // ========================================================
        // RELOAD WHEN MAP MOVES
        // ========================================================

        function scheduleBuildingReload() {
            window.clearTimeout(reloadTimer);

            reloadTimer = window.setTimeout(
                loadVisibleBuildings,
                350
            );
        }

        map.on("moveend", scheduleBuildingReload);
        loadVisibleBuildings();
    });
    </script>
    """

    dynamic_javascript = dynamic_javascript.replace(
        "__MAP_NAME__",
        map_name,
    )

    vienna_map.get_root().html.add_child(
        Element(dynamic_javascript)
    )

    return vienna_map
