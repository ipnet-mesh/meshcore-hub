import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router";
import { useTranslation } from "react-i18next";

import { ErrorAlert, Loading } from "@/components/Alerts";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { Markdown } from "@/components/Markdown";
import { useAppConfig } from "@/context/AppConfigContext";
import { apiGet, isAbortError } from "@/utils/api";

interface CustomPageData {
  slug: string;
  title: string;
  content_markdown: string;
}

export function CustomPagePage() {
  const { slug = "" } = useParams();
  const location = useLocation();
  const { t } = useTranslation();
  const config = useAppConfig();

  const [page, setPage] = useState<CustomPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiGet<CustomPageData>(
      `/spa/pages/${encodeURIComponent(slug)}`,
      {},
      { signal: controller.signal },
    )
      .then((data) => {
        setPage(data);
        setLoading(false);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        const message = e instanceof Error ? e.message : "";
        setError(
          message.includes("404")
            ? t("common.page_not_found")
            : message || t("custom_page.failed_to_load"),
        );
        setLoading(false);
      });
    return () => controller.abort();
  }, [slug, t]);

  useEffect(() => {
    if (!page) return;
    const networkName = config.network_name || "MeshCore Network";
    document.title = `${page.title} - ${networkName}`;
  }, [page, config.network_name]);

  useEffect(() => {
    if (!page || !location.hash) return;
    const id = location.hash.slice(1);
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    });
  }, [page, location.hash]);

  if (loading) return <Loading />;
  if (error) return <ErrorAlert message={error} />;
  if (!page) return null;

  return (
    <div className="max-w-4xl mx-auto">
      <Breadcrumbs
        items={[{ label: t("entities.home"), to: "/" }, { label: page.title }]}
      />
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body overflow-x-auto">
          <Markdown>{page.content_markdown}</Markdown>
        </div>
      </div>
    </div>
  );
}
