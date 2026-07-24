import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import {
  divIcon,
  latLngBounds,
  type DivIcon,
  type Map as LeafletMap,
} from "leaflet";
import "leaflet/dist/leaflet.css";

import { useAppConfig } from "@/context/AppConfigContext";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { formatNumber, formatRelativeTime, typeEmoji } from "@/utils/format";
import {
  getDistanceKm,
  getNodesWithinRadius,
  getAnchorPoint,
  normalizeType,
  type LatLng,
} from "@/utils/mapMath";
import { FilterToggle, OperatorSelect } from "@/components/FilterForm";
import { ErrorAlert, Loading } from "@/components/Alerts";
import { PageHeader } from "@/components/PageHeader";
import { IconMap } from "@/components/icons";

const MAX_BOUNDS_RADIUS_KM = 20;

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

function getBoundsPadding(): [number, number] {
  if (window.innerWidth < 480) return [50, 50];
  if (window.innerWidth < 768) return [75, 75];
  return [100, 100];
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

function createNodeIcon(node: MapNode, oidcEnabled: boolean): DivIcon {
  const displayName = node.name || "";
  const relativeTime = formatRelativeTime(node.last_seen);
  const timeDisplay = relativeTime ? " (" + relativeTime + ")" : "";

  const iconHtml =
    oidcEnabled && node.is_adopted
      ? '<div style="width: 12px; height: 12px; background: var(--color-marker-infra); border: 2px solid var(--color-marker-infra-border); border-radius: 50%; box-shadow: 0 0 4px rgba(59,130,246,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>'
      : '<div style="width: 12px; height: 12px; background: var(--color-marker-public); border: 2px solid var(--color-marker-public-border); border-radius: 50%; box-shadow: 0 0 4px rgba(34,197,94,0.6), 0 1px 2px rgba(0,0,0,0.5);"></div>';

  return divIcon({
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

function NodePopup({
  node,
  oidcEnabled,
}: {
  node: MapNode;
  oidcEnabled: boolean;
}) {
  const { t } = useTranslation();
  const typeDisplay = getTypeDisplay(node, t);
  const nodeTypeEmoji = typeEmoji(node.adv_type);
  const unknownLabel = t("node_types.unknown");
  const showInfra = oidcEnabled && typeof node.is_adopted !== "undefined";

  return (
    <div className="p-2">
      <h3 className="font-bold text-lg mb-2">
        {nodeTypeEmoji} {node.name || unknownLabel}
        {showInfra && (
          <span
            style={{
              display: "inline-block",
              width: "10px",
              height: "10px",
              background: node.is_adopted
                ? "var(--color-marker-infra)"
                : "var(--color-marker-public)",
              border: `2px solid ${
                node.is_adopted
                  ? "var(--color-marker-infra-border)"
                  : "var(--color-marker-public-border)"
              }`,
              borderRadius: "50%",
              verticalAlign: "middle",
            }}
            title={node.is_adopted ? t("map.infrastructure") : t("map.public")}
          />
        )}
      </h3>
      <div className="text-sm grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        <div className="opacity-70">{t("common.type")}</div>
        <div>{typeDisplay}</div>
        {node.role && (
          <>
            <div className="opacity-70">{t("map.role")}</div>
            <div>
              <span className="badge badge-xs badge-ghost">{node.role}</span>
            </div>
          </>
        )}
        {node.owner && (
          <>
            <div className="opacity-70">{t("map.owner")}</div>
            <div>
              {node.owner.callsign
                ? `${node.owner.name} (${node.owner.callsign})`
                : node.owner.name}
            </div>
          </>
        )}
        <div className="opacity-70">{t("common.key")}</div>
        <div>
          <code className="text-xs">{node.public_key.substring(0, 16)}...</code>
        </div>
        <div className="opacity-70">{t("common.location")}</div>
        <div>
          {node.lat.toFixed(4)}, {node.lon.toFixed(4)}
        </div>
        {node.last_seen && (
          <>
            <div className="opacity-70">{t("common.last_seen_label")}</div>
            <div>{node.last_seen.substring(0, 19).replace("T", " ")}</div>
          </>
        )}
      </div>
      <a
        href={`/nodes/${encodeURIComponent(node.public_key)}`}
        className="btn btn-outline btn-xs mt-3"
      >
        {t("common.view_details")}
      </a>
    </div>
  );
}

function fitInitialBounds(
  map: LeafletMap,
  data: MapData,
  oidcEnabled: boolean,
): void {
  const allNodes = data.nodes || [];
  const padding = getBoundsPadding();
  if (oidcEnabled) {
    const adoptedNodes = allNodes.filter((n) => n.is_adopted);
    if (adoptedNodes.length > 0) {
      map.fitBounds(
        latLngBounds(adoptedNodes.map((n) => [n.lat, n.lon])),
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
    latLngBounds(nodesToFit.map((n) => [n.lat, n.lon])),
    { padding },
  );
}

function MapController({
  mapData,
  filteredNodes,
  category,
  oidcEnabled,
}: {
  mapData: MapData;
  filteredNodes: MapNode[];
  category: string;
  oidcEnabled: boolean;
}) {
  const map = useMap();
  const initialFitRef = useRef(false);

  useEffect(() => {
    if (!mapData) return;
    if (!initialFitRef.current) {
      initialFitRef.current = true;
      fitInitialBounds(map, mapData, oidcEnabled);
      return;
    }
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
        latLngBounds(nodesToFit.map((n) => [n.lat, n.lon])),
        { padding: getBoundsPadding() },
      );
    } else {
      const center = mapData.center;
      if (center && (center.lat !== 0 || center.lon !== 0)) {
        map.setView([center.lat, center.lon], 10);
      }
    }
  }, [map, mapData, filteredNodes, category, oidcEnabled]);

  return null;
}

export function MapPage() {
  const { t } = useTranslation();
  const config = useAppConfig();
  usePageTitle("entities.map");

  const oidcEnabled = config.oidc_enabled;
  const operatorRole = config.role_names?.operator || "operator";

  const [filterOpen, setFilterOpen] = useState(false);
  const [category, setCategory] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [operatorFilter, setOperatorFilter] = useState("");
  const [showLabels, setShowLabels] = useState(false);

  const mapQuery = useQuery({
    queryKey: qk.map.data({ adopted_by: operatorFilter || undefined }),
    queryFn: ({ signal }) => {
      const params: Record<string, unknown> = {};
      if (operatorFilter) params.adopted_by = operatorFilter;
      return apiGet<MapData>("/map/data", params, { signal });
    },
  });
  const mapData = mapQuery.data ?? null;
  const loading = mapQuery.isLoading;
  const error = mapQuery.error
    ? mapQuery.error.message || t("common.failed_to_load_page")
    : null;

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

  const allNodes = useMemo(() => mapData?.nodes ?? [], [mapData]);

  const filteredNodes = useMemo(
    () =>
      allNodes.filter((node) => {
        if (category === "infra" && !node.is_adopted) return false;
        if (typeFilter && normalizeType(node.adv_type) !== typeFilter)
          return false;
        return true;
      }),
    [allNodes, category, typeFilter],
  );

  const markers = useMemo(
    () =>
      filteredNodes.map((node) => (
        <Marker
          key={node.public_key}
          position={[node.lat, node.lon]}
          icon={createNodeIcon(node, oidcEnabled)}
        >
          <Popup>
            <NodePopup node={node} oidcEnabled={oidcEnabled} />
          </Popup>
        </Marker>
      )),
    [filteredNodes, oidcEnabled],
  );

  const clearFilters = () => {
    setCategory("");
    setTypeFilter("");
    setOperatorFilter("");
    setShowLabels(false);
  };

  const debug = mapData?.debug ?? null;
  const nodeCount = allNodes.length;
  const filteredCount = filteredNodes.length;
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
  } else if (filteredCount === nodeCount) {
    countBadgeText = t("map.nodes_on_map", {
      count: formatNumber(nodeCount),
    });
  } else {
    countBadgeText = t("common.total", { count: formatNumber(nodeCount) });
  }
  const showFilteredBadge = filteredCount !== nodeCount;

  if (loading) return <Loading />;
  if (error) return <ErrorAlert message={error} />;

  return (
    <div>
      <PageHeader title={t("entities.map")} icon={IconMap}>
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
      </PageHeader>

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
              <OperatorSelect
                value={operatorFilter}
                onChange={(e) => setOperatorFilter(e.currentTarget.value)}
                profiles={operatorProfiles}
              />
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
            className={showLabels ? "show-labels" : undefined}
            style={{ height: "calc(100vh - 300px)", minHeight: "400px" }}
          >
            <MapContainer
              center={[0, 0]}
              zoom={2}
              style={{ height: "100%", width: "100%" }}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {markers}
              {mapData && (
                <MapController
                  mapData={mapData}
                  filteredNodes={filteredNodes}
                  category={category}
                  oidcEnabled={oidcEnabled}
                />
              )}
            </MapContainer>
          </div>
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
