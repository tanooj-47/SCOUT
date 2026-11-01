import React from "react";
import { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "neutral";
  accentColor?: "cyan" | "orange" | "red" | "green" | "yellow" | "blue";
  onClick?: () => void;
  className?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  subtext,
  icon: Icon,
  accentColor = "cyan",
  onClick,
  className = "",
}) => {
  const accentClasses = {
    cyan: "text-scout-cyan bg-scout-cyan/10 border-scout-cyan/20",
    orange: "text-scout-orange bg-scout-orange/10 border-scout-orange/20",
    red: "text-scout-red bg-scout-red/10 border-scout-red/20",
    green: "text-scout-green bg-scout-green/10 border-scout-green/20",
    yellow: "text-scout-yellow bg-scout-yellow/10 border-scout-yellow/20",
    blue: "text-scout-blue bg-scout-blue/10 border-scout-blue/20",
  }[accentColor];

  return (
    <div
      onClick={onClick}
      className={`relative overflow-hidden rounded-lg bg-scout-surface-1 border border-scout-border p-5 transition-all duration-200 hover:border-scout-border/80 hover:shadow-scout-card ${
        onClick ? "cursor-pointer hover:bg-scout-surface-2/60" : ""
      } ${className}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-scout-text-secondary">
            {label}
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono tracking-tight text-scout-text-primary">
              {value}
            </span>
          </div>
          {subtext && (
            <p className="mt-1 text-xs text-scout-text-muted">{subtext}</p>
          )}
        </div>
        {Icon && (
          <div className={`p-2.5 rounded-lg border ${accentClasses}`}>
            <Icon className="w-5 h-5" />
          </div>
        )}
      </div>
      <div
        className={`absolute bottom-0 left-0 right-0 h-0.5 ${
          accentColor === "cyan"
            ? "bg-scout-cyan/40"
            : accentColor === "orange"
            ? "bg-scout-orange/40"
            : accentColor === "red"
            ? "bg-scout-red/40"
            : accentColor === "green"
            ? "bg-scout-green/40"
            : accentColor === "yellow"
            ? "bg-scout-yellow/40"
            : "bg-scout-blue/40"
        }`}
      />
    </div>
  );
};
