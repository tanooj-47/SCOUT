import React from "react";

interface LogoProps {
  size?: "sm" | "md" | "lg" | "xl";
  showTagline?: boolean;
  className?: string;
  onClick?: () => void;
}

export const Logo: React.FC<LogoProps> = ({
  size = "md",
  showTagline = false,
  className = "",
  onClick,
}) => {
  const sizeMap = {
    sm: { img: "h-8 max-w-[120px]", title: "text-sm", tag: "text-[10px]" },
    md: { img: "h-11 max-w-[160px]", title: "text-base", tag: "text-xs" },
    lg: { img: "h-14 max-w-[210px]", title: "text-lg", tag: "text-sm" },
    xl: { img: "h-20 max-w-[300px]", title: "text-2xl", tag: "text-base" },
  };

  const currentSize = sizeMap[size];

  return (
    <div
      onClick={onClick}
      className={`inline-flex items-center gap-3 select-none ${
        onClick ? "cursor-pointer" : ""
      } ${className}`}
    >
      <div className="relative flex items-center justify-center overflow-hidden rounded-md bg-scout-sidebar/50 border border-scout-border/30 p-1">
        <img
          src="/brand/scout-logo.png"
          alt="SCOUT Platform"
          className={`${currentSize.img} object-contain transition-transform duration-200 hover:scale-105`}
          onError={(e) => {
            // Graceful fallback if asset path is unmounted in isolated test runner
            const target = e.currentTarget;
            target.style.display = "none";
            const parent = target.parentElement;
            if (parent && !parent.querySelector(".fallback-text")) {
              const fallback = document.createElement("span");
              fallback.className =
                "fallback-text font-black tracking-widest text-scout-cyan px-2 text-sm";
              fallback.textContent = "SCOUT";
              parent.appendChild(fallback);
            }
          }}
        />
      </div>
      {showTagline && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className={`font-bold tracking-wider text-scout-text-primary ${currentSize.title}`}>
              SCOUT
            </span>
            <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-scout-cyan/10 text-scout-cyan border border-scout-cyan/20">
              v1.0
            </span>
          </div>
          <span className={`text-scout-text-muted font-mono tracking-tight ${currentSize.tag}`}>
            Detect • Predict • Respond
          </span>
        </div>
      )}
    </div>
  );
};
