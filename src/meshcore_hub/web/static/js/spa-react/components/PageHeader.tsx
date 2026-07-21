import type { ReactNode } from "react";
import { useAppConfig } from "@/context/AppConfigContext";

export function PageHeader({
  title,
  children,
}: {
  title: ReactNode;
  children?: ReactNode;
}) {
  const config = useAppConfig();
  const tz = config.timezone || "";
  return (
    <div className="flex items-center justify-between mb-6">
      <h1 className="text-3xl font-bold">{title}</h1>
      <div className="flex items-center gap-2">
        {tz && tz !== "UTC" && (
          <span className="text-sm opacity-60">{tz}</span>
        )}
        {children}
      </div>
    </div>
  );
}
