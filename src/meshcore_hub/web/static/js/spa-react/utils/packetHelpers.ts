import type { ChannelItem } from "@/utils/packets";

export interface ChannelEntry {
  name: string;
  idx: number;
}

export interface PacketGroupItemLike {
  packet_hash?: string | null;
  receptions?: { packet_id: string }[];
}

export function buildChannelList(items: ChannelItem[]): ChannelEntry[] {
  return items
    .map((c) => ({ name: c.name, idx: parseInt(c.channel_hash, 16) }))
    .filter((c) => !Number.isNaN(c.idx));
}

export function packetUrl(p: PacketGroupItemLike): string {
  if (p.packet_hash) return `/packets/hash/${p.packet_hash}`;
  if (p.receptions && p.receptions.length > 0)
    return `/packets/${p.receptions[0].packet_id}`;
  return "/packets";
}
