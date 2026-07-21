import type { ReactNode } from "react";

export function SectionGroup({
  title,
  className,
  children,
}: {
  title: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <>
      <h2 className="text-lg font-semibold mt-6 mb-3 opacity-70">{title}</h2>
      <div
        className={
          className ?? "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        }
      >
        {children}
      </div>
    </>
  );
}
