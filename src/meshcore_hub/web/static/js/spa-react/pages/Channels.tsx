import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { useAppConfig, hasRole } from "@/context/AppConfigContext";
import { apiGet, apiPost, apiPut, apiDelete } from "@/utils/api";
import { qk, invalidate } from "@/utils/queryKeys";
import { usePageTitle } from "@/hooks/usePageTitle";
import { Loading, ErrorAlert } from "@/components/Alerts";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { MeshQrCode } from "@/components/MeshQrCode";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { SectionGroup } from "@/components/SectionGroup";
import { IconChannel, IconPlus, IconEdit, IconTrash } from "@/components/icons";

interface Channel {
  id: string;
  name: string;
  channel_hash: string;
  visibility: string;
  enabled: boolean;
  masked_key: string;
  key_hex: string | null;
  created_at: string;
  updated_at: string;
}

interface ChannelListResponse {
  items: Channel[];
  total: number;
}

const VISIBILITY_ORDER = ["community", "member", "operator", "admin"];

type ModalState =
  | { type: "add" }
  | { type: "edit"; channel: Channel }
  | { type: "delete"; channel: Channel };

function ChannelQrCode({ channel }: { channel: Channel }) {
  if (!channel.key_hex) return null;
  const qrUrl = `meshcore://channel/add?name=${encodeURIComponent(channel.name)}&secret=${channel.key_hex.toLowerCase()}`;
  return <MeshQrCode value={qrUrl} size={128} level="M" />;
}

interface ChannelCardProps {
  channel: Channel;
  oidcEnabled: boolean;
  isAdmin: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onNavigate: (channelIdx: number) => void;
}

function ChannelCard({
  channel,
  oidcEnabled,
  isAdmin,
  onEdit,
  onDelete,
  onNavigate,
}: ChannelCardProps) {
  const { t } = useTranslation();
  const channelIdx = parseInt(channel.channel_hash, 16);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onNavigate(channelIdx);
    }
  };

  return (
    <div
      className="card bg-base-100 shadow-xl cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      role="button"
      tabIndex={0}
      onClick={() => onNavigate(channelIdx)}
      onKeyDown={handleKeyDown}
    >
      <div className="card-body flex-row gap-4">
        <div className="flex-1 min-w-0">
          <h2 className="card-title flex items-center gap-2">
            {channel.name}
            {oidcEnabled && (
              <span className="badge badge-primary badge-sm">
                {channel.visibility}
              </span>
            )}
            {!channel.enabled && (
              <span className="badge badge-ghost badge-sm">
                {t("channels.disabled")}
              </span>
            )}
          </h2>
          {channel.key_hex && (
            <div className="font-mono text-xs opacity-70 mt-1 break-all select-all">
              {channel.key_hex.toLowerCase()}
            </div>
          )}
          {isAdmin && (
            <div className="flex gap-2 mt-2">
              <button
                className="btn btn-xs btn-outline"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit();
                }}
              >
                <IconEdit className="h-3 w-3" /> {t("common.edit")}
              </button>
              <button
                className="btn btn-xs btn-outline btn-error"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
              >
                <IconTrash className="h-3 w-3" /> {t("common.delete")}
              </button>
            </div>
          )}
        </div>
        <div className="flex-shrink-0 self-center">
          {channel.key_hex && <ChannelQrCode channel={channel} />}
        </div>
      </div>
    </div>
  );
}

interface ChannelModalProps {
  isEdit: boolean;
  channel: Channel | null;
  saving: boolean;
  onSave: (body: Record<string, unknown>) => void;
  onCancel: () => void;
}

function ChannelModal({
  isEdit,
  channel,
  saving,
  onSave,
  onCancel,
}: ChannelModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(channel?.name ?? "");
  const [keyHex, setKeyHex] = useState("");
  const [visibility, setVisibility] = useState(
    channel?.visibility ?? "community",
  );
  const [enabled, setEnabled] = useState(channel?.enabled !== false);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const body: Record<string, unknown> = { visibility, enabled };
    if (!isEdit) {
      body.name = name.trim();
      body.key_hex = keyHex.trim().toUpperCase();
    }
    onSave(body);
  };

  const title = isEdit
    ? t("channels.edit_channel")
    : t("channels.add_channel");

  return (
    <Modal title={title} onClose={onCancel}>
        <form onSubmit={handleSubmit}>
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 items-center mb-4">
            <label className="text-sm opacity-70 text-right">
              {t("channels.name_label")}
            </label>
            <input
              type="text"
              className="input input-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isEdit}
              placeholder={t("channels.name_label")}
              required
              maxLength={100}
            />
            {!isEdit && (
              <>
                <label className="text-sm opacity-70 text-right">
                  {t("channels.key_label")}
                </label>
                <input
                  type="text"
                  className="input input-sm font-mono"
                  value={keyHex}
                  onChange={(e) => setKeyHex(e.target.value)}
                  placeholder="e.g. ABCDEF0123456789..."
                  required
                  minLength={32}
                  maxLength={64}
                  pattern="[0-9A-Fa-f]{32,64}"
                />
              </>
            )}
            <label className="text-sm opacity-70 text-right">
              {t("channels.visibility_label")}
            </label>
            <select
              className="select select-sm"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
            >
              <option value="community">community</option>
              <option value="member">member</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
            <div></div>
            <label className="label cursor-pointer justify-start gap-3">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              <span className="text-sm">{t("channels.enabled_label")}</span>
            </label>
          </div>
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={onCancel}
              disabled={saving}
            >
              {t("common.cancel")}
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving && (
                <span className="loading loading-spinner loading-sm"></span>
              )}
              {t("common.save")}
            </button>
          </div>
        </form>
    </Modal>
  );
}

