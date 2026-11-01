import React from "react";

interface ThreatBadgeProps {
  threat: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const ThreatBadge: React.FC<ThreatBadgeProps> = ({
  threat,
  size = "md",
  className = "",
}) => {
  const norm = (threat || "").toUpperCase();

  const configMap: Record<string, { bg: string; text: string; border: string }> = {
    CRITICAL: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/50" },
    CRITICAL_EMERGENCY: { bg: "bg-red-500/25", text: "text-red-400", border: "border-red-500/60" },
    ACTIVE_THREAT: { bg: "bg-orange-500/20", text: "text-orange-400", border: "border-orange-500/50" },
    HIGH: { bg: "bg-orange-500/20", text: "text-orange-400", border: "border-orange-500/50" },
    POTENTIAL_THREAT: { bg: "bg-amber-500/20", text: "text-amber-400", border: "border-amber-500/50" },
    ELEVATED_PREPAREDNESS: { bg: "bg-yellow-500/20", text: "text-yellow-400", border: "border-yellow-500/50" },
    MODERATE: { bg: "bg-yellow-500/20", text: "text-yellow-400", border: "border-yellow-500/50" },
    LOW: { bg: "bg-emerald-500/20", text: "text-emerald-400", border: "border-emerald-500/50" },
    LOW_CONCERN: { bg: "bg-emerald-500/20", text: "text-emerald-400", border: "border-emerald-500/50" },
    INSUFFICIENT_DATA: { bg: "bg-slate-500/20", text: "text-slate-400", border: "border-slate-500/50" },
    INSUFFICIENT_EVIDENCE: { bg: "bg-slate-500/20", text: "text-slate-400", border: "border-slate-500/50" },
  };

  const style = configMap[norm] || {
    bg: "bg-scout-surface-2",
    text: "text-scout-text-secondary",
    border: "border-scout-border",
  };

  const sizeClasses = {
    sm: "text-[10px] px-2 py-0.5",
    md: "text-xs px-2.5 py-1",
    lg: "text-sm px-3.5 py-1.5 font-bold",
  }[size];

  return (
    <span
      className={`inline-flex items-center font-mono uppercase tracking-wider rounded border ${style.bg} ${style.text} ${style.border} ${sizeClasses} ${className}`}
    >
      {threat.replace(/_/g, " ")}
    </span>
  );
};
