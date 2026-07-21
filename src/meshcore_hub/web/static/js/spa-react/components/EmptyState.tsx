import type { ReactNode } from "react";

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="text-center py-8 opacity-70">{children}</div>;
}

export function EmptyRow({
  colSpan,
  children,
}: {
  colSpan: number;
  children: ReactNode;
}) {
  return (
    <tr>
      <td colSpan={colSpan} className="text-center py-8 opacity-70">
        {children}
      </td>
    </tr>
  );
}
