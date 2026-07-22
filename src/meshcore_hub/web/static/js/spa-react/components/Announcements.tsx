import { useState } from "react";

import { Markdown } from "@/components/Markdown";
import { useAppConfig } from "@/context/AppConfigContext";

export function Announcements() {
  const config = useAppConfig();
  const [dismissed, setDismissed] = useState(() => {
    try {
      return sessionStorage.getItem("flash-banner-dismissed") === "1";
    } catch {
      return false;
    }
  });

  const system = config.system_announcement;
  const network = config.network_announcement;

  const dismiss = () => {
    setDismissed(true);
    try {
      sessionStorage.setItem("flash-banner-dismissed", "1");
    } catch {
      // ignore
    }
  };

  if (!system && (!network || dismissed)) return null;

  return (
    <>
      {system && (
        <div
          id="system-banner"
          className="alert alert-error rounded-none py-2 px-4 text-center text-sm"
        >
          <Markdown className="flash-banner-content">
            {system}
          </Markdown>
        </div>
      )}
      {network && !dismissed && (
        <div
          id="flash-banner"
          className="alert alert-warning rounded-none py-2 px-4 text-center text-sm"
        >
          <Markdown className="flash-banner-content">
            {network}
          </Markdown>
          <button
            aria-label="Dismiss"
            onClick={dismiss}
            className="btn btn-ghost btn-xs"
          >
            &times;
          </button>
        </div>
      )}
    </>
  );
}
