import { type ComponentType, type SVGProps } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";

import { ErrorAlert, Loading } from "@/components/Alerts";
import { ActivityChart } from "@/components/charts/Charts";
import { StatCard } from "@/components/StatCard";
import {
  IconAdvertisements,
  IconAntenna,
  IconBandwidth,
  IconChannel,
  IconChart,
  IconCodingRate,
  IconDashboard,
  IconFrequency,
  IconInfo,
  IconMap,
  IconMembers,
  IconMessages,
  IconNodes,
  IconPage,
  IconPackets,
  IconPath,
  IconSettings,
  IconSpreadingFactor,
  IconTxPower,
  IconUsers,
} from "@/components/icons";
import { useAppConfig, useFeatures } from "@/context/AppConfigContext";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { usePageTitle } from "@/hooks/usePageTitle";
import type { RadioConfigDisplay } from "@/types/config";
import { apiGet } from "@/utils/api";
import { qk } from "@/utils/queryKeys";
import { getPageColor } from "@/utils/format";

interface DashboardStats {
  total_nodes: number;
  advertisements_7d: number;
  messages_7d: number;
  packets_7d: number;
  total_operators: number;
  total_members: number;
}

interface ActivitySeries {
  data: { date: string; count: number }[];
}

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

function NavCard({
  href,
  icon: Icon,
  label,
  colorVar,
}: {
  href: string;
  icon: IconComponent;
  label: string;
  colorVar: string;
}) {
  return (
    <Link
      to={href}
      className="w-20 h-20 sm:w-[6.75rem] sm:h-[6.75rem]
        border border-base-content/20 rounded-box
        hover:scale-105 hover:border-base-content/40
        transition-all duration-200 ease-out
        flex flex-col items-center justify-center gap-2
        bg-base-200/50 hover:bg-base-200
        group"
    >
      <span
        className="w-7 h-7 sm:w-9 sm:h-9 flex items-center justify-center"
        style={{ color: `var(${colorVar})` }}
      >
        <Icon className="w-full h-full" />
      </span>
      <span className="text-xs sm:text-sm font-medium text-base-content">
        {label}
      </span>
    </Link>
  );
}

