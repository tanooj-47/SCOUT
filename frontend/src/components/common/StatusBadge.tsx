import React from "react";

export type BadgeVariant =
  | "active"
  | "investigating"
  | "reported"
  | "contained"
  | "resolved"
  | "false_alarm"
  | "pending"
  | "approved"
  | "rejected"
  | "needs_revision"
  | "running"
  | "completed"
  | "failed"
  | "suspended_for_approval";

interface StatusBadgeProps {
  status: BadgeVariant | string;
  size?: "sm" | "md";
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = "md",
  className = "",
}) => {
  const norm = (status || "").toLowerCase().replace(/\s+/g, "_");

  const styleMap: Record<string, { bg: string; text: string; border: string; dot: string }> = {
    active: {
      bg: "bg-scout-red/10",
      text: "text-scout-red",
      border: "border-scout-red/30",
      dot: "bg-scout-red animate-pulse",
    },
    investigating: {
      bg: "bg-scout-orange/10",
      text: "text-scout-orange",
      border: "border-scout-orange/30",
      dot: "bg-scout-orange",
    },
    reported: {
      bg: "bg-scout-yellow/10",
      text: "text-scout-yellow",
      border: "border-scout-yellow/30",
      dot: "bg-scout-yellow",
    },
    contained: {
      bg: "bg-scout-blue/10",
      text: "text-scout-blue",
      border: "border-scout-blue/30",
      dot: "bg-scout-blue",
    },
    resolved: {
      bg: "bg-scout-green/10",
      text: "text-scout-green",
      border: "border-scout-green/30",
      dot: "bg-scout-green",
    },
    false_alarm: {
      bg: "bg-scout-surface-3",
      text: "text-scout-text-muted",
      border: "border-scout-border",
      dot: "bg-scout-text-muted",
    },
    pending: {
      bg: "bg-scout-yellow/15",
      text: "text-scout-yellow",
      border: "border-scout-yellow/40",
      dot: "bg-scout-yellow animate-pulse",
    },
    approved: {
      bg: "bg-scout-green/15",
      text: "text-scout-green",
      border: "border-scout-green/40",
      dot: "bg-scout-green",
    },
    rejected: {
      bg: "bg-scout-red/15",
      text: "text-scout-red",
      border: "border-scout-red/40",
      dot: "bg-scout-red",
    },
    needs_revision: {
      bg: "bg-scout-orange/15",
      text: "text-scout-orange",
      border: "border-scout-orange/40",
      dot: "bg-scout-orange",
    },
    running: {
      bg: "bg-scout-cyan/15",
      text: "text-scout-cyan",
      border: "border-scout-cyan/40",
      dot: "bg-scout-cyan animate-pulse",
    },
    completed: {
      bg: "bg-scout-green/15",
      text: "text-scout-green",
      border: "border-scout-green/40",
      dot: "bg-scout-green",
    },
    failed: {
      bg: "bg-scout-red/15",
      text: "text-scout-red",
      border: "border-scout-red/40",
      dot: "bg-scout-red",
    },
    suspended_for_approval: {
      bg: "bg-amber-500/15",
      text: "text-amber-400",
      border: "border-amber-500/40",
      dot: "bg-amber-400 animate-ping",
    },
  };

  const currentStyle = styleMap[norm] || {
    bg: "bg-scout-surface-2",
    text: "text-scout-text-secondary",
    border: "border-scout-border",
    dot: "bg-scout-text-secondary",
  };

  const sizeClasses =
    size === "sm" ? "text-[11px] px-2 py-0.5 gap-1.5" : "text-xs px-2.5 py-1 gap-2";

  return (
    <span
      className={`inline-flex items-center font-mono uppercase font-semibold tracking-wider rounded-full border ${currentStyle.bg} ${currentStyle.text} ${currentStyle.border} ${sizeClasses} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${currentStyle.dot}`} />
      <span>{status.replace(/_/g, " ")}</span>
    </span>
  );
};
