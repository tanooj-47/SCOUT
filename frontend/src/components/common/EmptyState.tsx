import React from "react";
import { LucideIcon, Inbox } from "lucide-react";
import { Button } from "./Button";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: LucideIcon;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon: Icon = Inbox,
  actionLabel,
  onAction,
  className = "",
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 text-center rounded-lg border border-dashed border-scout-border bg-scout-surface-1/40 ${className}`}
    >
      <div className="p-4 rounded-full bg-scout-surface-2 text-scout-text-muted mb-4 border border-scout-border">
        <Icon className="w-8 h-8" />
      </div>
      <h4 className="text-base font-semibold text-scout-text-primary mb-1">
        {title}
      </h4>
      <p className="text-xs text-scout-text-secondary max-w-sm mb-6">
        {description}
      </p>
      {actionLabel && onAction && (
        <Button variant="secondary" size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
};
