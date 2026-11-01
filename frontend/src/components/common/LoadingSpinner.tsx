import React from "react";

interface LoadingSpinnerProps {
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  label = "Loading telemetry...",
  size = "md",
  className = "",
}) => {
  const sizeMap = {
    sm: "w-4 h-4 border-2",
    md: "w-8 h-8 border-3",
    lg: "w-12 h-12 border-4",
  };

  return (
    <div className={`flex flex-col items-center justify-center py-10 gap-3 ${className}`}>
      <div
        className={`${sizeMap[size]} border-scout-border border-t-scout-cyan rounded-full animate-spin`}
      />
      {label && (
        <span className="text-xs font-mono text-scout-text-secondary tracking-wider uppercase">
          {label}
        </span>
      )}
    </div>
  );
};
