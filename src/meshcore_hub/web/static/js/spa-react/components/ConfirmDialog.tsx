import type { ReactNode } from "react";

import { Modal } from "@/components/Modal";

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel,
  saving = false,
  tone = "error",
  onConfirm,
  onCancel,
}: {
  title: ReactNode;
  message: ReactNode;
  confirmLabel: ReactNode;
  cancelLabel: ReactNode;
  saving?: boolean;
  tone?: "error" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onCancel}
            disabled={saving}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={tone === "error" ? "btn btn-error" : "btn btn-primary"}
            onClick={onConfirm}
            disabled={saving}
          >
            {saving && (
              <span className="loading loading-spinner loading-sm" />
            )}
            {confirmLabel}
          </button>
        </>
      }
    >
      {message}
    </Modal>
  );
}
