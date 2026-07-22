import { formatRelativeTime, useFormatDateTime } from "@/utils/format";

export function TimeAgo({
  iso,
  className,
}: {
  iso: string | null;
  className?: string;
}) {
  const { formatDateTime } = useFormatDateTime();
  if (!iso) return null;
  return (
    <time className={className} dateTime={iso} title={formatDateTime(iso)}>
      {formatRelativeTime(iso)}
    </time>
  );
}
