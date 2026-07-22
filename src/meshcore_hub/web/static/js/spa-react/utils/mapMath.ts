export interface LatLng {
  lat: number;
  lon: number;
}

export interface MapNodeLike {
  lat: number;
  lon: number;
  adv_type?: string | null;
}

export function getDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export function getNodesWithinRadius<T extends MapNodeLike>(
  nodes: T[],
  anchorLat: number,
  anchorLon: number,
  radiusKm: number,
): T[] {
  return nodes.filter(
    (n) => getDistanceKm(anchorLat, anchorLon, n.lat, n.lon) <= radiusKm,
  );
}

export function getAnchorPoint<T extends MapNodeLike>(
  nodes: T[],
  adoptedCenter: LatLng | null,
): LatLng {
  if (adoptedCenter) return adoptedCenter;
  if (nodes.length === 0) return { lat: 0, lon: 0 };
  return {
    lat: nodes.reduce((sum, n) => sum + n.lat, 0) / nodes.length,
    lon: nodes.reduce((sum, n) => sum + n.lon, 0) / nodes.length,
  };
}

export function normalizeType(type: string | null): string | null {
  return type ? type.toLowerCase() : null;
}
