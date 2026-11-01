import React from "react";
import { AlertTriangle, AlertCircle, Info, CheckCircle2, X } from "lucide-react";

interface AlertBannerProps {
  type?: "info" | "warning" | "error" | "success";
  title?: string;
  message: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({
  type = "info",
  title,
  message,
  onDismiss,
  className = "",
}) => {
  const styles = {
    info: {
      bg: "bg-scout-blue/10 border-scout-blue/30 text-scout-blue",
      icon: Info,
    },
    warning: {
      bg: "bg-scout-orange/10 border-scout-orange/30 text-scout-orange",
      icon: AlertTriangle,
    },
    error: {
      bg: "bg-scout-red/10 border-scout-red/30 text-scout-red",
      icon: AlertCircle,
    },
    success: {
      bg: "bg-scout-green/10 border-scout-green/30 text-scout-green",
      icon: CheckCircle2,
    },
  }[type];

  const Icon = styles.icon;

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-4 ${styles.bg} ${className}`}
    >
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1 text-xs leading-relaxed text-scout-text-primary">
        {title && (
          <p className="font-semibold text-scout-text-primary mb-0.5">{title}</p>
        )}
        <div className="text-scout-text-secondary">{message}</div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-scout-text-muted hover:text-scout-text-primary p-1 -mr-1 -mt-1 rounded"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};
