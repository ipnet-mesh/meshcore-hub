export interface RadioConfigDisplay {
  profile?: string;
  frequency?: string;
  bandwidth?: string;
  spreading_factor?: string;
  coding_rate?: string;
  tx_power?: string;
}

export interface CustomPage {
  slug: string;
  title: string;
  url: string;
  menu_order: number;
}

export interface OidcUser {
  sub: string;
  name?: string;
  email?: string;
  picture?: string;
}

export interface AppConfig {
  network_name: string;
  network_city?: string;
  network_country?: string;
  network_radio_config?: RadioConfigDisplay;
  network_contact_email?: string;
  network_contact_discord?: string;
  network_contact_github?: string;
  network_contact_youtube?: string;
  network_welcome_text?: string;
  features: Record<string, boolean>;
  custom_pages: CustomPage[];
  logo_url: string;
  version: string;
  timezone: string;
  timezone_iana: string;
  default_theme: string;
  locale: string;
  datetime_locale: string;
  auto_refresh_seconds: number;
  channel_labels: Record<string, string>;
  logo_invert_light: boolean;
  debug: boolean;
  locale_version: string;
  system_maintenance: boolean;
  spam_score_threshold: number;
  oidc_enabled: boolean;
  user: OidcUser | null;
  roles: string[];
  role_names: Record<string, string>;
  system_announcement?: string | null;
  network_announcement?: string | null;
}

declare global {
  interface Window {
    __APP_CONFIG__: AppConfig;
    t: (key: string, params?: Record<string, unknown>) => string;
  }
}

export {};
