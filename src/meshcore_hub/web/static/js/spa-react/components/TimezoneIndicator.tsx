import { useAppConfig } from "@/context/AppConfigContext";

export function TimezoneIndicator() {
  const config = useAppConfig();
  const tz = config.timezone || "UTC";
  return <span className="text-xs opacity-50 ml-2">({tz})</span>;
}
