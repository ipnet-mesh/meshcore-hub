import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppConfigProvider } from "@/context/AppConfigContext";
import { initI18n } from "@/i18n";
import { App } from "@/App";
import type { AppConfig } from "@/types/config";

async function bootstrap() {
  await initI18n();

  const config: AppConfig = window.__APP_CONFIG__;

  try {
    localStorage.removeItem("meshcore-observers-disabled");
  } catch {
    // ignore
  }

  const appContainer = document.getElementById("app");
  if (!appContainer) return;

  createRoot(appContainer).render(
    <StrictMode>
      <AppConfigProvider config={config}>
        <App />
      </AppConfigProvider>
    </StrictMode>,
  );
}

bootstrap();
