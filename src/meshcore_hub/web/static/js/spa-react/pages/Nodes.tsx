import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { useAppConfig } from "@/context/AppConfigContext";
import { apiGet } from "@/utils/api";
import { useFormatDateTime, formatNumber } from "@/utils/format";
import { copyToClipboard } from "@/utils/clipboard";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { Pagination } from "@/components/Pagination";
import { FilterForm, FilterToggle } from "@/components/FilterForm";
import {
  SortableTableHeader,
  MobileSortSelect,
} from "@/components/SortableTable";
import { NodeDisplay } from "@/components/NodeDisplay";
import { Loading, WarningBadge } from "@/components/Alerts";
import { IconRefresh } from "@/components/icons";

interface NodeTag {
  key: string;
  value: string | null;
}

interface NodeItem {
  public_key: string;
  name: string | null;
  adv_type: string | null;
  last_seen: string | null;
  tags: NodeTag[];
}

interface NodeListResponse {
  items: NodeItem[];
  total: number;
  limit: number;
  offset: number;
}

interface Profile {
  id: string;
  name: string | null;
  callsign: string | null;
  roles: string[];
  user_id?: string;
}

interface ProfileListResponse {
  items: Profile[];
  total: number;
}

function tagValue(tags: NodeTag[] | undefined, key: string): string | null {
  return tags?.find((tag) => tag.key === key)?.value ?? null;
}

