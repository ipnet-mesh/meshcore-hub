import { useTranslation } from "react-i18next";

import { useAppConfig } from "@/context/AppConfigContext";

export function Footer() {
  const config = useAppConfig();
  const { t } = useTranslation();

  const networkName = config.network_name || "MeshCore Network";
  const hasLocale = Boolean(config.network_city && config.network_country);

  return (
    <footer className="footer p-4 bg-base-100 text-base-content mt-auto">
      <div className="flex flex-col items-center gap-1 order-2 lg:order-1">
        <a
          href="https://meshcore.io/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:opacity-80 transition-opacity flex mb-1"
        >
          <img
            src="/static/img/meshcore.svg"
            alt="MeshCore"
            className="theme-logo theme-logo--invert-light h-4"
          />
        </a>
        <span className="text-xs opacity-50">{t("footer.tagline")}</span>
        <p className="text-sm opacity-70">
          <a
            href="https://meshcore.io/"
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover"
          >
            {t("links.website")}
          </a>
          <span> | </span>
          <a
            href="https://github.com/meshcore-dev/MeshCore"
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover"
          >
            {t("links.github")}
          </a>
        </p>
      </div>

      <div className="flex flex-col items-center gap-1 order-1 lg:order-2">
        <p>
          {networkName}
          {hasLocale ? ` | ${config.network_city}, ${config.network_country}` : ""}
        </p>
        <p className="text-xs opacity-50">
          {t("footer.powered_by")}{" "}
          <a
            href="https://github.com/ipnet-mesh/meshcore-hub"
            target="_blank"
            rel="noopener noreferrer"
            className="link link-hover"
          >
            MeshCore Hub
          </a>{" "}
          {config.version}
        </p>
        <p className="text-sm opacity-70">
          {config.network_contact_email && (
            <a href={`mailto:${config.network_contact_email}`} className="link link-hover">
              {config.network_contact_email}
            </a>
          )}
          {config.network_contact_email && config.network_contact_discord && " | "}
          {config.network_contact_discord && (
            <a
              href={config.network_contact_discord}
              target="_blank"
              rel="noopener noreferrer"
              className="link link-hover"
            >
              {t("links.discord")}
            </a>
          )}
          {(config.network_contact_email || config.network_contact_discord) &&
            config.network_contact_github &&
            " | "}
          {config.network_contact_github && (
            <a
              href={config.network_contact_github}
              target="_blank"
              rel="noopener noreferrer"
              className="link link-hover"
            >
              {t("links.github")}
            </a>
          )}
          {(config.network_contact_email ||
            config.network_contact_discord ||
            config.network_contact_github) &&
            config.network_contact_youtube &&
            " | "}
          {config.network_contact_youtube && (
            <a
              href={config.network_contact_youtube}
              target="_blank"
              rel="noopener noreferrer"
              className="link link-hover"
            >
              {t("links.youtube")}
            </a>
          )}
        </p>
      </div>
    </footer>
  );
}
