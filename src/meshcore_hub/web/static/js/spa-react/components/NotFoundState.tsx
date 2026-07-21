import type { ReactNode } from "react";

import { IconError } from "@/components/icons";

export function NotFoundState({
  message,
  tone = "error",
}: {
  message: ReactNode;
  tone?: "error" | "warning";
}) {
  return (
    <div role="alert" className={`alert alert-${tone} mb-4`}>
      {tone === "error" && (
        <IconError className="stroke-current shrink-0 h-6 w-6" />
      )}
      <span>{message}</span>
    </div>
  );
}
