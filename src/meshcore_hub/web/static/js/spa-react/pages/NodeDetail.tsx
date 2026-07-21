import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { ErrorAlert, Loading, SuccessAlert } from "@/components/Alerts";
import { IconEdit, IconError, IconPlus, IconTrash } from "@/components/icons";
import { hasRole, useAppConfig } from "@/context/AppConfigContext";
import { usePageTitle } from "@/hooks/usePageTitle";
import { apiDelete, apiGet, apiPost, apiPut, isAbortError } from "@/utils/api";
import { copyToClipboard } from "@/utils/clipboard";
import { typeEmoji, truncateKey, useFormatDateTime } from "@/utils/format";

interface NodeTag {
  key: string;
  value: string | null;
  value_type: string | null;
}

interface AdoptionInfo {
  user_id: string;
  name: string | null;
  profile_id: string;
}

interface NodeDetailData {
  public_key: string;
  name: string | null;
  adv_type: string | null;
  lat: number | null;
  lon: number | null;
  first_seen: string | null;
  last_seen: string | null;
  tags: NodeTag[] | null;
  adopted_by: AdoptionInfo | null;
}

interface AdvertisementItem {
  received_at: string | null;
  adv_type: string | null;
  observed_by: string | null;
  observer_name: string | null;
  observer_tag_name: string | null;
}

interface AdvertisementListResponse {
  items: AdvertisementItem[];
}

interface PrefixResolution {
  public_key: string;
}

