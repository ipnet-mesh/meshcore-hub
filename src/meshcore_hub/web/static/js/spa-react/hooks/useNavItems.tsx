import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useAppConfig } from "@/context/AppConfigContext";
import {
  IconAdvertisements,
  IconChannel,
  IconDashboard,
  IconHome,
  IconMap,
  IconMembers,
  IconMessages,
  IconNodes,
  IconPackets,
  IconPage,
  IconPath,
} from "@/components/icons";

export interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
}

export function useNavItems(sizeClass = "h-5 w-5"): NavItem[] {
  const { t } = useTranslation();
  const config = useAppConfig();
  const features = config.features ?? {};
  const customPages = config.custom_pages ?? [];

  const items: NavItem[] = [
    {
      href: "/",
      label: t("entities.home"),
      icon: <IconHome className={sizeClass} />,
      end: true,
    },
  ];

  if (features.dashboard !== false)
    items.push({
      href: "/dashboard",
      label: t("entities.dashboard"),
      icon: <IconDashboard className={`${sizeClass} nav-icon-dashboard`} />,
    });
  if (features.nodes !== false)
    items.push({
      href: "/nodes",
      label: t("entities.nodes"),
      icon: <IconNodes className={`${sizeClass} nav-icon-nodes`} />,
    });
  if (features.advertisements !== false)
    items.push({
      href: "/advertisements",
      label: t("entities.advertisements"),
      icon: <IconAdvertisements className={`${sizeClass} nav-icon-adverts`} />,
    });
  if (features.routes !== false)
    items.push({
      href: "/routes",
      label: t("entities.routes"),
      icon: <IconPath className={`${sizeClass} nav-icon-routes`} />,
    });
  if (features.channels !== false)
    items.push({
      href: "/channels",
      label: t("entities.channels"),
      icon: <IconChannel className={`${sizeClass} nav-icon-channels`} />,
    });
  if (features.messages !== false)
    items.push({
      href: "/messages",
      label: t("entities.messages"),
      icon: <IconMessages className={`${sizeClass} nav-icon-messages`} />,
    });
  if (features.packets !== false)
    items.push({
      href: "/packets",
      label: t("entities.packets"),
      icon: <IconPackets className={`${sizeClass} nav-icon-packets`} />,
    });
  if (features.map !== false)
    items.push({
      href: "/map",
      label: t("entities.map"),
      icon: <IconMap className={`${sizeClass} nav-icon-map`} />,
    });
  if (features.members !== false)
    items.push({
      href: "/members",
      label: t("entities.members"),
      icon: <IconMembers className={`${sizeClass} nav-icon-members`} />,
    });

  if (features.pages !== false) {
    for (const page of customPages) {
      items.push({
        href: page.url,
        label: page.title,
        icon: <IconPage className={sizeClass} />,
      });
    }
  }

  return items;
}
