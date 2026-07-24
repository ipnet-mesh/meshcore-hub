import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useAppConfig, hasRole } from "@/context/AppConfigContext";
import { apiGet, apiPut } from "@/utils/api";
import { qk, invalidate } from "@/utils/queryKeys";
import { resolveNodeName, useFormatDateTime } from "@/utils/format";
import { hasOperatorOrAdmin } from "@/utils/profileHelpers";
import { Loading, ErrorAlert, SuccessAlert } from "@/components/Alerts";
import { CallsignBadge, RoleBadge } from "@/components/Badges";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { PageHeader } from "@/components/PageHeader";
import { IconUser } from "@/components/icons";
import { TimeAgo } from "@/components/TimeAgo";
import { usePageTitle } from "@/hooks/usePageTitle";

interface ProfileNode {
  public_key: string;
  name?: string | null;
  last_seen?: string | null;
}

interface UserProfileData {
  id: string;
  user_id?: string | null;
  name?: string | null;
  callsign?: string | null;
  description?: string | null;
  url?: string | null;
  roles?: string[] | null;
  created_at?: string | null;
  nodes?: ProfileNode[] | null;
}

function RoleBadges({ roles }: { roles?: string[] | null }) {
  if (!roles || roles.length === 0) return null;
  return (
    <div className="flex gap-2 mt-2">
      {roles.map((role) => (
        <RoleBadge key={role} role={role} />
      ))}
    </div>
  );
}

function MemberSince({ createdAt }: { createdAt?: string | null }) {
  const { t } = useTranslation();
  const { formatDateTime } = useFormatDateTime();
  if (!createdAt) return null;
  return (
    <p className="text-sm opacity-60 mt-2">
      {t("user_profile.member_since", {
        date: formatDateTime(createdAt, {
          year: "numeric",
          month: "long",
          day: "numeric",
        }),
      })}
    </p>
  );
}

function AdoptedNodeLink({ node }: { node: ProfileNode }) {
  const displayName = resolveNodeName(node);

  return (
    <Link
      to={`/nodes/${node.public_key}`}
      className="flex items-center justify-between gap-3 p-3 bg-base-200 rounded-box hover:bg-base-300 transition-colors"
    >
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm truncate">{displayName}</div>
        <div className="font-mono text-xs opacity-60 truncate">
          {node.public_key}
        </div>
      </div>
      {node.last_seen ? (
        <TimeAgo
          iso={node.last_seen}
          className="text-xs opacity-60 whitespace-nowrap shrink-0"
        />
      ) : (
        <span className="text-xs opacity-60 whitespace-nowrap shrink-0">
          -
        </span>
      )}
    </Link>
  );
}

function AdoptedNodesCard({
  profile,
  className,
}: {
  profile: UserProfileData;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className={`card bg-base-100 shadow-xl ${className ?? ""}`}>
      <div className="card-body">
        <h2 className="card-title">{t("user_profile.adopted_nodes")}</h2>
        {profile.nodes && profile.nodes.length > 0 ? (
          <div className="space-y-2">
            {profile.nodes.map((node) => (
              <AdoptedNodeLink key={node.public_key} node={node} />
            ))}
          </div>
        ) : (
          <p className="opacity-60 text-sm py-4">
            {t("user_profile.no_adopted_nodes")}
          </p>
        )}
      </div>
    </div>
  );
}

function ProfileEditForm({
  profile,
  onSuccess,
  onError,
}: {
  profile: UserProfileData;
  onSuccess?: () => void;
  onError?: (msg: string) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: Record<string, unknown>;
    }) => apiPut(`/api/v1/user/profile/${id}`, body),
    onSuccess: () => invalidate.profiles(queryClient),
  });

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const body = {
      name: String(data.get("name") ?? "").trim() || null,
      callsign: String(data.get("callsign") ?? "").trim() || null,
      description: String(data.get("description") ?? "").trim() || null,
      url: String(data.get("url") ?? "").trim() || null,
    };
    try {
      await updateMutation.mutateAsync({ id: profile.id, body });
      onSuccess?.();
    } catch (err) {
      onError?.((err as Error).message);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="py-4 space-y-4" data-testid="profile-form">
      <label className="flex items-center gap-3 py-1">
        <span className="text-sm font-medium shrink-0 w-24">
          {t("user_profile.name_label")}
        </span>
        <input
          type="text"
          name="name"
          data-testid="profile-name"
          className="input flex-1"
          defaultValue={profile.name || ""}
          placeholder={t("user_profile.name_placeholder")}
          maxLength={255}
        />
      </label>
      <label className="flex items-center gap-3 py-1">
        <span className="text-sm font-medium shrink-0 w-24">
          {t("user_profile.callsign_label")}
        </span>
        <input
          type="text"
          name="callsign"
          data-testid="profile-callsign"
          className="input flex-1"
          defaultValue={profile.callsign || ""}
          placeholder={t("user_profile.callsign_placeholder")}
          maxLength={20}
        />
      </label>
      <label className="flex items-center gap-3 py-1">
        <span className="text-sm font-medium shrink-0 w-24">
          {t("user_profile.description_label")}
        </span>
        <input
          type="text"
          name="description"
          data-testid="profile-description"
          className="input flex-1"
          defaultValue={profile.description || ""}
          placeholder={t("user_profile.description_placeholder")}
          maxLength={500}
        />
      </label>
      <label className="flex items-center gap-3 py-1">
        <span className="text-sm font-medium shrink-0 w-24">
          {t("user_profile.url_label")}
        </span>
        <input
          type="url"
          name="url"
          data-testid="profile-url"
          className="input flex-1"
          defaultValue={profile.url || ""}
          placeholder={t("user_profile.url_placeholder")}
          maxLength={2048}
        />
      </label>
      <button
        type="submit"
        data-testid="profile-save"
        className="btn btn-primary btn-sm"
      >
        {t("user_profile.save_profile")}
      </button>
    </form>
  );
}

