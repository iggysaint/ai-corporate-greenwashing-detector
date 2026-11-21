"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Accessible side panel (focus trap, Escape to close, labelled) built on Radix Dialog. */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  side = "right",
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  side?: "right" | "left";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-950/40 backdrop-blur-[1px]" />
        <Dialog.Content
          className={cn(
            "fixed inset-y-0 z-50 flex w-full flex-col bg-surface shadow-pop focus:outline-none",
            side === "right" ? "right-0 max-w-2xl border-l border-line" : "left-0 max-w-xs",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="text-[15px] font-semibold text-text">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-0.5 text-[13px] text-text-muted">{description}</Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">Details panel</Dialog.Description>
              )}
            </div>
            <Dialog.Close
              className="-mr-1 rounded-md p-1.5 text-text-muted hover:bg-black/[0.05] hover:text-text"
              aria-label="Close panel"
            >
              <X aria-hidden className="size-4" />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
