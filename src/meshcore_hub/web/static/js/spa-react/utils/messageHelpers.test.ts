import { describe, expect, it } from "vitest";

import {
  parseSenderFromText,
  collapseNewlines,
  channelInfo,
  messageTextWithSender,
  dedupeBySignature,
} from "@/utils/messageHelpers";

describe("parseSenderFromText", () => {
  it("extracts the @[sender] pattern", () => {
    const result = parseSenderFromText("@[Alice]: Hello world");
    expect(result.sender).toBe("Alice");
    expect(result.text).toBe("Hello world");
  });

  it("extracts the ack @[sender] pattern", () => {
    const result = parseSenderFromText("ack @[Bob]: Got it");
    expect(result.sender).toBe("Bob");
    expect(result.text).toBe("Got it");
  });

  it("extracts the plain ack sender pattern", () => {
    const result = parseSenderFromText("ack Carol: Message");
    expect(result.sender).toBe("Carol");
    expect(result.text).toBe("Message");
  });

  it("returns null sender for non-matching text", () => {
    const result = parseSenderFromText("Just a message");
    expect(result.sender).toBeNull();
    expect(result.text).toBe("Just a message");
  });

  it("returns dash for null input", () => {
    expect(parseSenderFromText(null).text).toBe("-");
  });
});

describe("collapseNewlines", () => {
  it("replaces newlines with single spaces", () => {
    expect(collapseNewlines("line1\nline2")).toBe("line1 line2");
  });

  it("collapses surrounding whitespace", () => {
    expect(collapseNewlines("a  \n  b")).toBe("a b");
  });

  it("returns null for null input", () => {
    expect(collapseNewlines(null)).toBeNull();
  });
});

describe("channelInfo", () => {
  const base = {
    message_type: "channel" as const,
    text: "hello",
    received_at: "2024-01-01",
  };

  it("returns null label for non-channel messages", () => {
    const result = channelInfo(
      { ...base, message_type: "direct" },
      new Map(),
      "Fallback",
    );
    expect(result.label).toBeNull();
    expect(result.text).toBe("hello");
  });

  it("uses the known channel label from the map", () => {
    const labels = new Map([[17, "Public"]]);
    const result = channelInfo(
      { ...base, text: "[Public] hello", channel_idx: 17 },
      labels,
      "Fallback",
    );
    expect(result.label).toBe("Public");
    expect(result.text).toBe("hello");
  });

  it("falls back to channel_name when no label map match exists", () => {
    const result = channelInfo(
      { ...base, channel_name: "Custom" },
      new Map(),
      "Fallback",
    );
    expect(result.label).toBe("Custom");
  });

  it("falls back to Ch <idx> when only channel_idx is available", () => {
    const result = channelInfo(
      { ...base, channel_idx: 5 },
      new Map(),
      "Fallback",
    );
    expect(result.label).toBe("Ch 5");
  });
});

describe("messageTextWithSender", () => {
  const base = {
    message_type: "channel" as const,
    text: "hi",
    received_at: "2024-01-01",
  };

  it("prefixes with the sender name from msg fields", () => {
    expect(
      messageTextWithSender({ ...base, sender_name: "Alice" }, "hi"),
    ).toBe("Alice: hi");
  });

  it("parses the sender from text when no explicit sender exists", () => {
    expect(
      messageTextWithSender({ ...base, text: "@[Bob]: hello" }, "@[Bob]: hello"),
    ).toBe("Bob: hello");
  });

  it("does not duplicate the sender prefix", () => {
    expect(
      messageTextWithSender(
        { ...base, text: "Alice: hi", sender_name: "Alice" },
        "Alice: hi",
      ),
    ).toBe("Alice: hi");
  });
});

describe("dedupeBySignature", () => {
  const base = {
    message_type: "channel" as const,
    text: "hello",
    received_at: "2024-01-01",
  };

  it("keeps non-channel messages as-is", () => {
    const items = [{ ...base, message_type: "direct" as const }];
    expect(dedupeBySignature(items)).toHaveLength(1);
  });

  it("merges channel messages with the same long signature", () => {
    const items = [
      {
        ...base,
        signature: "SIG12345678",
        observers: [{ public_key: "a" }],
      },
      {
        ...base,
        signature: "SIG12345678",
        observers: [{ public_key: "b" }],
      },
    ];
    const result = dedupeBySignature(items);
    expect(result).toHaveLength(1);
    expect(result[0].observers).toHaveLength(2);
  });

  it("keeps messages with different signatures separate", () => {
    const items = [
      { ...base, signature: "SIGAAAAAA" },
      { ...base, signature: "SIGBBBBBB" },
    ];
    expect(dedupeBySignature(items)).toHaveLength(2);
  });

  it("does not dedupe channel messages with short signatures", () => {
    const items = [{ ...base, signature: "short" }];
    expect(dedupeBySignature(items)).toHaveLength(1);
  });
});
