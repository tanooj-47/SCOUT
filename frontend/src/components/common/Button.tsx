import React from "react";
import { LucideIcon } from "lucide-react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "warning" | "ghost" | "outline";
  size?: "sm" | "md" | "lg";
  icon?: LucideIcon;
  iconPosition?: "left" | "right";
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = "primary",
  size = "md",
  icon: Icon,
  iconPosition = "left",
  isLoading = false,
  className = "",
  disabled,
  ...props
}) => {
  const baseClasses =
    "inline-flex items-center justify-center font-medium rounded-md transition-all duration-150 select-none disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-scout-bg";

  const sizeClasses = {
    sm: "text-xs px-3 py-1.5 gap-1.5",
    md: "text-sm px-4 py-2 gap-2",
    lg: "text-base px-5 py-2.5 gap-2.5",
  }[size];

  const variantClasses = {
    primary:
      "bg-scout-cyan text-scout-bg font-semibold hover:bg-scout-cyan/90 active:scale-[0.98] shadow-sm focus:ring-scout-cyan",
    secondary:
      "bg-scout-surface-2 text-scout-text-primary border border-scout-border hover:bg-scout-surface-3 hover:border-scout-border/80 focus:ring-scout-border",
    danger:
      "bg-scout-red text-white font-semibold hover:bg-scout-red/90 active:scale-[0.98] focus:ring-scout-red",
    warning:
      "bg-scout-orange text-white font-semibold hover:bg-scout-orange/90 active:scale-[0.98] focus:ring-scout-orange",
    ghost:
      "text-scout-text-secondary hover:text-scout-text-primary hover:bg-scout-surface-2 focus:ring-scout-border",
    outline:
      "bg-transparent text-scout-cyan border border-scout-cyan/40 hover:bg-scout-cyan/10 focus:ring-scout-cyan",
  }[variant];

  return (
    <button
      className={`${baseClasses} ${sizeClasses} ${variantClasses} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-1.5" />
      ) : Icon && iconPosition === "left" ? (
        <Icon className="w-4 h-4" />
      ) : null}
      <span>{children}</span>
      {!isLoading && Icon && iconPosition === "right" && (
        <Icon className="w-4 h-4" />
      )}
    </button>
  );
};
