import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { IconHome, IconNodes } from "@/components/icons";
import { usePageTitle } from "@/hooks/usePageTitle";

export function NotFound() {
  const { t } = useTranslation();
  usePageTitle();

  return (
    <div className="hero min-h-[60vh]">
      <div className="hero-content text-center">
        <div className="max-w-md">
          <div className="text-9xl font-bold text-primary opacity-20">404</div>
          <h1 className="text-4xl font-bold -mt-8">
            {t("common.page_not_found")}
          </h1>
          <p className="py-6 opacity-70">{t("not_found.description")}</p>
          <div className="flex gap-4 justify-center">
            <Link to="/" className="btn btn-primary">
              <IconHome className="h-5 w-5 mr-2" />
              {t("common.go_home")}
            </Link>
            <Link to="/nodes" className="btn btn-outline">
              <IconNodes className="h-5 w-5 mr-2" />
              {t("common.view_entity", { entity: t("entities.nodes") })}
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
