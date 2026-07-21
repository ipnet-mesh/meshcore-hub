import type { ReactNode } from "react";

export function Modal({
  title,
  children,
  footer,
  size = "md",
  onClose,
}: {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg";
  onClose: () => void;
}) {
  return (
    <dialog open className="modal modal-open">
      <div
        className={size === "lg" ? "modal-box modal-box-lg" : "modal-box"}
      >
        <h3 className="font-bold text-lg mb-4">{title}</h3>
        {children}
        {footer && <div className="modal-action">{footer}</div>}
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose} aria-label="Close" />
      </form>
    </dialog>
  );
}