function PublicProfileView({ id }: { id: string }) {
  const { t } = useTranslation();
  const config = useAppConfig();
  const [editMode, setEditMode] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const { data: profile, error: queryError } = useQuery({
    queryKey: qk.profiles.detail(id),
    queryFn: ({ signal }) =>
      apiGet<UserProfileData>(`/api/v1/user/profile/${id}`, {}, { signal }),
  });
  const error = queryError ? queryError.message : null;

  if (error) return <ErrorAlert message={error} />;
  if (!profile) return <Loading />;

  const isOwner =
    !!config.user && !!profile.user_id && config.user.sub === profile.user_id;
  const isAdmin = hasRole("admin");

  return (
    <>
      <Breadcrumbs
        items={[
          { label: t("entities.home"), to: "/" },
          { label: t("entities.members"), to: "/members" },
          { label: profile.name || t("common.unnamed") },
        ]}
      />
      <PageHeader title={t("user_profile.title")} icon={IconUser}>
        {isOwner && (
          <Link to="/profile" className="btn btn-primary btn-sm">
            {t("user_profile.edit_profile")}
          </Link>
        )}
        {!isOwner && isAdmin && !editMode && (
          <button
            data-testid="profile-admin-edit"
            className="btn btn-primary btn-sm"
            onClick={() => {
              setEditMode(true);
              setEditError(null);
            }}
          >
            {t("user_profile.edit_profile")}
          </button>
        )}
        {editMode && (
          <button
            data-testid="profile-admin-cancel"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setEditMode(false);
              setEditError(null);
            }}
          >
            {t("common.cancel")}
          </button>
        )}
      </PageHeader>

      {editMode && isAdmin ? (
        <div className="card bg-base-100 shadow-xl">
          <div className="card-body">
            <h2 className="card-title">{t("user_profile.edit_profile")}</h2>
            <RoleBadges roles={profile.roles} />
            {editError && <ErrorAlert message={editError} />}
            <ProfileEditForm
              profile={profile}
              onSuccess={() => {
                setEditMode(false);
                setEditError(null);
              }}
              onError={(msg) => setEditError(msg)}
            />
            <MemberSince createdAt={profile.created_at} />
          </div>
        </div>
      ) : (
        <div className="card bg-base-100 shadow-xl">
          <div className="card-body">
            <h2 className="card-title">
              {profile.name || t("common.unnamed")}
              {profile.callsign && (
                <CallsignBadge callsign={profile.callsign} />
              )}
            </h2>
            <RoleBadges roles={profile.roles} />
            {profile.description && (
              <p className="text-sm opacity-80 mt-2">{profile.description}</p>
            )}
            {profile.url && (
              <a
                href={profile.url}
                target="_blank"
                rel="noopener noreferrer"
                className="link link-primary text-sm mt-1 inline-block"
              >
                {profile.url}
              </a>
            )}
            <MemberSince createdAt={profile.created_at} />
            {hasOperatorOrAdmin(profile.roles, config) && (
              <AdoptedNodesCard profile={profile} className="mt-6" />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function OwnProfileView() {
  const { t } = useTranslation();
  const config = useAppConfig();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: profile, error: queryError } = useQuery({
    queryKey: qk.profiles.me(),
    queryFn: ({ signal }) =>
      apiGet<UserProfileData>("/api/v1/user/profile/me", {}, { signal }),
  });
  const error = queryError ? queryError.message : null;

  if (!config.oidc_enabled || !config.user) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <h1 className="text-3xl font-bold mb-2">{t("user_profile.title")}</h1>
        <p className="opacity-70 mb-6">{t("user_profile.login_to_view")}</p>
        <a href="/auth/login" className="btn btn-primary">
          {t("auth.login")}
        </a>
      </div>
    );
  }

  if (error) return <ErrorAlert message={error} />;
  if (!profile) return <Loading />;

  const flashMessage = searchParams.get("message") || "";
  const flashError = searchParams.get("error") || "";

  return (
    <>
      <Breadcrumbs
        items={[
          { label: t("entities.home"), to: "/" },
          { label: t("user_profile.title") },
        ]}
      />
      <PageHeader title={t("user_profile.title")} icon={IconUser} />

      {flashMessage ? (
        <SuccessAlert message={flashMessage} />
      ) : flashError ? (
        <ErrorAlert message={flashError} />
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h2 className="card-title">{t("user_profile.your_profile")}</h2>
              <RoleBadges roles={profile.roles} />
              <ProfileEditForm
                profile={profile}
                onSuccess={() =>
                  navigate(
                    "/profile?message=" +
                      encodeURIComponent(t("user_profile.profile_updated")),
                    { replace: true },
                  )
                }
                onError={(msg) =>
                  navigate(
                    "/profile?error=" + encodeURIComponent(msg),
                    { replace: true },
                  )
                }
              />
              <MemberSince createdAt={profile.created_at} />
            </div>
          </div>
        </div>

        {hasOperatorOrAdmin(profile.roles, config) && (
          <AdoptedNodesCard profile={profile} />
        )}
      </div>
    </>
  );
}

export function Profile() {
  const { id } = useParams();
  usePageTitle("links.profile");

  return id ? <PublicProfileView id={id} /> : <OwnProfileView />;
}
