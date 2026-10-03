// Alpine component wrapping a Leaflet map. Data comes from <script type="application/json" id="trip-map-data">.
// Glyphs and labels mirror the legend in trip_detail.html (docs/design-system.md section 1.4).
const MARKERS = {
  harsh_brake: { glyph: "Br", label: "Harsh brake" },
  harsh_accel: { glyph: "Ac", label: "Harsh acceleration" },
  sharp_corner: { glyph: "Co", label: "Sharp corner" },
  speeding: { glyph: "Sp", label: "Speeding" },
  crash: { glyph: "!", label: "Crash" },
};
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function markerIcon(type) {
  const spec = MARKERS[type];
  const el = document.createElement("div");
  el.textContent = spec.glyph;
  const isCrash = type === "crash";
  el.style.cssText =
    "width:28px;height:28px;display:flex;align-items:center;justify-content:center;" +
    "color:#fff;font:700 11px/1 system-ui,sans-serif;border:2px solid #fff;box-sizing:border-box;" +
    `background:${window.DS_TOKENS.event[type]};border-radius:${isCrash ? "4px" : "50%"};`;
  return L.divIcon({ html: el, className: "", iconSize: [28, 28], iconAnchor: [14, 14] });
}

function addMarker(map, item, type) {
  const spec = MARKERS[type];
  const peak = item.peak_g == null ? "" : `, ${item.peak_g.toFixed(2)} g`;
  const title = `${spec.label}${peak}`;
  L.marker([item.lat, item.lon], { icon: markerIcon(type), title, alt: title, keyboard: true })
    .bindTooltip(title)
    .addTo(map);
}

document.addEventListener("alpine:init", () => {
  Alpine.data("tripMap", () => {
    // Kept outside Alpine's reactive data: Alpine proxies break Leaflet.
    let map = null;
    return {
      init() {
        const data = JSON.parse(document.getElementById("trip-map-data").textContent);
        const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
        map = L.map(this.$refs.map, {
          scrollWheelZoom: false,
          zoomAnimation: !reduce,
          fadeAnimation: !reduce,
          markerZoomAnimation: !reduce,
          inertia: !reduce,
        });
        L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTRIBUTION }).addTo(map);
        const points = [...data.route];
        if (data.route.length > 1) {
          L.polyline(data.route, { color: window.DS_TOKENS.primary, weight: 4, opacity: 0.9 }).addTo(map);
        }
        const items = [...data.events.map((e) => [e, e.type]), ...data.crashes.map((c) => [c, "crash"])];
        for (const [item, type] of items) {
          if (!(type in MARKERS)) continue;
          addMarker(map, item, type);
          points.push([item.lat, item.lon]);
        }
        if (points.length === 1) map.setView(points[0], 15, { animate: !reduce });
        else map.fitBounds(points, { padding: [24, 24], animate: !reduce });
      },
      destroy() {
        if (map) map.remove();
        map = null;
      },
    };
  });
});
