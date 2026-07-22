import { useEffect } from "react";
import { useAppConfig } from "@/context/AppConfigContext";

const titleMap: Record<string, string> = {};

export function usePageTitle(entityKey?: string) {
  const config = useAppConfig();
  const networkName = config.network_name || "MeshCore Network";

  useEffect(() => {
    if (entityKey) {
      const entity = window.t(entityKey);
      document.title = `${entity} - ${networkName}`;
    } else {
      document.title = networkName;
    }
  }, [entityKey, networkName]);
}
