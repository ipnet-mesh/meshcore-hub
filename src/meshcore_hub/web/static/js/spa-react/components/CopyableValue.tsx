import { copyToClipboard } from "@/utils/clipboard";

export function CopyableValue({
  value,
  variant = "inline",
}: {
  value: string;
  variant?: "inline" | "block";
}) {
  return (
    <code
      className={
        variant === "block"
          ? "text-sm bg-base-200 p-2 rounded block break-all cursor-pointer hover:bg-base-300 select-all"
          : "font-mono text-xs cursor-pointer hover:bg-base-200 px-1 py-0.5 rounded select-all"
      }
      onClick={(e) => copyToClipboard(e, value)}
      title="Click to copy"
    >
      {value}
    </code>
  );
}
