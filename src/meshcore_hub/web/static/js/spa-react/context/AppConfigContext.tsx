import { createContext, useContext, type ReactNode } from "react";
import type { AppConfig } from "@/types/config";

const AppConfigContext = createContext<AppConfig | null>(null);

export function AppConfigProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: ReactNode;
}) {
  return (
    <AppConfigContext.Provider value={config}>
      {children}
    </AppConfigContext.Provider>
  );
}

export function useAppConfig(): AppConfig {
  const ctx = useContext(AppConfigContext);
  if (!ctx) throw new Error("useAppConfig must be used within AppConfigProvider");
  return ctx;
}

export function useFeatures(): Record<string, boolean> {
  return useAppConfig().features;
}

export function hasRole(roleName: string): boolean {
  const config = window.__APP_CONFIG__;
  if (!config?.oidc_enabled) return false;
  const actualRole = config.role_names?.[roleName] ?? roleName;
  return (config.roles ?? []).includes(actualRole);
}

export function getChannelLabelsMap(
  config: AppConfig = window.__APP_CONFIG__,
): Map<number, string> {
  return new Map(
    Object.entries(config.channel_labels ?? {})
      .map(([idx, label]) => [
        parseInt(idx, 10),
        typeof label === "string" ? label.trim() : "",
      ])
      .filter(
        ([idx, label]) => Number.isInteger(idx) && (label as string).length > 0,
      ) as [number, string][],
  );
}

export function resolveChannelLabel(
  channelIdx: number | string,
  channelLabels: Map<number, string> = getChannelLabelsMap(),
): string | null {
  const parsed = parseInt(String(channelIdx), 10);
  if (!Number.isInteger(parsed)) return null;
  return channelLabels.get(parsed) ?? null;
}
