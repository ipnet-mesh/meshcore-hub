import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

let initialized = false;

export async function initI18n(): Promise<typeof i18n> {
  if (initialized) return i18n;

  const config = window.__APP_CONFIG__;
  const storedLocale = localStorage.getItem("meshcore-locale");
  const locale = storedLocale || config?.locale || "en";
  const version = config?.locale_version || "";

  let resources: Record<string, { translation: Record<string, unknown> }> = {};
  try {
    const res = await fetch(
      `/static/locales/${locale}.json${version ? "?v=" + version : ""}`,
    );
    if (res.ok) {
      const data = await res.json();
      resources = { [locale]: { translation: data } };
    }
  } catch (e) {
    console.warn(`Failed to load locale '${locale}':`, e);
  }

  await i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources,
      lng: locale,
      fallbackLng: "en",
      interpolation: {
        escapeValue: false,
        prefix: "{{",
        suffix: "}}",
      },
      detection: {
        order: ["localStorage", "navigator"],
        lookupLocalStorage: "meshcore-locale",
        caches: ["localStorage"],
      },
      react: {
        useSuspense: false,
      },
    });

  window.t = (key: string, params?: Record<string, unknown>) =>
    i18n.t(key, params ?? {});

  initialized = true;
  return i18n;
}

export { i18n };
