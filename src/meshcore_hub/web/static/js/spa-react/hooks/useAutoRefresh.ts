import { useEffect, useRef, useState, useCallback } from "react";
import { useAppConfig } from "@/context/AppConfigContext";

interface UseAutoRefreshOptions {
  onRefresh: () => Promise<void>;
}

interface UseAutoRefreshReturn {
  paused: boolean;
  toggle: () => void;
  intervalSeconds: number;
}

export function useAutoRefresh({
  onRefresh,
}: UseAutoRefreshOptions): UseAutoRefreshReturn {
  const config = useAppConfig();
  const intervalSeconds = config.auto_refresh_seconds || 0;
  const [paused, setPaused] = useState(false);
  const isPendingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  const toggle = useCallback(() => setPaused((p) => !p), []);

  useEffect(() => {
    if (!intervalSeconds || paused) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    const tick = async () => {
      if (isPendingRef.current) return;
      isPendingRef.current = true;
      try {
        await onRefreshRef.current();
      } catch {
        // handled by caller
      } finally {
        isPendingRef.current = false;
      }
    };

    timerRef.current = setInterval(tick, intervalSeconds * 1000);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [intervalSeconds, paused]);

  return { paused, toggle, intervalSeconds };
}
