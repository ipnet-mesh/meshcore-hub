import type { QueryClient } from "@tanstack/react-query";

export const qk = {
  nodes: {
    all: ["nodes"] as const,
    list: (params: unknown) => ["nodes", "list", params] as const,
    detail: (publicKey: string) => ["nodes", "detail", publicKey] as const,
    prefix: (prefix: string) => ["nodes", "prefix", prefix] as const,
  },
  messages: {
    all: ["messages"] as const,
    list: (params: unknown) => ["messages", "list", params] as const,
  },
  channels: {
    all: ["channels"] as const,
    list: (params: unknown) => ["channels", "list", params] as const,
  },
  routes: {
    all: ["routes"] as const,
    list: (params: unknown = {}) => ["routes", "list", params] as const,
    detail: (id: string) => ["routes", "detail", id] as const,
    history: (id: string, days: number) =>
      ["routes", "history", id, days] as const,
  },
  advertisements: {
    all: ["advertisements"] as const,
    list: (params: unknown) => ["advertisements", "list", params] as const,
  },
  profiles: {
    all: ["profiles"] as const,
    list: (params: unknown) => ["profiles", "list", params] as const,
    detail: (id: string) => ["profiles", "detail", id] as const,
    me: () => ["profiles", "me"] as const,
  },
  dashboard: {
    all: ["dashboard"] as const,
    stats: () => ["dashboard", "stats"] as const,
    series: (kind: string, params: unknown) =>
      ["dashboard", "series", kind, params] as const,
    recent: (params: unknown) => ["dashboard", "recent", params] as const,
    routesOverview: () => ["dashboard", "routes-overview"] as const,
  },
  packets: {
    all: ["packets"] as const,
    groups: (params: unknown) => ["packets", "groups", params] as const,
    group: (hash: string) => ["packets", "group", hash] as const,
    detail: (id: string) => ["packets", "detail", id] as const,
  },
  map: {
    all: ["map"] as const,
    data: (params: unknown) => ["map", "data", params] as const,
  },
};

export const invalidate = {
  channels: (qc: QueryClient) =>
    qc.invalidateQueries({ queryKey: qk.channels.all }),
  routes: (qc: QueryClient) => {
    qc.invalidateQueries({ queryKey: qk.routes.all });
    qc.invalidateQueries({ queryKey: qk.dashboard.all });
  },
  profiles: (qc: QueryClient) => {
    qc.invalidateQueries({ queryKey: qk.profiles.all });
    qc.invalidateQueries({ queryKey: qk.dashboard.all });
  },
  nodeTags: (qc: QueryClient) => {
    qc.invalidateQueries({ queryKey: qk.nodes.all });
    qc.invalidateQueries({ queryKey: qk.messages.all });
    qc.invalidateQueries({ queryKey: qk.advertisements.all });
    qc.invalidateQueries({ queryKey: qk.dashboard.all });
  },
  adoptions: (qc: QueryClient) => {
    qc.invalidateQueries({ queryKey: qk.nodes.all });
    qc.invalidateQueries({ queryKey: qk.profiles.all });
    qc.invalidateQueries({ queryKey: qk.advertisements.all });
    qc.invalidateQueries({ queryKey: qk.dashboard.all });
  },
};
