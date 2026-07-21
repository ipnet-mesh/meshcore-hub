import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { IconFilter } from "@/components/icons";

interface FilterFormProps {
  basePath: string;
  children: React.ReactNode;
  submitLabel?: string;
  clearLabel?: string;
}

export function FilterForm({
  basePath,
  children,
  submitLabel,
  clearLabel,
}: FilterFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const params = new URLSearchParams();
    const keys = new Set(formData.keys());
    for (const k of keys) {
      for (const v of formData.getAll(k)) {
        if (v) params.append(k, v as string);
      }
    }
    const queryStr = params.toString();
    navigate(queryStr ? `${basePath}?${queryStr}` : basePath);
  };

  return (
    <form
      method="GET"
      action={basePath}
      className="flex flex-col gap-4"
      onSubmit={handleSubmit}
    >
      <div className="flex gap-4 flex-wrap items-start">{children}</div>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-primary btn-sm">
          {submitLabel || t("common.filter")}
        </button>
        <a href={basePath} className="btn btn-ghost btn-sm">
          {clearLabel || t("common.clear")}
        </a>
      </div>
    </form>
  );
}

interface FilterToggleProps {
  open: boolean;
  onChange: () => void;
}

export function FilterToggle({ open, onChange }: FilterToggleProps) {
  const { t } = useTranslation();
  return (
    <label className="label cursor-pointer gap-2" title={t("common.filters")}>
      <span className="text-sm opacity-80 flex items-center gap-1">
        <IconFilter className="w-4 h-4" /> {t("common.filters")}
      </span>
      <input
        type="checkbox"
        id="filter-toggle"
        className="toggle toggle-sm toggle-primary"
        checked={open}
        onChange={onChange}
      />
    </label>
  );
}
