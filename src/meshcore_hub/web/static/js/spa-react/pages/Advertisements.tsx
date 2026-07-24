import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useAppConfig } from "@/context/AppConfigContext";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { useFormatDateTime } from "@/utils/format";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { IconAdvertisements } from "@/components/icons";
import { Pagination } from "@/components/Pagination";
import {
  FilterForm,
  FilterField,
  FilterSelect,
  OperatorSelect,
  autoSubmit,
  submitOnEnter,
} from "@/components/FilterForm";
import { MobileSortSelect, SortableTableHeader } from "@/components/SortableTable";
import { NodeDisplay } from "@/components/NodeDisplay";
import { CopyableValue } from "@/components/CopyableValue";
import {
  ObserverFilterBadges,
  ObserverIcons,
  getDisabledObserverAreas,
  toggleObserverArea,
} from "@/components/ObserverBadges";
import { RouteTypeBadge } from "@/components/RouteTypeBadge";
import { Loading } from "@/components/Alerts";
import { ListToolbar } from "@/components/ListToolbar";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, EmptyRow } from "@/components/EmptyState";

interface ObserverInfo {
  node_id?: string;
  public_key: string;
  name?: string;
  tag_name?: string;
  snr?: number | null;
  observed_at?: string;
}

interface Advertisement {
  public_key: string;
  name?: string | null;
  node_name?: string | null;
  node_tag_name?: string | null;
  node_tag_description?: string | null;
  adv_type?: string | null;
  route_type?: string | null;
  received_at: string;
  packet_hash?: string | null;
  observed_by?: string | null;
  observers?: ObserverInfo[];
}

interface NodeItem {
  public_key: string;
  tags?: { key: string; value: string | null }[];
}

interface OperatorProfile {
  id: string;
  user_id: string;
  name?: string | null;
  callsign?: string | null;
  roles: string[];
}

interface ListResponse<T> {
  items?: T[];
  total?: number;
}