interface DeleteChannelModalProps {
  channel: Channel;
  saving: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function DeleteChannelModal({
  channel,
  saving,
  onConfirm,
  onCancel,
}: DeleteChannelModalProps) {
  const { t } = useTranslation();

  return (
    <ConfirmDialog
      title={t("channels.delete_channel")}
      message={<p>{t("channels.delete_confirm", { name: channel.name })}</p>}
      confirmLabel={t("common.delete")}
      cancelLabel={t("common.cancel")}
      saving={saving}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

export function Channels() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const config = useAppConfig();
  const oidcEnabled = config.oidc_enabled;
  const isAdmin = hasRole("admin");
  usePageTitle("entities.channels");

  const queryClient = useQueryClient();

  const {
    data,
    isLoading: loading,
    error: queryError,
  } = useQuery({
    queryKey: qk.channels.list({}),
    queryFn: ({ signal }) =>
      apiGet<ChannelListResponse>("/api/v1/channels", {}, { signal }),
  });
  const channels = data?.items ?? [];
  const error = queryError ? queryError.message : null;
  const [modal, setModal] = useState<ModalState | null>(null);

  const saveMutation = useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id?: string;
      body: Record<string, unknown>;
    }) => {
      if (id) {
        await apiPut(`/api/v1/channels/${id}`, body);
      } else {
        await apiPost("/api/v1/channels", body);
      }
    },
    onSuccess: () => invalidate.channels(queryClient),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiDelete(`/api/v1/channels/${id}`),
    onSuccess: () => invalidate.channels(queryClient),
  });

  const saving = saveMutation.isPending || deleteMutation.isPending;

  const handleSave = async (body: Record<string, unknown>) => {
    try {
      await saveMutation.mutateAsync({
        id: modal?.type === "edit" ? modal.channel.id : undefined,
        body,
      });
      setModal(null);
    } catch (e) {
      alert((e as Error).message || "Failed to save channel");
    }
  };

  const handleDeleteConfirm = async () => {
    if (modal?.type !== "delete") return;
    try {
      await deleteMutation.mutateAsync(modal.channel.id);
      setModal(null);
    } catch (e) {
      alert((e as Error).message || "Failed to delete channel");
    }
  };

  const handleNavigate = (channelIdx: number) => {
    navigate(`/messages?channel_idx=${channelIdx}`);
  };

  const groups = new Map<string, Channel[]>();
  for (const vis of VISIBILITY_ORDER) {
    groups.set(vis, []);
  }
  for (const ch of channels) {
    const vis = ch.visibility || "community";
    if (!groups.has(vis)) groups.set(vis, []);
    groups.get(vis)!.push(ch);
  }

  if (loading) return <Loading />;

  return (
    <div>
      <PageHeader title={t("entities.channels")} icon={IconChannel} />

      {error && <ErrorAlert message={error} />}

      {isAdmin && (
        <div className="flex justify-end mb-4">
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setModal({ type: "add" })}
          >
            <IconPlus className="h-4 w-4" /> {t("channels.add_channel")}
          </button>
        </div>
      )}

      {channels.length === 0 && (
        <EmptyState>
          {t("common.no_entity_found", {
            entity: t("entities.channels").toLowerCase(),
          })}
        </EmptyState>
      )}

      {VISIBILITY_ORDER.map((vis) => {
        const group = groups.get(vis);
        if (!group || group.length === 0) return null;
        return (
          <div key={vis}>
            <SectionGroup title={t(`channels.visibility_${vis}`)}>
              {group.map((ch) => (
                <ChannelCard
                  key={ch.id}
                  channel={ch}
                  oidcEnabled={oidcEnabled}
                  isAdmin={isAdmin}
                  onEdit={() => setModal({ type: "edit", channel: ch })}
                  onDelete={() => setModal({ type: "delete", channel: ch })}
                  onNavigate={handleNavigate}
                />
              ))}
            </SectionGroup>
          </div>
        );
      })}

      {modal && (modal.type === "add" || modal.type === "edit") && (
        <ChannelModal
          key={modal.type === "edit" ? `edit-${modal.channel.id}` : "add"}
          isEdit={modal.type === "edit"}
          channel={modal.type === "edit" ? modal.channel : null}
          saving={saving}
          onSave={handleSave}
          onCancel={() => setModal(null)}
        />
      )}

      {modal?.type === "delete" && (
        <DeleteChannelModal
          channel={modal.channel}
          saving={saving}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  );
}
