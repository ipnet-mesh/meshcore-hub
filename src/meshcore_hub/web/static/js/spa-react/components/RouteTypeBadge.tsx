export function RouteTypeBadge({ routeType }: { routeType: string | null }) {
  if (!routeType) return null;
  if (routeType === "flood" || routeType === "transport_flood") {
    return (
      <span className="badge badge-sm badge-info">
        {routeType === "flood" ? "Flood" : "Relay"}
      </span>
    );
  }
  if (routeType === "direct" || routeType === "transport_direct") {
    return (
      <span className="badge badge-sm badge-success">
        {routeType === "direct" ? "Zero-hop" : "Direct relay"}
      </span>
    );
  }
  return null;
}