export function Advertisements() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const config = useAppConfig();
  const { formatDateTime, formatDateTimeShort } = useFormatDateTime();
  usePageTitle("entities.advertisements");

  const search = searchParams.get("search") ?? "";
  const adoptedBy = searchParams.get("adopted_by") ?? "";
  const routeType = searchParams.get("route_type") ?? "flood,transport_flood";
  const page = parseInt(searchParams.get("page") ?? "", 10) || 1;
  const limit = parseInt(searchParams.get("limit") ?? "", 10) || 20;
  const sort = searchParams.get("sort") ?? "time";
  const order = searchParams.get("order") ?? "desc";
  const offset = (page - 1) * limit;

  const features = config.features ?? {};
  const packetsEnabled = features.packets !== false;

  const [disabledAreas, setDisabledAreas] = useState<Set<string>>(() =>
    getDisabledObserverAreas(),
  );
  const [filterOpen, setFilterOpen] = useState(
    search !== "" ||
      (config.oidc_enabled && adoptedBy !== "") ||
      routeType !== "flood,transport_flood",
  );

  const { paused, toggle, intervalSeconds, refetchInterval } =
    useAutoRefresh();

  const { data, error: queryError } = useQuery({
    queryKey: qk.advertisements.list({
      limit,
      offset,
      search,
      sort,
      order,
      routeType,
      adoptedBy,
      oidcEnabled: config.oidc_enabled,
      operatorRole: config.role_names?.operator || "operator",
      disabledAreas: [...disabledAreas].sort(),
    }),
    refetchInterval,
    queryFn: async ({ signal }) => {
      const nodesPromise = apiGet<ListResponse<NodeItem>>(
        "/api/v1/nodes",
        { limit: 500, observer: true },
        { signal },
      );
      const profilesPromise = config.oidc_enabled
        ? apiGet<ListResponse<OperatorProfile>>(
            "/api/v1/user/profiles",
            { limit: 500 },
            { signal },
          )
        : Promise.resolve(null);
      const [nodesData, profilesData] = await Promise.all([
        nodesPromise,
        profilesPromise,
      ]);

      const operatorRole = config.role_names?.operator || "operator";
      const operators = (profilesData?.items ?? [])
        .filter((p) => p.roles?.includes(operatorRole))
        .sort((a, b) =>
          (a.name || a.callsign || "").localeCompare(
            b.name || b.callsign || "",
          ),
        );

      const areaMap = new Map<string, string[]>();
      for (const n of nodesData.items ?? []) {
        const area = n.tags?.find((tg) => tg.key === "area")?.value;
        if (!area || !area.trim()) continue;
        const key = area.trim();
        if (!areaMap.has(key)) areaMap.set(key, []);
        areaMap.get(key)!.push(n.public_key);
      }
      const sortedAreas = [...areaMap.keys()].sort((a, b) =>
        a.toLowerCase().localeCompare(b.toLowerCase()),
      );

      const observerFilterActive = sortedAreas.some((a) =>
        disabledAreas.has(a),
      );
      const apiParams: Record<string, unknown> = {
        limit,
        offset,
        search,
        sort,
        order,
        route_type: routeType,
      };
      if (observerFilterActive) {
        apiParams.observed_by = sortedAreas
          .filter((a) => !disabledAreas.has(a))
          .flatMap((a) => areaMap.get(a) ?? []);
      }
      if (adoptedBy) apiParams.adopted_by = adoptedBy;

      const adData = await apiGet<ListResponse<Advertisement>>(
        "/api/v1/advertisements",
        apiParams,
        { signal },
      );
      return {
        items: adData.items ?? [],
        total: adData.total ?? 0,
        operators,
        sortedAreas,
      };
    },
  });
  const error = queryError ? queryError.message : null;

  const items = data?.items ?? null;
  const total = data?.total ?? null;
  const operators = data?.operators ?? [];
  const sortedAreas = data?.sortedAreas ?? [];

  const handleObserverToggle = (area: string) => {
    const updated = toggleObserverArea(area, sortedAreas.length);
    setDisabledAreas(new Set(updated));
    if (page > 1) {
      const sp = new URLSearchParams(searchParams);
      sp.delete("page");
      const qs = sp.toString();
      navigate(qs ? `/advertisements?${qs}` : "/advertisements");
    }
  };

  const totalPages = total !== null ? Math.ceil(total / limit) : 0;
  const headerParams = {
    search,
    adopted_by: adoptedBy,
    route_type: routeType,
    limit: String(limit),
  };
  const paginationParams = { ...headerParams, sort, order };
  const emptyMessage = t("common.no_entity_found", {
    entity: t("entities.advertisements").toLowerCase(),
  });

  const renderReceivers = (ad: Advertisement, variant: "mobile" | "desktop") => {
    if (ad.observers && ad.observers.length >= 1) {
      return <ObserverIcons observers={ad.observers} />;
    }
    if (ad.observed_by) {
      return (
        <span className={`opacity-50 ${variant === "mobile" ? "text-xs" : ""}`}>
          {"\u{1F4E1}"}
        </span>
      );
    }
    return variant === "desktop" ? <span className="opacity-50">-</span> : null;
  };

  return (
    <>
      <PageHeader title={t("entities.advertisements")} icon={IconAdvertisements} />

      <ListToolbar
        total={total}
        error={error}
        autoRefresh={{ paused, onToggle: toggle, intervalSeconds }}
        filterToggle={{ open: filterOpen, onChange: () => setFilterOpen((o) => !o) }}
      />

      {filterOpen && (
        <div className="mb-4">
          <FilterForm basePath="/advertisements">
            <FilterField label={t("common.search")}>
              <input
                type="text"
                name="search"
                key={`search-${search}`}
                defaultValue={search}
                placeholder={t("common.search_placeholder")}
                className="input input-sm w-80"
                onKeyDown={submitOnEnter}
              />
            </FilterField>
            <FilterField
              label={t("advertisements.filter_route_type_label")}
              className="max-w-48"
            >
              <FilterSelect
                name="route_type"
                key={`route_type-${routeType}`}
                defaultValue={routeType}
                onChange={autoSubmit}
                options={[
                  {
                    value: "flood,transport_flood",
                    label: t("advertisements.route_type_flood"),
                  },
                  { value: "all", label: t("advertisements.route_type_all") },
                  {
                    value: "direct",
                    label: t("advertisements.route_type_direct"),
                  },
                ]}
              />
            </FilterField>
            {config.oidc_enabled && operators.length > 0 && (
              <FilterField
                label={t("common.filter_operator_label")}
                className="max-w-56"
              >
                <OperatorSelect
                  name="adopted_by"
                  key={`adopted_by-${adoptedBy}`}
                  defaultValue={adoptedBy}
                  onChange={autoSubmit}
                  profiles={operators}
                />
              </FilterField>
            )}
          </FilterForm>
        </div>
      )}

      {items === null ? (
        <Loading />
      ) : (
        <>
          <ObserverFilterBadges
            areas={sortedAreas}
            disabled={disabledAreas}
            onToggle={handleObserverToggle}
            extraClass="hidden lg:flex mb-4"
          />

          <MobileSortSelect
            currentSort={sort}
            currentOrder={order}
            basePath="/advertisements"
            params={headerParams}
            options={[
              { value: "time:desc", label: t("advertisements.sort.newest") },
              { value: "time:asc", label: t("advertisements.sort.oldest") },
              {
                value: "node_name:asc",
                label: t("advertisements.sort.node_az"),
              },
              {
                value: "node_name:desc",
                label: t("advertisements.sort.node_za"),
              },
              {
                value: "public_key:asc",
                label: t("advertisements.sort.key_asc"),
              },
              {
                value: "public_key:desc",
                label: t("advertisements.sort.key_desc"),
              },
            ]}
          />

          <ObserverFilterBadges
            areas={sortedAreas}
            disabled={disabledAreas}
            onToggle={handleObserverToggle}
            extraClass="flex lg:hidden mb-4"
          />

          <div className="lg:hidden space-y-3">
            {items.length === 0 ? (
              <EmptyState>{emptyMessage}</EmptyState>
            ) : (
              items.map((ad, idx) => {
                const adName =
                  ad.node_tag_name || ad.node_name || ad.name || null;
                const detailUrl =
                  packetsEnabled && ad.packet_hash
                    ? `/packets/hash/${ad.packet_hash}`
                    : null;
                return (
                  <div
                    key={`${ad.public_key}-${ad.received_at}-${idx}`}
                    className={`card bg-base-100 shadow-sm block ${detailUrl ? "cursor-pointer" : ""}`}
                    onClick={
                      detailUrl ? () => navigate(detailUrl) : undefined
                    }
                  >
                    <div className="card-body p-3">
                      <div className="flex items-center justify-between gap-2">
                        <Link
                          to={`/nodes/${ad.public_key}`}
                          className="min-w-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <NodeDisplay
                            name={adName}
                            description={ad.node_tag_description ?? null}
                            publicKey={ad.public_key}
                            advType={ad.adv_type ?? null}
                            size="sm"
                          />
                        </Link>
                        <div className="text-right flex-shrink-0">
                          <div className="text-xs opacity-60">
                            {formatDateTimeShort(ad.received_at)}
                          </div>
                          <div className="flex items-center justify-end gap-1">
                            <RouteTypeBadge
                              routeType={ad.route_type ?? null}
                            />
                            {renderReceivers(ad, "mobile")}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="hidden lg:block overflow-x-auto overflow-y-visible bg-base-100 rounded-box shadow-sm">
            <table className="table table-zebra">
              <thead>
                <tr>
                  <SortableTableHeader
                    label={t("entities.node")}
                    sortKey="node_name"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/advertisements"
                    params={headerParams}
                  />
                  <SortableTableHeader
                    label={t("common.public_key")}
                    sortKey="public_key"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/advertisements"
                    params={headerParams}
                  />
                  <th>{t("advertisements.col_route_type")}</th>
                  <SortableTableHeader
                    label={t("common.time")}
                    sortKey="time"
                    currentSort={sort}
                    currentOrder={order}
                    basePath="/advertisements"
                    params={headerParams}
                  />
                  <th>{t("common.observers")}</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <EmptyRow colSpan={5}>{emptyMessage}</EmptyRow>
                ) : (
                  items.map((ad, idx) => {
                    const adName =
                      ad.node_tag_name || ad.node_name || ad.name || null;
                    const detailUrl =
                      packetsEnabled && ad.packet_hash
                        ? `/packets/hash/${ad.packet_hash}`
                        : null;
                    return (
                      <tr
                        key={`${ad.public_key}-${ad.received_at}-${idx}`}
                        data-testid="list-row"
                        className={detailUrl ? "hover cursor-pointer" : ""}
                        onClick={
                          detailUrl ? () => navigate(detailUrl) : undefined
                        }
                      >
                        <td>
                          <Link
                            to={`/nodes/${ad.public_key}`}
                            className="link link-hover"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <NodeDisplay
                              name={adName}
                              description={ad.node_tag_description ?? null}
                              publicKey={ad.public_key}
                              advType={ad.adv_type ?? null}
                              size="base"
                            />
                          </Link>
                        </td>
                        <td>
                          <CopyableValue value={ad.public_key} />
                        </td>
                        <td>
                          <RouteTypeBadge routeType={ad.route_type ?? null} />
                        </td>
                        <td className="text-sm whitespace-nowrap">
                          {formatDateTime(ad.received_at)}
                        </td>
                        <td>{renderReceivers(ad, "desktop")}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            basePath="/advertisements"
            params={paginationParams}
          />
        </>
      )}
    </>
  );
}
