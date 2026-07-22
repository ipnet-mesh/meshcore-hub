import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
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
        <Link to={basePath} className="btn btn-ghost btn-sm">
          {clearLabel || t("common.clear")}
        </Link>
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

export function autoSubmit(
  e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>,
) {
  e.currentTarget.form?.requestSubmit();
}

export function submitOnEnter(e: React.KeyboardEvent<HTMLInputElement>) {
  if (e.key === "Enter") e.currentTarget.form?.requestSubmit();
}

export function FilterField({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`.trim()}>
      <label className="flex items-center py-1">
        <span className="opacity-80 text-sm">{label}</span>
      </label>
      {children}
    </div>
  );
}

interface FilterSelectOption {
  value: string;
  label: string;
}

interface FilterSelectProps {
  name: string;
  options: FilterSelectOption[];
  defaultValue?: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  className?: string;
}

export function FilterSelect({
  name,
  options,
  defaultValue,
  onChange,
  className,
}: FilterSelectProps) {
  return (
    <select
      name={name}
      className={`select select-sm ${className ?? ""}`.trim()}
      defaultValue={defaultValue}
      onChange={onChange}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export interface OperatorOption {
  id: string;
  name?: string | null;
  callsign?: string | null;
  user_id?: string;
}

interface OperatorSelectProps {
  name?: string;
  profiles: OperatorOption[];
  value?: string;
  defaultValue?: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  className?: string;
}

export function OperatorSelect({
  name,
  profiles,
  value,
  defaultValue,
  onChange,
  className,
}: OperatorSelectProps) {
  const { t } = useTranslation();
  const controlled = value !== undefined;
  return (
    <select
      name={name}
      className={`select select-sm ${className ?? ""}`.trim()}
      {...(controlled ? { value } : { defaultValue })}
      onChange={onChange}
    >
      <option value="">{t("common.all_operators")}</option>
      {profiles.map((p) => (
        <option key={p.id} value={p.id}>
          {p.callsign
            ? `${p.name} (${p.callsign})`
            : p.name || p.callsign || p.user_id || p.id}
        </option>
      ))}
    </select>
  );
}
