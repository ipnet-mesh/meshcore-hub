import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";

import { useAppConfig } from "@/context/AppConfigContext";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { useFormatDateTime } from "@/utils/format";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { Pagination } from "@/components/Pagination";
import {
  FilterForm,
  FilterField,
  FilterSelect,
  OperatorSelect,
  autoSubmit,
} from "@/components/FilterForm";
import {
  SortableTableHeader,
  MobileSortSelect,
} from "@/components/SortableTable";
import { NodeDisplay, NodeLink } from "@/components/NodeDisplay";
import { CopyableValue } from "@/components/CopyableValue";
import { Loading } from "@/components/Alerts";
import { ListToolbar } from "@/components/ListToolbar";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, EmptyRow } from "@/components/EmptyState";

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

  const hasActiveFilters =
    search !== "" ||
    advType !== "" ||
    pubkeyPrefix !== "" ||
    (config.oidc_enabled && adoptedBy !== "");

  const [filterOpen, setFilterOpen] = useState(hasActiveFilters);

  const oidcEnabled = config.oidc_enabled;
  const operatorRole = config.role_names?.operator || "operator";

  const { paused, toggle, intervalSeconds, refetchInterval } =
    useAutoRefresh();

  const {
    data,
    isLoading: loading,
    error: queryError,
  } = useQuery({
    queryKey: qk.nodes.list({
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
    }),
    refetchInterval,
    queryFn: async ({ signal }) => {
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
        apiGet<NodeListResponse>("/api/v1/nodes", apiParams, { signal }),
      ];
      if (oidcEnabled) {
        fetches.push(
          apiGet<ProfileListResponse>(
            "/api/v1/user/profiles",
            { limit: 500 },
            { signal },
          ),
        );
      }
      const results = await Promise.all(fetches);
      const nodeData = results[0] as NodeListResponse;
      const profs = oidcEnabled
        ? ((results[1] as ProfileListResponse)?.items || []).filter(
            (p) => p.roles && p.roles.includes(operatorRole),
          )
        : [];

      return {
        nodes: nodeData.items || [],
        total: nodeData.total || 0,
        profiles: profs,
      };
    },
  });
  const error = queryError ? queryError.message : null;

  const nodes = data?.nodes ?? [];
  const total = data?.total ?? null;
  const profiles = data?.profiles ?? [];

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

  const noEntity = t("common.no_entity_found", {
    entity: t("entities.nodes").toLowerCase(),
  });

  const mobileCards =
    nodes.length === 0 ? (
      <EmptyState>{noEntity}</EmptyState>
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
      <EmptyRow colSpan={3}>{noEntity}</EmptyRow>
    ) : (
      nodes.map((node) => {
        const displayName = tagValue(node.tags, "name") || node.name;
        const tagDescription = tagValue(node.tags, "description");
        const lastSeen = node.last_seen ? formatDateTime(node.last_seen) : "-";
        return (
          <tr key={node.public_key} className="hover" data-testid="list-row">
            <td>
              <NodeLink
                name={displayName}
                description={tagDescription}
                publicKey={node.public_key}
                advType={node.adv_type}
                size="base"
              />
            </td>
            <td>
              <CopyableValue value={node.public_key} />
            </td>
            <td className="text-sm whitespace-nowrap">{lastSeen}</td>
          </tr>
        );
      })
    );

  if (loading) return <Loading />;

  return (
    <div>
      <PageHeader title={t("entities.nodes")} />

      <ListToolbar
        total={total}
        error={error}
        autoRefresh={{ paused, onToggle: toggle, intervalSeconds }}
        filterToggle={{
          open: filterOpen,
          onChange: () => setFilterOpen((open) => !open),
        }}
      />

      {filterOpen && (
        <div className="mb-4">
          <FilterForm
            key={`filters-${search}-${advType}-${adoptedBy}-${pubkeyPrefix}`}
            basePath="/nodes"
          >
            <FilterField label={t("common.search")}>
              <input
                type="text"
                name="search"
                defaultValue={search}
                placeholder={t("common.search_placeholder")}
                className="input input-sm w-80"
              />
            </FilterField>
            <FilterField label={t("common.type")}>
              <FilterSelect
                name="adv_type"
                defaultValue={advType}
                onChange={autoSubmit}
                options={[
                  { value: "", label: t("common.all_types") },
                  { value: "chat", label: t("node_types.chat") },
                  { value: "repeater", label: t("node_types.repeater") },
                  { value: "companion", label: t("node_types.companion") },
                  { value: "room", label: t("node_types.room") },
                ]}
              />
            </FilterField>
            {oidcEnabled && sortedProfiles.length > 0 && (
              <FilterField
                label={t("common.filter_operator_label")}
                className="max-w-56"
              >
                <OperatorSelect
                  name="adopted_by"
                  defaultValue={adoptedBy}
                  onChange={autoSubmit}
                  profiles={sortedProfiles}
                />
              </FilterField>
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
