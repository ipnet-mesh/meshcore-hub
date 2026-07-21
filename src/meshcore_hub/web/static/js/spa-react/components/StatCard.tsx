import type { ReactNode } from "react";
import { formatNumber } from "@/utils/format";

interface StatCardProps {
  icon: ReactNode;
  color: string;
  title: string;
  value: number | string;
  description?: string;
}

export function StatCard({
  icon,
  color,
  title,
  value,
  description,
}: StatCardProps) {
  return (
    <div
      className="stat bg-base-200 rounded-box shadow-sm panel-accent !py-2"
      style={{ "--panel-color": color } as React.CSSProperties}
    >
      <div className="stat-figure" style={{ color }}>
        {icon}
      </div>
      <div className="stat-title">{title}</div>
      <div className="stat-value text-3xl">{formatNumber(value)}</div>
      {description && <div className="stat-desc">{description}</div>}
    </div>
  );
}
