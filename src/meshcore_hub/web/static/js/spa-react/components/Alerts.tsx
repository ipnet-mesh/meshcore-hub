import { useTranslation } from "react-i18next";
import { IconError, IconInfo, IconSuccess, IconAlert } from "@/components/icons";

export function Loading() {
  return (
    <div className="flex justify-center py-12">
      <span className="loading loading-spinner loading-lg"></span>
    </div>
  );
}

export function ErrorAlert({ message }: { message: string }) {
  return (
    <div role="alert" className="alert alert-error mb-4">
      <IconError className="stroke-current shrink-0 h-6 w-6" />
      <span>{message}</span>
    </div>
  );
}

export function InfoAlert({ message }: { message: string }) {
  return (
    <div role="alert" className="alert alert-info mb-4">
      <IconInfo className="stroke-current shrink-0 h-6 w-6" />
      <span>{message}</span>
    </div>
  );
}

export function SuccessAlert({ message }: { message: string }) {
  return (
    <div role="alert" className="alert alert-success mb-4">
      <IconSuccess className="stroke-current shrink-0 h-6 w-6" />
      <span>{message}</span>
    </div>
  );
}

export function WarningBadge({ message }: { message: string }) {
  return (
    <span className="tooltip tooltip-bottom" data-tip={message}>
      <span className="badge badge-warning badge-sm">
        <IconAlert className="h-4 w-4" />
      </span>
    </span>
  );
}
