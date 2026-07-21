import { useState, useCallback } from "react";
import { useAppConfig } from "@/context/AppConfigContext";

interface UseAutoRefreshReturn {
  paused: boolean;
  toggle: () => void;
  intervalSeconds: number;
  refetchInterval: number | false;
}

export function useAutoRefresh(): UseAutoRefreshReturn {
  const config = useAppConfig();
  const intervalSeconds = config.auto_refresh_seconds || 0;
  const [paused, setPaused] = useState(false);
  const toggle = useCallback(() => setPaused((p) => !p), []);

  const refetchInterval =
    !intervalSeconds || paused ? false : intervalSeconds * 1000;

  return { paused, toggle, intervalSeconds, refetchInterval };
}
