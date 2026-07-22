import {
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useAppConfig } from "@/context/AppConfigContext";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { formatNumber, resolveNodeName } from "@/utils/format";
import { Loading, ErrorAlert } from "@/components/Alerts";
import { CallsignBadge, RoleBadge } from "@/components/Badges";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { IconAntenna, IconUsers } from "@/components/icons";
import { usePageTitle } from "@/hooks/usePageTitle";

interface MemberNode {
  public_key: string;
  name?: string | null;
}

interface MemberProfile {
  id: string;
  name?: string | null;
  callsign?: string | null;
  description?: string | null;
  url?: string | null;
  roles?: string[] | null;
  node_count?: number | null;
  adopted_nodes?: MemberNode[] | null;
}

interface ProfilesResponse {
  items?: MemberProfile[] | null;
}

function ProfileTile({ profile }: { profile: MemberProfile }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const openNode = (e: MouseEvent | KeyboardEvent, publicKey: string) => {
    e.preventDefault();
    e.stopPropagation();
    navigate(`/nodes/${publicKey}`);
  };

  const openUrl = (e: MouseEvent | KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
    window.open(profile.url ?? undefined, "_blank", "noopener,noreferrer");
  };

  return (
    <Link
      to={`/profile/${profile.id}`}
      data-testid="member-card"
      data-profile-name={profile.name || ""}
      className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow"
    >
      <div className="card-body">
        <h2 className="card-title">
          {profile.name || t("common.unnamed")}
          {profile.callsign && <CallsignBadge callsign={profile.callsign} />}
        </h2>
        {profile.roles && profile.roles.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {profile.roles.map((role) => (
              <RoleBadge key={role} role={role} />
            ))}
          </div>
        )}
        {profile.description && (
          <p className="text-sm opacity-70 mt-1 truncate">
            {profile.description}
          </p>
        )}
        {profile.url && (
          <span
            className="link link-accent text-xs mt-1 inline-block truncate cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            role="link"
            tabIndex={0}
            onClick={openUrl}
            onKeyDown={(e) => {
              if (e.key === "Enter") openUrl(e);
            }}
          >
            {profile.url}
          </span>
        )}
        {(profile.node_count ?? 0) > 0 && (
          <span className="text-sm opacity-60">
            {t("members_page.node_count", {
              count: formatNumber(profile.node_count),
            })}
          </span>
        )}
        {profile.adopted_nodes && profile.adopted_nodes.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {profile.adopted_nodes.map((node) => {
              const label = resolveNodeName(node);
              return (
                <span
                  key={node.public_key}
                  className="badge badge-secondary badge-sm cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  role="button"
                  data-testid="member-node-badge"
                  data-node-key={node.public_key}
                  tabIndex={0}
                  onClick={(e) => openNode(e, node.public_key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      openNode(e, node.public_key);
                    }
                  }}
                >
                  {label}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </Link>
  );
}

function ProfileGroup({
  title,
  icon,
  profiles,
}: {
  title: string;
  icon: ReactNode;
  profiles: MemberProfile[];
}) {
  if (profiles.length === 0) return null;
  return (
    <>
      <h2 className="text-2xl font-bold mt-8 mb-4 flex items-center gap-2">
        {icon}
        {title}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {profiles.map((profile) => (
          <ProfileTile key={profile.id} profile={profile} />
        ))}
      </div>
    </>
  );
}

export function Members() {
  const { t } = useTranslation();
  const config = useAppConfig();
  usePageTitle("entities.members");

  const { data, error: queryError } = useQuery({
    queryKey: qk.profiles.list({ limit: 500 }),
    queryFn: async ({ signal }) => {
      const resp = await apiGet<ProfilesResponse>(
        "/api/v1/user/profiles",
        { limit: 500 },
        { signal },
      );
      return resp.items || [];
    },
  });
  const profiles = data ?? null;
  const error = queryError ? queryError.message : null;

  if (error) return <ErrorAlert message={error} />;
  if (profiles === null) return <Loading />;

  const roleNames = config.role_names || {};
  const operatorRole = roleNames.operator || "operator";
  const memberRole = roleNames.member || "member";
  const testRole = roleNames.test || "test";

  const visible = profiles.filter((p) => !p.roles || !p.roles.includes(testRole));

  if (visible.length === 0) {
    return (
      <>
        <PageHeader title={t("entities.members")} />
        <EmptyState>
          <p className="text-lg">{t("members_page.empty_state")}</p>
          <p className="text-sm mt-2">{t("members_page.empty_description")}</p>
        </EmptyState>
      </>
    );
  }

  const byName = (a: MemberProfile, b: MemberProfile) =>
    (a.name || "").localeCompare(b.name || "");
  const operators = visible
    .filter((p) => !!p.roles && p.roles.includes(operatorRole))
    .sort(byName);
  const members = visible
    .filter(
      (p) =>
        !!p.roles && p.roles.includes(memberRole) && !p.roles.includes(operatorRole),
    )
    .sort(byName);

  return (
    <>
      <PageHeader title={t("entities.members")}>
        <span className="badge badge-lg">
          {t("common.count_entity", {
            count: formatNumber(operators.length + members.length),
            entity: t("entities.members").toLowerCase(),
          })}
        </span>
      </PageHeader>

      <ProfileGroup
        title={t("members_page.operators")}
        icon={
          <span className="text-primary">
            <IconAntenna className="h-6 w-6" />
          </span>
        }
        profiles={operators}
      />
      <ProfileGroup
        title={t("members_page.members")}
        icon={
          <span className="text-secondary">
            <IconUsers className="h-6 w-6" />
          </span>
        }
        profiles={members}
      />
    </>
  );
}
