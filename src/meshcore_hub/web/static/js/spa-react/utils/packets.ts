export interface ChannelItem {
  name: string;
  channel_hash: string;
}

export function buildChannelNames(items: ChannelItem[]): Map<number, string> {
  const names = new Map<number, string>();
  for (const c of items) {
    const idx = parseInt(c.channel_hash, 16);
    if (!Number.isNaN(idx)) names.set(idx, c.name);
  }
  return names;
}

export function isNotFoundError(e: unknown): boolean {
  return e instanceof Error && e.message.includes("404");
}
