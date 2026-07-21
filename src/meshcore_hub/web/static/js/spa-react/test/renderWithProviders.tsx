import type { ReactElement, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { render, type RenderOptions } from "@testing-library/react";

import { AppConfigProvider } from "@/context/AppConfigContext";
import { makeConfig } from "@/test/makeConfig";
import type { AppConfig } from "@/types/config";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

interface ProviderOptions {
  config?: AppConfig;
  client?: QueryClient;
  route?: string;
  renderOptions?: Omit<RenderOptions, "wrapper">;
}

export function renderWithProviders(
  ui: ReactElement,
  options: ProviderOptions = {},
) {
  const {
    config = makeConfig(),
    client = createTestQueryClient(),
    route = "/",
    renderOptions,
  } = options;

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <AppConfigProvider config={config}>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </AppConfigProvider>
      </QueryClientProvider>
    );
  }

  return { client, ...render(ui, { wrapper: Wrapper, ...renderOptions }) };
}
