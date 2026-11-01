import React from "react";

interface CardProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  action,
  children,
  className = "",
  bodyClassName = "",
}) => {
  return (
    <div
      className={`rounded-lg bg-scout-surface-1 border border-scout-border shadow-scout-card overflow-hidden ${className}`}
    >
      {(title || subtitle || action) && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-scout-border px-5 py-4 gap-2 bg-scout-surface-2/40">
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-scout-text-primary tracking-wide flex items-center gap-2">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-xs text-scout-text-muted mt-0.5">{subtitle}</p>
            )}
          </div>
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={`p-5 ${bodyClassName}`}>{children}</div>
    </div>
  );
};
