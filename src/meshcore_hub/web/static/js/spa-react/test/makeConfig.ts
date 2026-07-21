import type { AppConfig } from "@/types/config";

export function makeConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    network_name: "TestNet",
    features: {},
    custom_pages: [],
    logo_url: "/logo.svg",
    version: "1.0.0",
    timezone: "UTC",
    timezone_iana: "UTC",
    default_theme: "dark",
    locale: "en",
    datetime_locale: "en-US",
    auto_refresh_seconds: 30,
    channel_labels: {},
    logo_invert_light: false,
    debug: false,
    locale_version: "",
    system_maintenance: false,
    spam_score_threshold: 0,
    oidc_enabled: false,
    user: null,
    roles: [],
    role_names: {},
    ...overrides,
  };
}
