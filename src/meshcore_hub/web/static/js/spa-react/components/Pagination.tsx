import { useTranslation } from "react-i18next";
import { Link } from "react-router";

interface PaginationProps {
  page: number;
  totalPages: number;
  basePath: string;
  params?: Record<string, string | string[]>;
}

export function Pagination({
  page,
  totalPages,
  basePath,
  params = {},
}: PaginationProps) {
  const { t } = useTranslation();
  if (totalPages <= 1) return null;

  const queryParts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (k === "page" || v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) {
      v.forEach((item) =>
        queryParts.push(
          `${encodeURIComponent(k)}=${encodeURIComponent(item)}`,
        ),
      );
    } else {
      queryParts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
  }
  const extraQuery = queryParts.length > 0 ? "&" + queryParts.join("&") : "";

  const pageUrl = (p: number) => `${basePath}?page=${p}${extraQuery}`;

  const pageNumbers: React.ReactNode[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (p === page) {
      pageNumbers.push(
        <button key={p} className="join-item btn btn-sm btn-active">
          {p}
        </button>,
      );
    } else if (
      p === 1 ||
      p === totalPages ||
      (p >= page - 2 && p <= page + 2)
    ) {
      pageNumbers.push(
        <Link key={p} to={pageUrl(p)} className="join-item btn btn-sm">
          {p}
        </Link>,
      );
    } else if (p === 2 || p === totalPages - 1) {
      pageNumbers.push(
        <button
          key={p}
          className="join-item btn btn-sm btn-disabled"
          disabled
        >
          ...
        </button>,
      );
    }
  }

  return (
    <div className="flex justify-center mt-6">
      <div className="join">
        {page > 1 ? (
          <Link to={pageUrl(page - 1)} className="join-item btn btn-sm">
            {t("common.previous")}
          </Link>
        ) : (
          <button className="join-item btn btn-sm btn-disabled" disabled>
            {t("common.previous")}
          </button>
        )}
        {pageNumbers}
        {page < totalPages ? (
          <Link to={pageUrl(page + 1)} className="join-item btn btn-sm">
            {t("common.next")}
          </Link>
        ) : (
          <button className="join-item btn btn-sm btn-disabled" disabled>
            {t("common.next")}
          </button>
        )}
      </div>
    </div>
  );
}
