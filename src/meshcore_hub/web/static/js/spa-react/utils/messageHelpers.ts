import { resolveChannelLabel } from "@/context/AppConfigContext";

export interface ObserverInfo {
  public_key?: string | null;
  node_id?: string | null;
  observed_at?: string | null;
  snr?: number | null;
}

export interface Message {
  message_type: string;
  text: string;
  channel_idx?: number | null;
  channel_name?: string | null;
  signature?: string | null;
  pubkey_prefix?: string | null;
  sender_name?: string | null;
  sender_tag_name?: string | null;
  observed_by?: string | null;
  observer_name?: string | null;
  observer_tag_name?: string | null;
  received_at: string;
  packet_hash?: string | null;
  spam_score?: number | null;
  observers?: ObserverInfo[];
}

export function parseSenderFromText(text: string | null): {
  sender: string | null;
  text: string;
} {
  if (!text || typeof text !== "string") {
    return { sender: null, text: text || "-" };
  }
  const patterns = [
    /^\s*ack\s+@\[(.+?)\]\s*:\s*([\s\S]+)$/i,
    /^\s*@\[(.+?)\]\s*:\s*([\s\S]+)$/i,
    /^\s*ack\s+([^:|\n]{1,80})\s*:\s*([\s\S]+)$/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) continue;
    const sender = (match[1] || "").trim();
    const remaining = (match[2] || "").trim();
    if (!sender) continue;
    return { sender, text: remaining || text };
  }
  return { sender: null, text };
}

export function collapseNewlines(text: string | null): string | null {
  if (!text || typeof text !== "string") return text;
  return text.replace(/\s*\n\s*/g, " ");
}

export function channelInfo(
  msg: Message,
  channelLabels: Map<number, string>,
  fallbackLabel: string,
): { label: string | null; text: string } {
  if (msg.message_type !== "channel") {
    return { label: null, text: msg.text || "-" };
  }
  const rawText = msg.text || "";
  const match = rawText.match(/^\[([^\]]+)\]\s+([\s\S]*)$/);
  if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
    const knownLabel = resolveChannelLabel(msg.channel_idx, channelLabels);
    if (knownLabel) {
      return {
        label: knownLabel,
        text: match ? match[2] || "-" : rawText || "-",
      };
    }
  }
  if (msg.channel_name) {
    return { label: msg.channel_name, text: msg.text || "-" };
  }
  if (match) {
    return { label: match[1], text: match[2] || "-" };
  }
  if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
    const knownLabel = resolveChannelLabel(msg.channel_idx, channelLabels);
    return { label: knownLabel || `Ch ${msg.channel_idx}`, text: rawText || "-" };
  }
  return { label: fallbackLabel, text: rawText || "-" };
}

export function messageTextWithSender(msg: Message, text: string): string {
  const parsed = parseSenderFromText(text || "-");
  const explicitSender =
    msg.sender_tag_name ||
    msg.sender_name ||
    (msg.pubkey_prefix || "").slice(0, 12) ||
    null;
  const sender = explicitSender || parsed.sender;
  const body = collapseNewlines((parsed.text || text || "-").trim()) || "-";
  if (!sender) return body;
  if (body.toLowerCase().startsWith(`${sender.toLowerCase()}:`)) return body;
  return `${sender}: ${body}`;
}

export function dedupeBySignature<T extends Message>(items: T[]): T[] {
  const deduped: T[] = [];
  const bySignature = new Map<string, T>();

  for (const msg of items) {
    const signature =
      typeof msg.signature === "string"
        ? msg.signature.trim().toUpperCase()
        : "";
    const canDedupe = msg.message_type === "channel" && signature.length >= 8;
    if (!canDedupe) {
      deduped.push(msg);
      continue;
    }

    const existing = bySignature.get(signature);
    if (!existing) {
      const clone: T = {
        ...msg,
        observers: [...(msg.observers ?? [])],
      } as T;
      bySignature.set(signature, clone);
      deduped.push(clone);
      continue;
    }

    const combined = [...(existing.observers ?? []), ...(msg.observers ?? [])];
    const seenReceivers = new Set<string>();
    existing.observers = combined.filter((recv) => {
      const key =
        recv?.public_key ||
        recv?.node_id ||
        `${recv?.observed_at ?? ""}:${recv?.snr ?? ""}`;
      if (seenReceivers.has(key)) return false;
      seenReceivers.add(key);
      return true;
    });

    if (!existing.observed_by && msg.observed_by)
      existing.observed_by = msg.observed_by;
    if (!existing.observer_name && msg.observer_name)
      existing.observer_name = msg.observer_name;
    if (!existing.observer_tag_name && msg.observer_tag_name)
      existing.observer_tag_name = msg.observer_tag_name;
    if (!existing.pubkey_prefix && msg.pubkey_prefix)
      existing.pubkey_prefix = msg.pubkey_prefix;
    if (!existing.sender_name && msg.sender_name)
      existing.sender_name = msg.sender_name;
    if (!existing.sender_tag_name && msg.sender_tag_name)
      existing.sender_tag_name = msg.sender_tag_name;
    if (!existing.channel_name && msg.channel_name)
      existing.channel_name = msg.channel_name;
    if (
      existing.channel_name === "Public" &&
      msg.channel_name &&
      msg.channel_name !== "Public"
    ) {
      existing.channel_name = msg.channel_name;
    }
    if (existing.channel_idx === null || existing.channel_idx === undefined) {
      if (msg.channel_idx !== null && msg.channel_idx !== undefined) {
        existing.channel_idx = msg.channel_idx;
      }
    } else if (
      existing.channel_idx === 17 &&
      msg.channel_idx !== null &&
      msg.channel_idx !== undefined &&
      msg.channel_idx !== 17
    ) {
      existing.channel_idx = msg.channel_idx;
    }
  }

  return deduped;
}
