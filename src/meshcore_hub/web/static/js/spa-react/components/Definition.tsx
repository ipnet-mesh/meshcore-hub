import type { ReactNode } from "react";

export function DefinitionField({
  label,
  children,
}: {
  label: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 py-2 border-b border-base-200">
      <span className="text-xs uppercase opacity-60">{label}</span>
      <span className="text-sm">{children}</span>
    </div>
  );
}

export function DefinitionGrid({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={className ?? "grid grid-cols-1 md:grid-cols-2 gap-x-8"}>
      {children}
    </div>
  );
}
