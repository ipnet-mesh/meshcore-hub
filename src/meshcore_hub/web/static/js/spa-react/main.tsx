import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppConfigProvider } from "@/context/AppConfigContext";
import { initI18n } from "@/i18n";
import { App } from "@/App";
import { AuthSection } from "@/components/AuthSection";
import { MobileNav } from "@/components/MobileNav";
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

  const wrap = (ui: React.ReactNode) => (
    <StrictMode>
      <AppConfigProvider config={config}>{ui}</AppConfigProvider>
    </StrictMode>
  );

  createRoot(appContainer).render(wrap(<App />));

  const authContainer = document.getElementById("auth-section");
  if (authContainer) {
    createRoot(authContainer).render(wrap(<AuthSection />));
  }

  const mobileNavContainer = document.getElementById("mobile-nav");
  if (mobileNavContainer) {
    createRoot(mobileNavContainer).render(wrap(<MobileNav />));
  }
}

bootstrap();
