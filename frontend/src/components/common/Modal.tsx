import React, { useEffect } from "react";
import { X } from "lucide-react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl" | "2xl" | "4xl";
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  maxWidth = "lg",
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const maxWidthClass = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-lg",
    xl: "max-w-xl",
    "2xl": "max-w-2xl",
    "4xl": "max-w-4xl",
  }[maxWidth];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-scout-bg/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal Dialog */}
      <div
        className={`relative w-full ${maxWidthClass} rounded-xl bg-scout-surface-1 border border-scout-border shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150`}
      >
        <div className="flex items-center justify-between border-b border-scout-border px-6 py-4 bg-scout-surface-2/60">
          <div>
            <h3 className="text-base font-semibold text-scout-text-primary tracking-wide">
              {title}
            </h3>
            {subtitle && (
              <p className="text-xs text-scout-text-muted mt-0.5">{subtitle}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-scout-text-muted hover:text-scout-text-primary hover:bg-scout-surface-3 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="max-h-[75vh] overflow-y-auto p-6">{children}</div>

        {footer && (
          <div className="flex items-center justify-end gap-3 border-t border-scout-border px-6 py-4 bg-scout-surface-2/40">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};