function RadioTiles({ rc }: { rc?: RadioConfigDisplay }) {
  const { t } = useTranslation();
  if (!rc) return null;

  const tiles = [
    { icon: IconSettings, label: t("links.profile"), value: rc.profile },
    { icon: IconFrequency, label: t("home.frequency"), value: rc.frequency },
    { icon: IconBandwidth, label: t("home.bandwidth"), value: rc.bandwidth },
    {
      icon: IconSpreadingFactor,
      label: t("home.spreading_factor"),
      value: rc.spreading_factor,
    },
    {
      icon: IconCodingRate,
      label: t("home.coding_rate"),
      value: rc.coding_rate,
    },
    { icon: IconTxPower, label: t("home.tx_power"), value: rc.tx_power },
  ].filter((tile) => tile.value);

  if (tiles.length === 0) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      {tiles.map(({ icon: Icon, label, value }) => (
        <div
          key={label}
          className="flex flex-col items-center justify-center gap-1.5 p-3
            border border-base-content/10 rounded-box text-center"
        >
          <span className="radio-tile-icon w-6 h-6">
            <Icon className="w-full h-full" />
          </span>
          <span className="text-xs opacity-70 leading-tight">{label}</span>
          <span className="text-sm font-semibold leading-tight">
            {String(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  const config = useAppConfig();
  const features = useFeatures();
  usePageTitle();

  const networkName = config.network_name || "MeshCore Network";
  const logoUrl = config.logo_url || "/static/img/logo.svg";
  const logoInvertLight = config.logo_invert_light !== false;
  const customPages = config.custom_pages || [];

  const showStats =
    features.nodes !== false ||
    features.advertisements !== false ||
    features.messages !== false ||
    features.packets !== false;
  const showAdvertSeries = features.advertisements !== false;
  const showMessageSeries = features.messages !== false;
  const showActivityChart = showAdvertSeries || showMessageSeries;
  const showMembersPanel = features.members !== false;
  const showRadioPanel = features.radio_config !== false;

  const { refetchInterval } = useAutoRefresh();

  const statsQuery = useQuery({
    queryKey: qk.dashboard.stats(),
    queryFn: ({ signal }) =>
      apiGet<DashboardStats>("/api/v1/dashboard/stats", {}, { signal }),
    refetchInterval,
  });
  const advertQuery = useQuery({
    queryKey: qk.dashboard.series("activity", { days: 7 }),
    queryFn: ({ signal }) =>
      apiGet<ActivitySeries>(
        "/api/v1/dashboard/activity",
        { days: 7 },
        { signal },
      ),
    refetchInterval,
  });
  const messageQuery = useQuery({
    queryKey: qk.dashboard.series("message-activity", { days: 7 }),
    queryFn: ({ signal }) =>
      apiGet<ActivitySeries>(
        "/api/v1/dashboard/message-activity",
        { days: 7 },
        { signal },
      ),
    refetchInterval,
  });

  const stats = statsQuery.data ?? null;
  const advertActivity = advertQuery.data ?? null;
  const messageActivity = messageQuery.data ?? null;
  const loading =
    statsQuery.isLoading || advertQuery.isLoading || messageQuery.isLoading;
  const firstError =
    statsQuery.error ?? advertQuery.error ?? messageQuery.error;
  const error =
    !stats && firstError
      ? firstError.message || t("common.failed_to_load_page")
      : null;

  if (loading) return <Loading />;
  if (error) return <ErrorAlert message={error} />;
  if (!stats) return null;

  const navItems: {
    feature: string;
    href: string;
    icon: IconComponent;
    label: string;
    colorVar: string;
  }[] = [
    {
      feature: "dashboard",
      href: "/dashboard",
      icon: IconDashboard,
      label: t("entities.dashboard"),
      colorVar: "--color-dashboard",
    },
    {
      feature: "nodes",
      href: "/nodes",
      icon: IconNodes,
      label: t("entities.nodes"),
      colorVar: "--color-nodes",
    },
    {
      feature: "advertisements",
      href: "/advertisements",
      icon: IconAdvertisements,
      label: t("entities.advertisements"),
      colorVar: "--color-adverts",
    },
    {
      feature: "routes",
      href: "/routes",
      icon: IconPath,
      label: t("entities.routes"),
      colorVar: "--color-routes",
    },
    {
      feature: "channels",
      href: "/channels",
      icon: IconChannel,
      label: t("entities.channels"),
      colorVar: "--color-channels",
    },
    {
      feature: "messages",
      href: "/messages",
      icon: IconMessages,
      label: t("entities.messages"),
      colorVar: "--color-messages",
    },
    {
      feature: "packets",
      href: "/packets",
      icon: IconPackets,
      label: t("entities.packets"),
      colorVar: "--color-packets",
    },
    {
      feature: "map",
      href: "/map",
      icon: IconMap,
      label: t("entities.map"),
      colorVar: "--color-map",
    },
    {
      feature: "members",
      href: "/members",
      icon: IconMembers,
      label: t("entities.members"),
      colorVar: "--color-members",
    },
  ];

  return (
    <>
      <div
        className={`${showStats ? "grid grid-cols-1 lg:grid-cols-3 gap-6" : ""} bg-base-100 rounded-box shadow-xl p-6`}
      >
        <div
          className={`flex flex-col ${showStats ? "lg:col-span-2" : ""}`}
        >
          <div className="flex flex-col items-center text-center flex-1">
            <div className="flex flex-col sm:flex-row items-center gap-4 sm:gap-8">
              <img
                src={logoUrl}
                alt={networkName}
                className={`theme-logo ${logoInvertLight ? "theme-logo--invert-light" : ""} h-24 w-24 sm:h-36 sm:w-36`}
              />
              <div className="flex flex-col justify-center">
                <h1 className="hero-title text-3xl sm:text-5xl lg:text-6xl font-black tracking-tight">
                  {networkName}
                </h1>
                {config.network_city && config.network_country && (
                  <p className="text-lg sm:text-2xl opacity-70 mt-2">
                    {config.network_city}, {config.network_country}
                  </p>
                )}
              </div>
            </div>
            <div className="flex-1 flex items-center justify-center w-full">
              <p className="py-6 max-w-[90%] sm:max-w-[70%]">
                {config.network_welcome_text ||
                  t("home.welcome_default", { network_name: networkName })}
              </p>
            </div>
            <div
              className="flex flex-wrap justify-center justify-items-center gap-2
                sm:grid sm:grid-cols-4 min-[1536px]:grid-cols-8
                sm:gap-3 min-[1536px]:gap-2"
            >
              {navItems
                .filter((item) => features[item.feature] !== false)
                .map((item) => (
                  <NavCard
                    key={item.href}
                    href={item.href}
                    icon={item.icon}
                    label={item.label}
                    colorVar={item.colorVar}
                  />
                ))}
            </div>
            {features.pages !== false && customPages.length > 0 && (
              <div className="flex flex-wrap justify-center gap-3 mt-4">
                {customPages.slice(0, 3).map((page) => (
                  <Link
                    key={page.slug}
                    to={page.url}
                    className="btn btn-outline border-base-content/20"
                  >
                    <IconPage className="h-5 w-5 mr-2" />
                    {page.title}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
        {showStats && (
          <div className="flex flex-col gap-4">
            {features.nodes !== false && (
              <StatCard
                icon={<IconNodes className="h-8 w-8" />}
                color={getPageColor("nodes")}
                title={t("entities.nodes")}
                value={stats.total_nodes}
                description={t("home.all_discovered_nodes")}
              />
            )}
            {features.advertisements !== false && (
              <StatCard
                icon={<IconAdvertisements className="h-8 w-8" />}
                color={getPageColor("adverts")}
                title={t("entities.advertisements")}
                value={stats.advertisements_7d}
                description={t("time.last_7_days")}
              />
            )}
            {features.messages !== false && (
              <StatCard
                icon={<IconMessages className="h-8 w-8" />}
                color={getPageColor("messages")}
                title={t("entities.messages")}
                value={stats.messages_7d}
                description={t("time.last_7_days")}
              />
            )}
            {features.packets !== false && (
              <StatCard
                icon={<IconPackets className="h-8 w-8" />}
                color={getPageColor("packets")}
                title={t("entities.packets")}
                value={stats.packets_7d}
                description={t("time.last_7_days")}
              />
            )}
          </div>
        )}
      </div>

      <div
        className={`grid grid-cols-1 md:grid-cols-2 ${showRadioPanel && showMembersPanel && showActivityChart ? "lg:grid-cols-3" : ""} gap-6 mt-6`}
      >
        {showRadioPanel && (
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h2 className="card-title">
                <IconInfo className="h-6 w-6" />
                {t("home.network_info")}
              </h2>
              <div className="mt-2">
                <RadioTiles rc={config.network_radio_config} />
              </div>
            </div>
          </div>
        )}

        {showMembersPanel && (
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h2 className="card-title">
                <IconMembers className="h-6 w-6" />
                {t("entities.members")}
              </h2>
              <div className="grid grid-cols-1 gap-4 mt-2">
                <StatCard
                  icon={<IconAntenna className="h-6 w-6" />}
                  color={getPageColor("members")}
                  title={t("members_page.operators")}
                  value={stats.total_operators ?? 0}
                />
                <StatCard
                  icon={<IconUsers className="h-6 w-6" />}
                  color={getPageColor("members")}
                  title={t("members_page.members")}
                  value={stats.total_members ?? 0}
                />
              </div>
            </div>
          </div>
        )}

        {showActivityChart && (
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h2 className="card-title">
                <IconChart className="h-6 w-6" />
                {t("home.network_activity")}
              </h2>
              <p className="text-sm opacity-70 mb-2">
                {t("time.activity_per_day_last_7_days")}
              </p>
              <ActivityChart
                advertData={showAdvertSeries ? advertActivity : null}
                messageData={showMessageSeries ? messageActivity : null}
              />
            </div>
          </div>
        )}
      </div>
    </>
  );
}
