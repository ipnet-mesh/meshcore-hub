import { useTranslation } from "react-i18next";
import { usePageTitle } from "@/hooks/usePageTitle";

export function Maintenance() {
  const { t } = useTranslation();
  usePageTitle();

  return (
    <div className="hero min-h-[60vh]">
      <div className="hero-content text-center">
        <div className="max-w-md">
          <div className="text-7xl mb-4">🔧</div>
          <h1 className="text-4xl font-bold mb-4">
            {t("maintenance.title")}
          </h1>
          <p className="text-lg opacity-70">{t("maintenance.description")}</p>
        </div>
      </div>
    </div>
  );
}