interface FlashState {
  type: "success" | "error";
  message: string;
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function NodeDetailPage() {
  const { t } = useTranslation();
  const config = useAppConfig();
  const navigate = useNavigate();
  const { publicKey: publicKeyParam } = useParams();
  const [searchParams] = useSearchParams();
  const { formatDateTime } = useFormatDateTime();
  usePageTitle("entities.node_detail");

  const publicKey = publicKeyParam ?? "";
  const searchKey = searchParams.toString();
  const flashMessage = searchParams.get("message") || "";
  const flashError = searchParams.get("error") || "";

  const [node, setNode] = useState<NodeDetailData | null>(null);
  const [advertisements, setAdvertisements] = useState<AdvertisementItem[]>(
    [],
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [flash, setFlash] = useState<FlashState | null>(null);

  const [addKey, setAddKey] = useState("");
  const [addValue, setAddValue] = useState("");
  const [addType, setAddType] = useState("string");
  const [addError, setAddError] = useState("");

  const [editTag, setEditTag] = useState<NodeTag | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editType, setEditType] = useState("string");
  const [editError, setEditError] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  const [deleteSaving, setDeleteSaving] = useState(false);

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const qrRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<unknown>(null);
  const qrInitRef = useRef(false);

  useEffect(() => {
    if (!publicKey || publicKey.length === 64) return;
    const ac = new AbortController();
    (async () => {
      try {
        const resolved = await apiGet<PrefixResolution>(
          `/api/v1/nodes/prefix/${encodeURIComponent(publicKey)}`,
          {},
          { signal: ac.signal },
        );
        navigate(`/nodes/${resolved.public_key}`, { replace: true });
      } catch (e) {
        if (isAbortError(e)) return;
        if (errorMessage(e).includes("404")) {
          setNotFound(true);
        } else {
          setError(errorMessage(e));
        }
        setLoading(false);
      }
    })();
    return () => ac.abort();
  }, [publicKey, navigate]);

  const loadData = useCallback(
    async (signal: AbortSignal) => {
      try {
        const [nodeData, adsData] = await Promise.all([
          apiGet<NodeDetailData | null>(
            `/api/v1/nodes/${publicKey}`,
            {},
            { signal },
          ),
          apiGet<AdvertisementListResponse>(
            "/api/v1/advertisements",
            { public_key: publicKey, limit: 10 },
            { signal },
          ),
          apiGet<unknown>(
            "/api/v1/telemetry",
            { node_public_key: publicKey, limit: 10 },
            { signal },
          ),
        ]);
        if (!nodeData) {
          setNotFound(true);
          return;
        }
        setNode(nodeData);
        setAdvertisements(adsData.items || []);
        setNotFound(false);
        setError(null);
      } catch (e) {
        if (isAbortError(e)) return;
        if (errorMessage(e).includes("404")) {
          setNotFound(true);
        } else {
          setError(errorMessage(e));
        }
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [publicKey],
  );

  useEffect(() => {
    if (!publicKey || publicKey.length !== 64) return;
    const ac = new AbortController();
    loadData(ac.signal);
    return () => ac.abort();
  }, [loadData, searchKey]);

  let lat: number | null = node?.lat ?? null;
  let lon: number | null = node?.lon ?? null;
  if (node) {
    for (const tag of node.tags || []) {
      if (tag.key === "lat" && !lat) lat = parseFloat(tag.value ?? "");
      if (tag.key === "lon" && !lon) lon = parseFloat(tag.value ?? "");
    }
  }
  const hasCoords =
    lat != null &&
    lon != null &&
    !Number.isNaN(lat) &&
    !Number.isNaN(lon) &&
    !(lat === 0 && lon === 0);

  const tagName = node?.tags?.find((tag) => tag.key === "name")?.value ?? null;
  const tagDescription =
    node?.tags?.find((tag) => tag.key === "description")?.value ?? null;
  const displayName = tagName || node?.name || t("common.unnamed_node");
  const emoji = typeEmoji(node?.adv_type ?? null);

  useEffect(() => {
    if (!node || !hasCoords || lat == null || lon == null) return;
    const L = (window as any).L;
    const mapEl = mapContainerRef.current;
    if (!L || !mapEl) return;
    const map = L.map(mapEl, {
      zoomControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      attributionControl: false,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(
      map,
    );
    map.setView([lat, lon], 14);
    const point = map.latLngToContainerPoint([lat, lon]);
    const newPoint = L.point(point.x + map.getSize().x * 0.17, point.y);
    const newLatLng = map.containerPointToLatLng(newPoint);
    map.setView(newLatLng, 14, { animate: false });
    const mapIcon = L.divIcon({
      html:
        '<span style="font-size: 32px; text-shadow: 0 0 3px #1a237e, 0 0 6px #1a237e, 0 1px 2px rgba(0,0,0,0.7);">' +
        emoji +
        "</span>",
      className: "",
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });
    L.marker([lat, lon], { icon: mapIcon }).addTo(map);
    mapRef.current = map;
    return () => {
      mapRef.current = null;
      map.remove();
    };
  }, [node, hasCoords, lat, lon, emoji]);

  useEffect(() => {
    if (!node) return;
    qrInitRef.current = false;
    const typeMap: Record<string, number> = {
      chat: 1,
      repeater: 2,
      room: 3,
      companion: 1,
      sensor: 4,
    };
    const typeNum = typeMap[(node.adv_type || "").toLowerCase()] || 1;
    const url =
      "meshcore://contact/add?name=" +
      encodeURIComponent(displayName) +
      "&public_key=" +
      node.public_key +
      "&type=" +
      typeNum;
    const initQr = (): boolean => {
      const QRCode = (window as any).QRCode;
      const el = qrRef.current;
      if (!QRCode || !el || qrInitRef.current) return false;
      el.innerHTML = "";
      new QRCode(el, {
        text: url,
        width: 140,
        height: 140,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.L,
      });
      qrInitRef.current = true;
      return true;
    };
    if (initQr()) return;
    let attempts = 0;
    const interval = setInterval(() => {
      if (initQr() || ++attempts >= 20) clearInterval(interval);
    }, 100);
    return () => clearInterval(interval);
  }, [node, displayName, hasCoords]);

  useEffect(() => {
    if (!flash) return;
    const timer = setTimeout(() => setFlash(null), 3000);
    return () => clearTimeout(timer);
  }, [flash]);

  const showFlash = (type: "success" | "error", message: string) => {
    setFlash({ type, message });
  };

  const reloadNode = () => {
    navigate(`/nodes/${publicKey}?refresh=${Date.now()}`, { replace: true });
  };

  const validateTagValue = (value: string, type: string): string | null => {
    if (!value || !type) return null;
    if (type === "number" && isNaN(Number(value))) {
      return t("common.validation_invalid_number");
    }
    if (type === "boolean") {
      const normalized = value.toLowerCase().trim();
      if (!["true", "false", "yes", "no", "1", "0"].includes(normalized)) {
        return t("common.validation_invalid_boolean");
      }
    }
    return null;
  };

  const handleAdopt = async () => {
    if (!node) return;
    try {
      await apiPost("/api/v1/adoptions", { public_key: node.public_key });
      navigate(
        `/nodes/${node.public_key}?message=${encodeURIComponent(t("nodes.adopt_success"))}`,
        { replace: true },
      );
    } catch (e) {
      navigate(
        `/nodes/${node.public_key}?error=${encodeURIComponent(errorMessage(e))}`,
        { replace: true },
      );
    }
  };

  const handleRelease = async () => {
    if (!node) return;
    if (!confirm(t("nodes.release_confirm"))) return;
    try {
      await apiDelete(`/api/v1/adoptions/${node.public_key}`);
      navigate(
        `/nodes/${node.public_key}?message=${encodeURIComponent(t("nodes.release_success"))}`,
        { replace: true },
      );
    } catch (e) {
      navigate(
        `/nodes/${node.public_key}?error=${encodeURIComponent(errorMessage(e))}`,
        { replace: true },
      );
    }
  };

  const handleAddTag = async (e: FormEvent) => {
    e.preventDefault();
    if (!node) return;
    const validationError = validateTagValue(addValue, addType);
    if (validationError) {
      setAddError(validationError);
      return;
    }
    setAddError("");
    try {
      await apiPost(`/api/v1/nodes/${node.public_key}/tags`, {
        key: addKey,
        value: addValue,
        value_type: addType,
      });
      setAddKey("");
      setAddValue("");
      setAddType("string");
      showFlash(
        "success",
        t("common.entity_added_success", { entity: t("entities.tag") }),
      );
      reloadNode();
    } catch (e) {
      showFlash("error", errorMessage(e));
    }
  };

  const openEditTag = (tag: NodeTag) => {
    setEditTag(tag);
    setEditValue(tag.value ?? "");
    setEditType(tag.value_type || "string");
    setEditError("");
  };

  const handleEditTag = async (e: FormEvent) => {
    e.preventDefault();
    if (!node || !editTag) return;
    const validationError = validateTagValue(editValue, editType);
    if (validationError) {
      setEditError(validationError);
      return;
    }
    setEditError("");
    setEditSaving(true);
    try {
      await apiPut(
        `/api/v1/nodes/${node.public_key}/tags/${encodeURIComponent(editTag.key)}`,
        { value: editValue, value_type: editType },
      );
      setEditTag(null);
      showFlash(
        "success",
        t("common.entity_updated_success", { entity: t("entities.tag") }),
      );
      reloadNode();
    } catch (e) {
      setEditError(errorMessage(e));
    } finally {
      setEditSaving(false);
    }
  };

  const handleDeleteTag = async () => {
    if (!node || deleteKey === null) return;
    setDeleteSaving(true);
    try {
      await apiDelete(
        `/api/v1/nodes/${node.public_key}/tags/${encodeURIComponent(deleteKey)}`,
      );
      setDeleteKey(null);
      showFlash(
        "success",
        t("common.entity_deleted_success", { entity: t("entities.tag") }),
      );
      reloadNode();
    } catch (e) {
      setDeleteKey(null);
      showFlash("error", errorMessage(e));
    } finally {
      setDeleteSaving(false);
    }
  };

  if (!node) {
    if (notFound) {
      return (
        <>
          <div className="breadcrumbs text-sm mb-4">
            <ul>
              <li>
                <Link to="/">{t("entities.home")}</Link>
              </li>
              <li>
                <Link to="/nodes">{t("entities.nodes")}</Link>
              </li>
              <li>{t("common.page_not_found")}</li>
            </ul>
          </div>
          <div className="alert alert-error">
            <IconError className="stroke-current shrink-0 h-6 w-6" />
            <span>
              {t("common.entity_not_found_details", {
                entity: t("entities.node"),
                details: publicKey,
              })}
            </span>
          </div>
          <Link to="/nodes" className="btn btn-primary mt-4">
            {t("common.view_entity", { entity: t("entities.nodes") })}
          </Link>
        </>
      );
    }
    if (error) {
      return <ErrorAlert message={error} />;
    }
    return <Loading />;
  }

  const canEditTags =
    config.oidc_enabled &&
    !!config.user &&
    (hasRole("admin") ||
      (hasRole("operator") && node.adopted_by?.user_id === config.user.sub));

  const isOperator = hasRole("operator");
  const isAdmin = hasRole("admin");

  let adoptionCard: ReactNode = null;
  if (config.oidc_enabled && config.user) {
    if (node.adopted_by) {
      const adoptedBy = node.adopted_by;
      const ownerName = adoptedBy.name || adoptedBy.user_id;
      const canRelease =
        (isOperator || isAdmin) &&
        (adoptedBy.user_id === config.user.sub || isAdmin);
      adoptionCard = (
        <div className="card bg-base-100 shadow-xl h-full">
          <div className="card-body">
            <h2 className="card-title">{t("nodes.ownership")}</h2>
            <div className="flex items-center justify-between">
              <p className="text-sm opacity-70">
                {t("nodes.adopted_by_prefix")}{" "}
                <Link
                  to={`/profile/${adoptedBy.profile_id}`}
                  className="link link-hover text-primary"
                >
                  {ownerName}
                </Link>
              </p>
              {canRelease && (
                <button
                  className="btn btn-sm btn-outline btn-error"
                  onClick={handleRelease}
                >
                  {t("nodes.release")}
                </button>
              )}
            </div>
          </div>
        </div>
      );
    } else if (isOperator || isAdmin) {
      adoptionCard = (
        <div className="card bg-base-100 shadow-xl h-full">
          <div className="card-body">
            <h2 className="card-title">{t("nodes.ownership")}</h2>
            <p className="text-sm opacity-70">{t("nodes.not_adopted")}</p>
            <div className="mt-2">
              <button className="btn btn-sm btn-primary" onClick={handleAdopt}>
                {t("nodes.adopt")}
              </button>
            </div>
          </div>
        </div>
      );
    }
  }

  const publicKeyCard = (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body">
        <div>
          <h3 className="font-semibold opacity-70 mb-2">
            {t("common.public_key")}
          </h3>
          <code
            className="text-sm bg-base-200 p-2 rounded block break-all cursor-pointer hover:bg-base-300 select-all"
            onClick={(e) => copyToClipboard(e, node.public_key)}
            title="Click to copy"
          >
            {node.public_key}
          </code>
        </div>
        <div className="flex flex-wrap gap-x-8 gap-y-2 mt-4 text-sm">
          <div>
            <span className="opacity-70">{t("common.first_seen_label")}</span>{" "}
            {formatDateTime(node.first_seen)}
          </div>
          <div>
            <span className="opacity-70">{t("common.last_seen_label")}</span>{" "}
            {formatDateTime(node.last_seen)}
          </div>
          {hasCoords && (
            <div>
              <span className="opacity-70">{t("common.location")}:</span>{" "}
              {lat}, {lon}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  const tags = node.tags || [];

  const tagsTable = canEditTags ? (
    tags.length > 0 ? (
      <div className="overflow-x-auto">
        <table className="table table-sm w-full">
          <thead>
            <tr>
              <th>{t("common.key")}</th>
              <th>{t("common.value")}</th>
              <th className="hidden sm:table-cell">{t("common.type")}</th>
              <th className="w-16">{t("common.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {tags.map((tag) => (
              <tr key={tag.key}>
                <td className="font-mono min-w-0 truncate max-w-[8rem]">
                  {tag.key}
                </td>
                <td className="min-w-0 truncate max-w-[12rem]">
                  {tag.value || ""}
                </td>
                <td className="hidden sm:table-cell opacity-70">
                  {tag.value_type || "string"}
                </td>
                <td>
                  <div className="flex gap-1">
                    <button
                      className="btn btn-xs btn-ghost"
                      onClick={() => openEditTag(tag)}
                    >
                      <IconEdit className="h-4 w-4" />
                    </button>
                    <button
                      className="btn btn-xs btn-ghost"
                      onClick={() => setDeleteKey(tag.key)}
                    >
                      <IconTrash className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <p className="opacity-70">
        {t("common.no_entity_defined", {
          entity: t("entities.tags").toLowerCase(),
        })}
      </p>
    )
  ) : tags.length > 0 ? (
    <div className="overflow-x-auto">
      <table className="table table-sm w-full">
        <thead>
          <tr>
            <th>{t("common.key")}</th>
            <th>{t("common.value")}</th>
            <th>{t("common.type")}</th>
          </tr>
        </thead>
        <tbody>
          {tags.map((tag) => (
            <tr key={tag.key}>
              <td className="font-mono">{tag.key}</td>
              <td>{tag.value || ""}</td>
              <td className="opacity-70">{tag.value_type || "string"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="opacity-70">
      {t("common.no_entity_defined", {
        entity: t("entities.tags").toLowerCase(),
      })}
    </p>
  );

  return (
    <>
      <div className="breadcrumbs text-sm mb-4">
        <ul>
          <li>
            <Link to="/">{t("entities.home")}</Link>
          </li>
          <li>
            <Link to="/nodes">{t("entities.nodes")}</Link>
          </li>
          <li>{tagName || node.name || truncateKey(node.public_key)}</li>
        </ul>
      </div>

      <div className="flex items-start gap-4 mb-6">
        <span
          className="text-6xl flex-shrink-0"
          title={node.adv_type || t("node_types.unknown")}
        >
          {emoji}
        </span>
        <div className="flex-1 min-w-0">
          <h1 className="text-3xl font-bold">{displayName}</h1>
          {tagDescription && (
            <p className="opacity-70 mt-2">{tagDescription}</p>
          )}
        </div>
      </div>

      {flashMessage ? (
        <SuccessAlert message={flashMessage} />
      ) : flashError ? (
        <ErrorAlert message={flashError} />
      ) : null}

      {flash &&
        (flash.type === "success" ? (
          <SuccessAlert message={flash.message} />
        ) : (
          <ErrorAlert message={flash.message} />
        ))}

      {hasCoords ? (
        <div
          className="relative rounded-box overflow-hidden mb-6 shadow-xl"
          style={{ height: 180 }}
        >
          <div ref={mapContainerRef} className="absolute inset-0 z-0" />
          <div className="relative z-20 h-full p-3 flex items-center justify-end">
            <div ref={qrRef} className="bg-white p-2 rounded-box shadow-lg" />
          </div>
        </div>
      ) : (
        <div className="card bg-base-100 shadow-xl mb-6">
          <div className="card-body flex-row items-center gap-4">
            <div ref={qrRef} className="bg-white p-2 rounded-box" />
            <p className="text-sm opacity-70">{t("nodes.scan_to_add")}</p>
          </div>
        </div>
      )}

      {adoptionCard ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {publicKeyCard}
          {adoptionCard}
        </div>
      ) : (
        <div className="mb-6">{publicKeyCard}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card bg-base-100 shadow-xl">
          <div className="card-body">
            <h2 className="card-title">
              {t("common.recent_entity", {
                entity: t("entities.advertisements"),
              })}
            </h2>
            {advertisements.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="table table-sm w-full">
                  <thead>
                    <tr>
                      <th>{t("common.time")}</th>
                      <th>{t("common.type")}</th>
                      <th>{t("common.received_by")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {advertisements.map((adv, idx) => {
                      const recvName = adv.observed_by
                        ? (adv.observer_tag_name || adv.observer_name)
                        : null;
                      return (
                        <tr key={adv.observed_by ? `${adv.observed_by}-${adv.received_at}` : idx}>
                          <td className="text-xs whitespace-nowrap">
                            {formatDateTime(adv.received_at)}
                          </td>
                          <td>
                            {adv.adv_type ? (
                              <span
                                title={
                                  adv.adv_type.charAt(0).toUpperCase() +
                                  adv.adv_type.slice(1)
                                }
                              >
                                {typeEmoji(adv.adv_type)}
                              </span>
                            ) : (
                              <span className="opacity-50">-</span>
                            )}
                          </td>
                          <td>
                            {!adv.observed_by ? (
                              <span className="opacity-50">-</span>
                            ) : recvName ? (
                              <Link
                                to={`/nodes/${adv.observed_by}`}
                                className="link link-hover"
                              >
                                <div className="font-medium text-sm truncate max-w-[8rem]">
                                  {recvName}
                                </div>
                                <div className="text-xs font-mono opacity-70 hidden sm:block">
                                  {adv.observed_by.slice(0, 16)}...
                                </div>
                              </Link>
                            ) : (
                              <Link
                                to={`/nodes/${adv.observed_by}`}
                                className="link link-hover"
                              >
                                <span className="font-mono text-xs">
                                  {adv.observed_by.slice(0, 12)}...
                                </span>
                              </Link>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="opacity-70">
                {t("common.no_entity_recorded", {
                  entity: t("entities.advertisements").toLowerCase(),
                })}
              </p>
            )}
          </div>
        </div>

        <div className="card bg-base-100 shadow-xl">
          <div className="card-body">
            <h2 className="card-title">{t("entities.tags")}</h2>
            {tagsTable}
            {canEditTags && (
              <form className="mt-4" onSubmit={handleAddTag}>
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-2 items-end">
                  <div className="fieldset">
                    <input
                      type="text"
                      className="input input-sm w-full"
                      placeholder={t("common.key")}
                      required
                      value={addKey}
                      onChange={(e) => setAddKey(e.target.value)}
                    />
                  </div>
                  <div className="fieldset">
                    <input
                      type="text"
                      className="input input-sm w-full"
                      placeholder={t("common.value")}
                      value={addValue}
                      onChange={(e) => setAddValue(e.target.value)}
                    />
                    {addError && (
                      <div className="text-xs text-error">{addError}</div>
                    )}
                  </div>
                  <select
                    className="select select-sm w-28"
                    value={addType}
                    onChange={(e) => setAddType(e.target.value)}
                  >
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                  </select>
                  <button type="submit" className="btn btn-sm btn-primary">
                    <IconPlus className="h-4 w-4" /> {t("common.add")}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>

      {canEditTags && editTag && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">
              {t("common.edit_entity", { entity: t("entities.tag") })}:{" "}
              <span className="font-mono text-base font-normal">
                {editTag.key}
              </span>
            </h3>
            <form className="py-4" onSubmit={handleEditTag}>
              <div className="fieldset mb-4">
                <label className="fieldset-label">{t("common.value")}</label>
                <input
                  type="text"
                  className="input w-full"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                />
                {editError && (
                  <div className="text-xs text-error">{editError}</div>
                )}
              </div>
              <div className="fieldset mb-4">
                <label className="fieldset-label">{t("common.type")}</label>
                <select
                  className="select w-full"
                  value={editType}
                  onChange={(e) => setEditType(e.target.value)}
                >
                  <option value="string">string</option>
                  <option value="number">number</option>
                  <option value="boolean">boolean</option>
                </select>
              </div>
              <div className="modal-action">
                <button
                  type="button"
                  className="btn"
                  onClick={() => setEditTag(null)}
                  disabled={editSaving}
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={editSaving}
                >
                  {editSaving && (
                    <span className="loading loading-spinner loading-sm" />
                  )}
                  {t("common.save_changes")}
                </button>
              </div>
            </form>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => !editSaving && setEditTag(null)}
          />
        </div>
      )}

      {canEditTags && deleteKey !== null && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">
              {t("common.delete_entity", { entity: t("entities.tag") })}
            </h3>
            <p
              className="py-4"
              dangerouslySetInnerHTML={{
                __html: t("common.delete_entity_confirm", {
                  entity: t("entities.tag"),
                  name: deleteKey,
                }),
              }}
            />
            <div className="alert alert-error mb-4">
              <span>{t("common.cannot_be_undone")}</span>
            </div>
            <div className="modal-action">
              <button
                type="button"
                className="btn"
                onClick={() => setDeleteKey(null)}
                disabled={deleteSaving}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="btn btn-error"
                onClick={handleDeleteTag}
                disabled={deleteSaving}
              >
                {deleteSaving && (
                  <span className="loading loading-spinner loading-sm" />
                )}
                {t("common.delete")}
              </button>
            </div>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => !deleteSaving && setDeleteKey(null)}
          />
        </div>
      )}
    </>
  );
}
