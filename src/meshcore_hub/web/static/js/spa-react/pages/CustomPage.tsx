import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";

import { ErrorAlert, Loading } from "@/components/Alerts";
import { useAppConfig } from "@/context/AppConfigContext";
import { apiGet, isAbortError } from "@/utils/api";

interface CustomPageData {
  slug: string;
  title: string;
  content_html: string;
}

export function CustomPagePage() {
  const { slug = "" } = useParams();
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

  if (loading) return <Loading />;
  if (error) return <ErrorAlert message={error} />;
  if (!page) return null;

  return (
    <div className="max-w-4xl mx-auto">
      <div className="card bg-base-100 shadow-xl">
        <div
          className="card-body prose prose-lg max-w-none overflow-x-auto"
          dangerouslySetInnerHTML={{ __html: page.content_html }}
        />
      </div>
    </div>
  );
}
