import { useEffect, useRef } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router";

interface LitBridgeProps {
  loader: () => Promise<{
    render: (
      container: HTMLElement,
      params: Record<string, unknown>,
      router: { navigate: (url: string, replace?: boolean) => void },
    ) => Promise<(() => void) | void>;
  }>;
}

export function LitBridge({ loader }: LitBridgeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const params = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const cleanupRef = useRef<(() => void) | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const query: Record<string, string | string[]> = {};
    for (const [k, v] of searchParams.entries()) {
      if (k in query) {
        const existing = query[k];
        query[k] = Array.isArray(existing) ? [...existing, v] : [existing, v];
      } else {
        query[k] = v;
      }
    }

    const routerAdapter = {
      navigate(url: string, replace = false) {
        navigate(url, { replace });
      },
    };

    let cancelled = false;

    loader()
      .then((module) => {
        if (cancelled) return;
        return module.render(
          container,
          { ...params, query, signal: controller.signal },
          routerAdapter,
        );
      })
      .then((cleanup) => {
        if (cancelled) {
          if (typeof cleanup === "function") cleanup();
          return;
        }
        if (typeof cleanup === "function") {
          cleanupRef.current = cleanup;
        }
      })
      .catch((e) => {
        if (e?.name === "AbortError") return;
        console.error("LitBridge page load error:", e);
      });

    return () => {
      cancelled = true;
      controller.abort();
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [loader, params, searchParams, navigate]);

  return <div ref={containerRef} />;
}
