import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { useAppConfig } from "@/context/AppConfigContext";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiGet, isAbortError } from "@/utils/api";
import { formatNumber, formatRelativeTime, typeEmoji } from "@/utils/format";
import { FilterToggle } from "@/components/FilterForm";
import { ErrorAlert, Loading } from "@/components/Alerts";

const MAX_BOUNDS_RADIUS_KM = 20;

interface LatLng {
  lat: number;
  lon: number;
}

interface MapNodeOwner {
  name: string;
  callsign: string | null;
}

interface MapNode {
  public_key: string;
  name: string | null;
  adv_type: string | null;
  lat: number;
  lon: number;
  last_seen: string | null;
  is_adopted?: boolean;
  role: string | null;
  owner: MapNodeOwner | null;
}

interface Profile {
  id: string;
  name: string | null;
  callsign: string | null;
  roles: string[] | null;
}

interface MapDebug {
  total_nodes: number;
  nodes_with_coords: number;
  error: string | null;
}

interface MapData {
  nodes: MapNode[];
  center: LatLng | null;
  adopted_center: LatLng | null;
  debug: MapDebug | null;
  profiles: Profile[];
}

function escapeHtml(str: string | null | undefined): string {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function getDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function getNodesWithinRadius(
  nodes: MapNode[],
  anchorLat: number,
  anchorLon: number,
  radiusKm: number,
): MapNode[] {
  return nodes.filter(
    (n) => getDistanceKm(anchorLat, anchorLon, n.lat, n.lon) <= radiusKm,
  );
}

function getAnchorPoint(nodes: MapNode[], adoptedCenter: LatLng | null): LatLng {
  if (adoptedCenter) return adoptedCenter;
  if (nodes.length === 0) return { lat: 0, lon: 0 };
  return {
    lat: nodes.reduce((sum, n) => sum + n.lat, 0) / nodes.length,
    lon: nodes.reduce((sum, n) => sum + n.lon, 0) / nodes.length,
  };
}

function getBoundsPadding(): [number, number] {
  if (window.innerWidth < 480) return [50, 50];
  if (window.innerWidth < 768) return [75, 75];
  return [100, 100];
}

function normalizeType(type: string | null): string | null {
  return type ? type.toLowerCase() : null;
}

function getTypeDisplay(node: MapNode, t: TFunction): string {
  const type = normalizeType(node.adv_type);
  if (type === "chat") return t("node_types.chat");
  if (type === "repeater") return t("node_types.repeater");
  if (type === "room") return t("node_types.room");
  return type
    ? type.charAt(0).toUpperCase() + type.slice(1)
    : t("node_types.unknown");
}

function createNodeIcon(L: any, node: MapNode, oidcEnabled: boolean): any {
  const displayName = node.name || "";
  const relativeTime = formatRelativeTime(node.last_seen);
  const timeDisplay = relativeTime ? " (" + relativeTime + ")" : "";

  const iconHtml =
    oidcEnabled && node.is_adopted
      ? '<div style="width: 12px; height: 12px; background: var(--color-marker-infra); border: 2px solid var(--color-marker-infra-border); border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>'
      : '<div style="width: 12px; height: 12px; background: var(--color-marker-public); border: 2px solid var(--color-marker-public-border); border-radius: 50%; box-shadow: 0 0 4px rgba(34,197,94,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';

  return L.divIcon({
    className: "custom-div-icon",
    html:
      '<div class="map-marker" style="display: flex; flex-direction: column; align-items: center; gap: 2px;">' +
      iconHtml +
      '<span class="map-label" style="font-size: 10px; font-weight: bold; color: #fff; background: rgba(0,0,0,0.5); padding: 1px 4px; border-radius: 3px; white-space: nowrap; text-align: center;">' +
      escapeHtml(displayName) +
      escapeHtml(timeDisplay) +
      "</span>" +
      "</div>",
    iconSize: [120, 50],
    iconAnchor: [60, 12],
  });
}

function createPopupContent(
  node: MapNode,
  oidcEnabled: boolean,
  t: TFunction,
): string {
  const typeDisplay = getTypeDisplay(node, t);
  const nodeTypeEmoji = typeEmoji(node.adv_type);

  let infraIndicatorHtml = "";
  if (oidcEnabled && typeof node.is_adopted !== "undefined") {
    const dotColor = node.is_adopted
      ? "var(--color-marker-infra)"
      : "var(--color-marker-public)";
    const borderColor = node.is_adopted
      ? "var(--color-marker-infra-border)"
      : "var(--color-marker-public-border)";
    const title = node.is_adopted ? t("map.infrastructure") : t("map.public");
    infraIndicatorHtml =
      ' <span style="display: inline-block; width: 10px; height: 10px; background: ' +
      dotColor +
      "; border: 2px solid " +
      borderColor +
      '; border-radius: 50%; vertical-align: middle;" title="' +
      escapeHtml(title) +
      '"></span>';
  }

  const typeLabel = t("common.type");
  const keyLabel = t("common.key");
  const locationLabel = t("common.location");
  const lastSeenLabel = t("common.last_seen_label");
  const unknownLabel = t("node_types.unknown");
  const viewDetailsLabel = t("common.view_details");

  let rows = "";
  rows +=
    '<div class="opacity-70">' +
    typeLabel +
    "</div><div>" +
    escapeHtml(typeDisplay) +
    "</div>";

  if (node.role) {
    const roleLabel = t("map.role");
    rows +=
      '<div class="opacity-70">' +
      roleLabel +
      '</div><div><span class="badge badge-xs badge-ghost">' +
      escapeHtml(node.role) +
      "</span></div>";
  }

  if (node.owner) {
    const ownerLabel = t("map.owner");
    const ownerDisplay = node.owner.callsign
      ? escapeHtml(node.owner.name) +
        " (" +
        escapeHtml(node.owner.callsign) +
        ")"
      : escapeHtml(node.owner.name);
    rows +=
      '<div class="opacity-70">' + ownerLabel + "</div><div>" + ownerDisplay + "</div>";
  }

  rows +=
    '<div class="opacity-70">' +
    keyLabel +
    '</div><div><code class="text-xs">' +
    escapeHtml(node.public_key.substring(0, 16)) +
    "...</code></div>";
  rows +=
    '<div class="opacity-70">' +
    locationLabel +
    "</div><div>" +
    node.lat.toFixed(4) +
    ", " +
    node.lon.toFixed(4) +
    "</div>";

  if (node.last_seen) {
    rows +=
      '<div class="opacity-70">' +
      lastSeenLabel +
      "</div><div>" +
      node.last_seen.substring(0, 19).replace("T", " ") +
      "</div>";
  }

  return (
    '<div class="p-2">' +
    '<h3 class="font-bold text-lg mb-2">' +
    nodeTypeEmoji +
    " " +
    escapeHtml(node.name || unknownLabel) +
    infraIndicatorHtml +
    "</h3>" +
    '<div class="text-sm grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">' +
    rows +
    "</div>" +
    '<a href="/nodes/' +
    encodeURIComponent(node.public_key) +
    '" class="btn btn-outline btn-xs mt-3">' +
    viewDetailsLabel +
    "</a>" +
    "</div>"
  );
}

function fitInitialBounds(
  map: any,
  L: any,
  data: MapData,
  oidcEnabled: boolean,
): void {
  const allNodes = data.nodes || [];
  const padding = getBoundsPadding();
  if (oidcEnabled) {
    const adoptedNodes = allNodes.filter((n) => n.is_adopted);
    if (adoptedNodes.length > 0) {
      map.fitBounds(
        L.latLngBounds(adoptedNodes.map((n) => [n.lat, n.lon])),
        { padding },
      );
      return;
    }
  }
  if (allNodes.length === 0) return;
  const anchor = getAnchorPoint(
    allNodes,
    oidcEnabled ? data.adopted_center : null,
  );
  const nearbyNodes = getNodesWithinRadius(
    allNodes,
    anchor.lat,
    anchor.lon,
    MAX_BOUNDS_RADIUS_KM,
  );
  const nodesToFit = nearbyNodes.length > 0 ? nearbyNodes : allNodes;
  map.fitBounds(
    L.latLngBounds(nodesToFit.map((n) => [n.lat, n.lon])),
    { padding },
  );
}

export function MapPage() {
  const { t } = useTranslation();
  const config = useAppConfig();
  usePageTitle("entities.map");

  const oidcEnabled = config.oidc_enabled;
  const tz = config.timezone || "";
  const operatorRole = config.role_names?.operator || "operator";

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const initialFitRef = useRef(false);

  const [mapData, setMapData] = useState<MapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [operatorFilter, setOperatorFilter] = useState("");
  const [showLabels, setShowLabels] = useState(false);
  const [nodeCount, setNodeCount] = useState(0);
  const [filteredCount, setFilteredCount] = useState<number | null>(null);

  const operatorProfiles = useMemo(
    () =>
      (mapData?.profiles || [])
        .filter((p) => p.roles && p.roles.includes(operatorRole))
        .sort((a, b) => {
          const na = a.name || a.callsign || "";
          const nb = b.name || b.callsign || "";
          return na.localeCompare(nb);
        }),
    [mapData, operatorRole],
  );

  useEffect(() => {
    const ac = new AbortController();
    const params: Record<string, unknown> = {};
    if (operatorFilter) params.adopted_by = operatorFilter;
    apiGet<MapData>("/map/data", params, { signal: ac.signal })
      .then((data) => {
        setMapData(data);
        setError(null);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        setError((e as Error).message || t("common.failed_to_load_page"));
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, [operatorFilter, t]);

  useEffect(() => {
    if (loading || mapRef.current) return;
    const L = (window as any).L;
    const el = mapContainerRef.current;
    if (!L || !el) return;
    const map = L.map(el).setView([0, 0], 2);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    mapRef.current = map;
    return () => {
      mapRef.current = null;
      markersRef.current = [];
      map.remove();
    };
  }, [loading]);

  const updateMarkers = useCallback(
    (map: any, L: any, nodes: MapNode[]) => {
      markersRef.current.forEach((m) => map.removeLayer(m));
      markersRef.current = [];
      nodes.forEach((node) => {
        const marker = L.marker([node.lat, node.lon], {
          icon: createNodeIcon(L, node, oidcEnabled),
        }).addTo(map);
        marker.bindPopup(createPopupContent(node, oidcEnabled, t));
        markersRef.current.push(marker);
      });
    },
    [oidcEnabled, t],
  );

  const applyFilters = useCallback(() => {
    const map = mapRef.current;
    const L = (window as any).L;
    if (!map || !L || !mapData) return;
    const allNodes = mapData.nodes || [];
    const filteredNodes = allNodes.filter((node) => {
      if (category === "infra" && !node.is_adopted) return false;
      if (typeFilter && normalizeType(node.adv_type) !== typeFilter)
        return false;
      return true;
    });

    updateMarkers(map, L, filteredNodes);
    setNodeCount(allNodes.length);
    setFilteredCount(filteredNodes.length);

    if (filteredNodes.length > 0) {
      let nodesToFit = filteredNodes;
      if (category !== "infra") {
        const anchor = getAnchorPoint(filteredNodes, mapData.adopted_center);
        const nearbyNodes = getNodesWithinRadius(
          filteredNodes,
          anchor.lat,
          anchor.lon,
          MAX_BOUNDS_RADIUS_KM,
        );
        if (nearbyNodes.length > 0) nodesToFit = nearbyNodes;
      }
      map.fitBounds(
        L.latLngBounds(nodesToFit.map((n) => [n.lat, n.lon])),
        { padding: getBoundsPadding() },
      );
    } else {
      const center = mapData.center;
      if (center && (center.lat !== 0 || center.lon !== 0)) {
        map.setView([center.lat, center.lon], 10);
      }
    }
  }, [mapData, category, typeFilter, updateMarkers]);

  useEffect(() => {
    const map = mapRef.current;
    const L = (window as any).L;
    if (!map || !L || !mapData || mapData.debug?.error) return;
    if (!initialFitRef.current) {
      initialFitRef.current = true;
      fitInitialBounds(map, L, mapData, oidcEnabled);
      const allNodes = mapData.nodes || [];
      updateMarkers(map, L, allNodes);
      setNodeCount(allNodes.length);
      setFilteredCount(allNodes.length);
      return;
    }
    applyFilters();
  }, [mapData, oidcEnabled, applyFilters, updateMarkers]);

  useEffect(() => {
    const el = mapContainerRef.current;
    if (el) el.classList.toggle("show-labels", showLabels);
  }, [showLabels]);

  const clearFilters = () => {
    setCategory("");
    setTypeFilter("");
    setOperatorFilter("");
    setShowLabels(false);
  };

  const debug = mapData?.debug ?? null;
  let countBadgeText: string;
  if (debug?.error) {
    countBadgeText = "Error: " + debug.error;
  } else if (debug && debug.total_nodes === 0) {
    countBadgeText = t("common.no_entity_in_database", {
      entity: t("entities.nodes").toLowerCase(),
    });
  } else if (debug && debug.nodes_with_coords === 0) {
    countBadgeText = t("map.nodes_none_have_coordinates", {
      count: formatNumber(debug.total_nodes),
    });
  } else if (filteredCount === null || filteredCount === nodeCount) {
    countBadgeText = t("map.nodes_on_map", {
      count: formatNumber(nodeCount),
    });
  } else {
    countBadgeText = t("common.total", { count: formatNumber(nodeCount) });
  }
  const showFilteredBadge = filteredCount !== null && filteredCount !== nodeCount;

  if (loading) return <Loading />;
  if (error) return <ErrorAlert message={error} />;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">{t("entities.map")}</h1>
        <div className="flex items-center gap-2">
          {tz && tz !== "UTC" && (
            <span className="text-sm opacity-60">{tz}</span>
          )}
          <span className="badge badge-lg">{countBadgeText}</span>
          {showFilteredBadge && (
            <span className="badge badge-lg badge-ghost">
              {t("common.shown", { count: formatNumber(filteredCount) })}
            </span>
          )}
          <FilterToggle
            open={filterOpen}
            onChange={() => setFilterOpen((open) => !open)}
          />
        </div>
      </div>

      {filterOpen && (
        <div className="flex gap-4 flex-wrap items-end mb-6">
          <div className="fieldset">
            <label className="fieldset-label">{t("common.show")}</label>
            <select
              className="select select-sm"
              value={category}
              onChange={(e) => setCategory(e.currentTarget.value)}
            >
              <option value="">
                {t("common.all_entity", { entity: t("entities.nodes") })}
              </option>
              {oidcEnabled && (
                <option value="infra">{t("map.infrastructure_only")}</option>
              )}
            </select>
          </div>
          <div className="fieldset">
            <label className="fieldset-label">{t("common.node_type")}</label>
            <select
              className="select select-sm"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.currentTarget.value)}
            >
              <option value="">{t("common.all_types")}</option>
              <option value="chat">{t("node_types.chat")}</option>
              <option value="repeater">{t("node_types.repeater")}</option>
              <option value="room">{t("node_types.room")}</option>
            </select>
          </div>
          {oidcEnabled && operatorProfiles.length > 0 && (
            <div className="fieldset">
              <label className="fieldset-label">
                {t("common.filter_operator_label")}
              </label>
              <select
                className="select select-sm"
                value={operatorFilter}
                onChange={(e) => setOperatorFilter(e.currentTarget.value)}
              >
                <option value="">{t("common.all_operators")}</option>
                {operatorProfiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.callsign
                      ? `${p.name} (${p.callsign})`
                      : p.name || p.callsign || p.id}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="fieldset">
            <label className="fieldset-label cursor-pointer gap-2">
              <span>{t("map.show_labels")}</span>
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={showLabels}
                onChange={(e) => setShowLabels(e.currentTarget.checked)}
              />
            </label>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={clearFilters}>
            {t("common.clear_filters")}
          </button>
        </div>
      )}

      <div className="card bg-base-100 shadow-xl">
        <div className="card-body p-2">
          <div
            ref={mapContainerRef}
            style={{ height: "calc(100vh - 300px)", minHeight: "400px" }}
          />
        </div>
      </div>

      {oidcEnabled && (
        <div className="mt-4 flex flex-wrap gap-4 items-center text-sm">
          <span className="opacity-70">{t("map.legend")}</span>
          <div className="flex items-center gap-1">
            <div
              style={{
                width: "10px",
                height: "10px",
                background: "var(--color-marker-infra)",
                border: "2px solid var(--color-marker-infra-border)",
                borderRadius: "50%",
              }}
            />
            <span>{t("map.infrastructure")}</span>
          </div>
          <div className="flex items-center gap-1">
            <div
              style={{
                width: "10px",
                height: "10px",
                background: "var(--color-marker-public)",
                border: "2px solid var(--color-marker-public-border)",
                borderRadius: "50%",
              }}
            />
            <span>{t("map.public")}</span>
          </div>
        </div>
      )}

      <div className="mt-2 text-sm opacity-70">
        <p>{t("map.gps_description")}</p>
      </div>
    </div>
  );
}
