export interface ReceptionLike {
  observed_by?: string | null;
}

export function groupByObserver<T extends ReceptionLike>(
  receptions: T[],
): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const r of receptions) {
    const key = r.observed_by || "__unknown__";
    const list = groups.get(key);
    if (list) {
      list.push(r);
    } else {
      groups.set(key, [r]);
    }
  }
  return groups;
}
