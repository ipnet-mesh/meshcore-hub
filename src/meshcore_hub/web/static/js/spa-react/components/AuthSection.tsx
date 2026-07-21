import { useTranslation } from "react-i18next";
import { useAppConfig } from "@/context/AppConfigContext";
import { IconUser, IconLogout } from "@/components/icons";

export function AuthSection() {
  const { t } = useTranslation();
  const config = useAppConfig();

  if (!config.oidc_enabled) return null;

  const user = config.user;
  if (!user) {
    return (
      <a href="/auth/login" className="btn btn-sm btn-outline">
        {t("auth.login")}
      </a>
    );
  }

  const displayName = user.name || user.email || "User";
  const initials = displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const roleBadges = (config.roles ?? []).map((r) => {
    const key = `auth.role_${r}`;
    const label = t(key);
    const name = label !== key ? label : r;
    return (
      <span key={r} className="badge badge-primary badge-xs">
        {name}
      </span>
    );
  });

  return (
    <div className="dropdown dropdown-end">
      <div
        tabIndex={0}
        role="button"
        className="btn btn-ghost btn-circle btn-sm avatar"
      >
        {user.picture ? (
          <img
            src={user.picture}
            alt={displayName}
            className="w-8 h-8 rounded-full"
          />
        ) : (
          <span className="text-sm font-bold">{initials}</span>
        )}
      </div>
      <ul
        tabIndex={0}
        className="dropdown-content menu z-50 p-2 shadow-sm bg-base-100 rounded-box w-56 mt-3"
      >
        <li className="menu-title">
          <div className="flex flex-col gap-1">
            <span className="font-medium">{displayName}</span>
            {config.debug && user.sub && (
              <span className="text-xs opacity-40 font-mono">{user.sub}</span>
            )}
            {roleBadges.length > 0 && (
              <div className="flex flex-wrap gap-1">{roleBadges}</div>
            )}
          </div>
        </li>
        <hr className="my-1 opacity-20" />
        <li>
          <a href="/profile">
            <IconUser className="h-5 w-5" /> {t("links.profile")}
          </a>
        </li>
        <li>
          <a href="/auth/logout">
            <IconLogout className="h-5 w-5" /> {t("auth.logout")}
          </a>
        </li>
      </ul>
    </div>
  );
}
