import type { ReactNode } from "react";

export function CountBadge({ children }: { children: ReactNode }) {
  return <span className="badge badge-lg">{children}</span>;
}

export function RoleBadge({ role }: { role: string }) {
  return <span className="badge badge-primary badge-sm">{role}</span>;
}

export function CallsignBadge({ callsign }: { callsign: string }) {
  return <span className="badge badge-neutral badge-sm">{callsign}</span>;
}
