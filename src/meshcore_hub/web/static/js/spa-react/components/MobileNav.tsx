import { useTranslation } from "react-i18next";
import { useAppConfig } from "@/context/AppConfigContext";
import {
  IconHome,
  IconDashboard,
  IconNodes,
  IconAdvertisements,
  IconMessages,
  IconPackets,
  IconMap,
  IconMembers,
  IconPage,
  IconChannel,
  IconPath,
} from "@/components/icons";

export function MobileNav() {
  const { t } = useTranslation();
  const config = useAppConfig();
  const features = config.features ?? {};
  const customPages = config.custom_pages ?? [];

  const items: { href: string; icon: React.ReactNode; label: string }[] = [
    { href: "/", icon: <IconHome className="h-5 w-5" />, label: t("entities.home") },
  ];

  if (features.dashboard !== false)
    items.push({ href: "/dashboard", icon: <IconDashboard className="h-5 w-5 nav-icon-dashboard" />, label: t("entities.dashboard") });
  if (features.nodes !== false)
    items.push({ href: "/nodes", icon: <IconNodes className="h-5 w-5 nav-icon-nodes" />, label: t("entities.nodes") });
  if (features.advertisements !== false)
    items.push({ href: "/advertisements", icon: <IconAdvertisements className="h-5 w-5 nav-icon-adverts" />, label: t("entities.advertisements") });
  if (features.routes !== false)
    items.push({ href: "/routes", icon: <IconPath className="h-5 w-5 nav-icon-routes" />, label: t("entities.routes") });
  if (features.channels !== false)
    items.push({ href: "/channels", icon: <IconChannel className="h-5 w-5 nav-icon-channels" />, label: t("entities.channels") });
  if (features.messages !== false)
    items.push({ href: "/messages", icon: <IconMessages className="h-5 w-5 nav-icon-messages" />, label: t("entities.messages") });
  if (features.packets !== false)
    items.push({ href: "/packets", icon: <IconPackets className="h-5 w-5 nav-icon-packets" />, label: t("entities.packets") });
  if (features.map !== false)
    items.push({ href: "/map", icon: <IconMap className="h-5 w-5 nav-icon-map" />, label: t("entities.map") });
  if (features.members !== false)
    items.push({ href: "/members", icon: <IconMembers className="h-5 w-5 nav-icon-members" />, label: t("entities.members") });

  if (features.pages !== false) {
    for (const page of customPages) {
      items.push({ href: page.url, icon: <IconPage className="h-5 w-5" />, label: page.title });
    }
  }

  return (
    <>
      {items.map((item) => (
        <li key={item.href}>
          <a href={item.href} data-nav-link>
            {item.icon} {item.label}
          </a>
        </li>
      ))}
    </>
  );
}
