import { Button } from "./Button";
import { Sheet } from "./Sheet";

export function ConfirmDialog({
  open,
  title,
  text,
  confirmLabel,
  cancelLabel = "Не сейчас",
  tone = "primary",
  loading,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  text: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "primary" | "danger";
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant={tone} size="lg" block loading={loading} onClick={onConfirm} data-autofocus>
            {confirmLabel}
          </Button>
          <Button variant="ghost" size="md" block onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
        </>
      }
    >
      <p className="leading-relaxed">{text}</p>
    </Sheet>
  );
}
