import React from "react";
import { cn } from "../lib/utils";
import { X } from "@phosphor-icons/react";

export function Modal({ open, onClose, title, children, size = "md", testId }) {
  if (!open) return null;
  const sizeMap = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl" };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid={testId || "modal"}>
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onClose} />
      <div className={cn("relative bg-white rounded-lg shadow-soft border border-line w-full overflow-hidden fade-up", sizeMap[size])}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <h3 className="font-display text-base font-medium">{title}</h3>
          <button onClick={onClose} className="btn-ghost p-1.5" data-testid="modal-close-btn">
            <X size={16} />
          </button>
        </div>
        <div className="p-5 max-h-[70vh] overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
