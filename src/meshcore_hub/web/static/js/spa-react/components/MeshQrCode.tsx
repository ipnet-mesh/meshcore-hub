import QRCode from "react-qr-code";

export function MeshQrCode({
  value,
  size = 140,
  level = "L",
  className = "bg-white p-2 rounded-box",
  ...rest
}: {
  value: string;
  size?: number;
  level?: "L" | "M" | "Q" | "H";
  className?: string;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={className} {...rest}>
      <QRCode
        value={value}
        size={size}
        level={level}
        fgColor="#000000"
        bgColor="#ffffff"
      />
    </div>
  );
}