export function Nodes() {
  const { t } = useTranslation();
  const config = useAppConfig();
  const [searchParams] = useSearchParams();
  const { formatDateTime, formatDateTimeShort } = useFormatDateTime();
  usePageTitle("entities.nodes");

  const search = searchParams.get("search") || "";
  const advType = searchParams.get("adv_type") || "";
  const adoptedBy = searchParams.get("adopted_by") || "";
  const pubkeyPrefix = searchParams.get("pubkey_prefix") || "";
  const page = parseInt(searchParams.get("page") || "", 10) || 1;
  const limit = parseInt(searchParams.get("limit") || "", 10) || 20;
  const offset = (page - 1) * limit;
  const sort = searchParams.get("sort") || "last_seen";
  const order = searchParams.get("order") || "desc";

  const tz = config.timezone || "";
  const hasActiveFilters =
    search !== "" ||
    advType !== "" ||
    pubkeyPrefix !== "" ||
    (config.oidc_enabled && adoptedBy !== "");

  const [filterOpen, setFilterOpen] = useState(hasActiveFilters);
  const [nodes, setNodes] = useState<NodeItem[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const oidcEnabled = config.oidc_enabled;
  const operatorRole = config.role_names?.operator || "operator";

  const fetchData = useCallback(async () => {
    try {
      const apiParams: Record<string, unknown> = {
        limit,
        offset,
        search,
        adv_type: advType,
        sort,
        order,
      };
      if (adoptedBy) apiParams.adopted_by = adoptedBy;
      if (pubkeyPrefix) apiParams.pubkey_prefix = pubkeyPrefix;

      const fetches: Promise<unknown>[] = [
        apiGet<NodeListResponse>("/api/v1/nodes", apiParams),
      ];
      if (oidcEnabled) {
        fetches.push(
          apiGet<ProfileListResponse>("/api/v1/user/profiles", { limit: 500 }),
        );
      }
      const results = await Promise.all(fetches);
      const data = results[0] as NodeListResponse;
      const profs = oidcEnabled
        ? ((results[1] as ProfileListResponse)?.items || []).filter(
            (p) => p.roles && p.roles.includes(operatorRole),
          )
        : [];

      setNodes(data.items || []);
      setTotal(data.total || 0);
      setProfiles(profs);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [
    limit,
    offset,
    search,
    advType,
    sort,
    order,
    adoptedBy,
    pubkeyPrefix,
    oidcEnabled,
    operatorRole,
  ]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const { paused, toggle, intervalSeconds } = useAutoRefresh({
    onRefresh: fetchData,
  });

  const sortedProfiles = useMemo(
    () =>
      [...profiles].sort((a, b) => {
        const na = a.name || a.callsign || "";
        const nb = b.name || b.callsign || "";
        return na.localeCompare(nb);
      }),
    [profiles],
  );

  const totalPages = total !== null ? Math.ceil(total / limit) : 0;
  const headerParams: Record<string, string> = {
    search,
    adv_type: advType,
    adopted_by: adoptedBy,
    pubkey_prefix: pubkeyPrefix,
    limit: String(limit),
  };

  const autoSubmit = (e: React.ChangeEvent<HTMLSelectElement>) => {
    e.currentTarget.form?.requestSubmit();
  };

  const noEntity = t("common.no_entity_found", {
    entity: t("entities.nodes").toLowerCase(),
  });

  const mobileCards =
    nodes.length === 0 ? (
      <div className="text-center py-8 opacity-70">{noEntity}</div>
    ) : (
      nodes.map((node) => {
        const displayName = tagValue(node.tags, "name") || node.name;
        const tagDescription = tagValue(node.tags, "description");
        const lastSeen = node.last_seen
          ? formatDateTimeShort(node.last_seen)
          : "-";
        return (
          <Link
            key={node.public_key}
            to={`/nodes/${node.public_key}`}
            className="card bg-base-100 shadow-sm block"
          >
            <div className="card-body p-3">
              <div className="flex items-center justify-between gap-2">
                <NodeDisplay
                  name={displayName}
                  description={tagDescription}
                  publicKey={node.public_key}
                  advType={node.adv_type}
                  size="sm"
                />
                <div className="text-right flex-shrink-0">
                  <div className="text-xs opacity-60">{lastSeen}</div>
                </div>
              </div>
            </div>
          </Link>
        );
      })
    );

  const tableRows =
    nodes.length === 0 ? (
      <tr>
        <td colSpan={3} className="text-center py-8 opacity-70">
          {noEntity}
        </td>
      </tr>
    ) : (
      nodes.map((node) => {
        const displayName = tagValue(node.tags, "name") || node.name;
        const tagDescription = tagValue(node.tags, "description");
        const lastSeen = node.last_seen ? formatDateTime(node.last_seen) : "-";
        return (
          <tr key={node.public_key} className="hover">
            <td>
              <Link
                to={`/nodes/${node.public_key}`}
                className="link link-hover"
              >
                <NodeDisplay
                  name={displayName}
                  description={tagDescription}
                  publicKey={node.public_key}
                  advType={node.adv_type}
                  size="base"
                />
              </Link>
            </td>
            <td>
              <code
                className="font-mono text-xs cursor-pointer hover:bg-base-200 px-1 py-0.5 rounded select-all"
                onClick={(e) => copyToClipboard(e, node.public_key)}
                title="Click to copy"
              >
                {node.public_key}
              </code>
            </td>
            <td className="text-sm whitespace-nowrap">{lastSeen}</td>
          </tr>
        );
      })
    );

  if (loading) return <Loading />;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">{t("entities.nodes")}</h1>
        {tz && tz !== "UTC" && (
          <span className="text-sm opacity-60">{tz}</span>
        )}
      </div>

      <div className="flex items-center gap-2 mb-4">
        {total !== null && (
          <span className="badge badge-lg">
            {t("common.total", { count: formatNumber(total) })}
          </span>
        )}
        {error && <WarningBadge message={error} />}
        <div className="ml-auto flex items-center gap-3">
          {intervalSeconds > 0 && (
            <label
              className="label cursor-pointer gap-2"
              title={
                paused ? t("auto_refresh.resume") : t("auto_refresh.pause")
              }
            >
              <span className="text-sm opacity-80 flex items-center gap-1">
                <IconRefresh className="w-4 h-4" />
                <span className="text-xs">{intervalSeconds}s</span>
              </span>
              <input
                type="checkbox"
                className="toggle toggle-sm toggle-primary"
                checked={!paused}
                onChange={toggle}
              />
            </label>
          )}
        </div>
        <div className="ml-4">
          <FilterToggle
            open={filterOpen}
            onChange={() => setFilterOpen((open) => !open)}
          />
        </div>
      </div>

      {filterOpen && (
        <div className="mb-4">
          <FilterForm
            key={`filters-${search}-${advType}-${adoptedBy}-${pubkeyPrefix}`}
            basePath="/nodes"
          >
            <div className="flex flex-col gap-1">
              <label className="flex items-center py-1">
                <span className="opacity-80 text-sm">{t("common.search")}</span>
              </label>
              <input
                type="text"
                name="search"
                defaultValue={search}
                placeholder={t("common.search_placeholder")}
                className="input input-sm w-80"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="flex items-center py-1">
                <span className="opacity-80 text-sm">{t("common.type")}</span>
              </label>
              <select
                name="adv_type"
                className="select select-sm"
                defaultValue={advType}
                onChange={autoSubmit}
              >
                <option value="">{t("common.all_types")}</option>
                <option value="chat">{t("node_types.chat")}</option>
                <option value="repeater">{t("node_types.repeater")}</option>
                <option value="companion">{t("node_types.companion")}</option>
                <option value="room">{t("node_types.room")}</option>
              </select>
            </div>
            {oidcEnabled && sortedProfiles.length > 0 && (
              <div className="flex flex-col gap-1 max-w-56">
                <label className="flex items-center py-1">
                  <span className="opacity-80 text-sm">
                    {t("common.filter_operator_label")}
                  </span>
                </label>
                <select
                  name="adopted_by"
                  className="select select-sm"
                  defaultValue={adoptedBy}
                  onChange={autoSubmit}
                >
                  <option value="">{t("common.all_operators")}</option>
                  {sortedProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.callsign
                        ? `${p.name} (${p.callsign})`
                        : p.name || p.callsign || p.user_id || p.id}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </FilterForm>
        </div>
      )}

      <MobileSortSelect
        currentSort={sort}
        currentOrder={order}
        basePath="/nodes"
        params={headerParams}
        options={[
          { value: "last_seen:desc", label: t("nodes.sort.last_seen_newest") },
          { value: "last_seen:asc", label: t("nodes.sort.last_seen_oldest") },
          { value: "name:asc", label: t("nodes.sort.name_az") },
          { value: "name:desc", label: t("nodes.sort.name_za") },
          { value: "public_key:asc", label: t("nodes.sort.key_asc") },
          { value: "public_key:desc", label: t("nodes.sort.key_desc") },
        ]}
      />

      <div className="lg:hidden space-y-3">{mobileCards}</div>

      <div className="hidden lg:block overflow-x-auto bg-base-100 rounded-box shadow-sm">
        <table className="table table-zebra">
          <thead>
            <tr>
              <SortableTableHeader
                label={t("entities.node")}
                sortKey="name"
                currentSort={sort}
                currentOrder={order}
                basePath="/nodes"
                params={headerParams}
              />
              <SortableTableHeader
                label={t("common.public_key")}
                sortKey="public_key"
                currentSort={sort}
                currentOrder={order}
                basePath="/nodes"
                params={headerParams}
              />
              <SortableTableHeader
                label={t("common.last_seen")}
                sortKey="last_seen"
                currentSort={sort}
                currentOrder={order}
                basePath="/nodes"
                params={headerParams}
              />
            </tr>
          </thead>
          <tbody>{tableRows}</tbody>
        </table>
      </div>

      <Pagination
        page={page}
        totalPages={totalPages}
        basePath="/nodes"
        params={{
          search,
          adv_type: advType,
          adopted_by: adoptedBy,
          pubkey_prefix: pubkeyPrefix,
          limit: String(limit),
          sort,
          order,
        }}
      />
    </div>
  );
}
