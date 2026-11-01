import React from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Radar,
  Flame,
  MapPin,
  ShieldAlert,
  GitPullRequest,
  FileText,
  Database,
  Settings,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";
import { Logo } from "../common/Logo";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  pendingApprovalsCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggleCollapse,
  pendingApprovalsCount = 0,
}) => {
  const navigationItems = [
    { name: "Overview Dashboard", path: "/", icon: LayoutDashboard, exact: true },
    { name: "Live Monitoring", path: "/monitoring", icon: Radar },
    { name: "Incident Intelligence", path: "/incidents", icon: Flame },
    { name: "Geospatial Intelligence", path: "/geospatial", icon: MapPin },
    { name: "Risk Assessment", path: "/risk", icon: ShieldAlert },
    {
      name: "Response Workflows",
      path: "/workflows",
      icon: GitPullRequest,
      badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
    },
    { name: "Reports & Dossiers", path: "/reports", icon: FileText },
    { name: "Data Sources", path: "/data-sources", icon: Database },
    { name: "System Settings", path: "/settings", icon: Settings },
  ];

  return (
    <aside
      className={`fixed top-0 bottom-0 left-0 z-30 flex flex-col border-r border-scout-border bg-scout-sidebar transition-all duration-300 ease-in-out ${
        collapsed ? "w-20" : "w-64"
      }`}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between border-b border-scout-border px-4">
        {collapsed ? (
          <div className="w-full flex justify-center">
            <Logo size="sm" showTagline={false} />
          </div>
        ) : (
          <Logo size="md" showTagline={true} />
        )}
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 space-y-1.5 overflow-y-auto p-3">
        <div className={`mb-2 px-3 text-[10px] font-mono uppercase tracking-wider text-scout-text-muted ${collapsed ? "hidden" : "block"}`}>
          Operational Modules
        </div>

        {navigationItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.exact}
            className={({ isActive }) =>
              `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium transition-all duration-150 ${
                isActive
                  ? "bg-scout-cyan/15 text-scout-cyan border border-scout-cyan/30 shadow-sm"
                  : "text-scout-text-secondary hover:bg-scout-surface-1 hover:text-scout-text-primary"
              } ${collapsed ? "justify-center" : ""}`
            }
            title={collapsed ? item.name : undefined}
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            {!collapsed && <span className="truncate">{item.name}</span>}
            {!collapsed && item.badge !== undefined && (
              <span className="ml-auto flex h-5 min-w-[20px] items-center justify-center rounded-full bg-scout-orange/20 px-1.5 font-mono text-[11px] font-bold text-scout-orange border border-scout-orange/40 animate-pulse">
                {item.badge}
              </span>
            )}
            {collapsed && item.badge !== undefined && (
              <span className="absolute top-2 right-2 flex h-2 w-2 rounded-full bg-scout-orange animate-ping" />
            )}
          </NavLink>
        ))}
      </nav>

      {/* Decision-Support Safety Advisory Notice */}
      {!collapsed && (
        <div className="mx-3 mb-3 rounded-lg border border-scout-border/60 bg-scout-surface-1/60 p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-scout-cyan">
            <ShieldCheck className="w-4 h-4 text-scout-cyan" />
            <span>Advisory Decision Support</span>
          </div>
          <p className="mt-1 text-[10px] text-scout-text-muted leading-relaxed">
            Zero autonomous emergency dispatch. All recommended actions require authorized Incident Commander approval.
          </p>
        </div>
      )}

      {/* Collapse Footer */}
      <div className="flex h-12 items-center justify-between border-t border-scout-border px-3 bg-scout-sidebar/50">
        <button
          onClick={onToggleCollapse}
          className="flex w-full items-center justify-center rounded-md p-1.5 text-scout-text-muted hover:bg-scout-surface-1 hover:text-scout-text-primary transition-colors"
          title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <div className="flex items-center gap-2 text-xs">
              <ChevronLeft className="w-4 h-4" />
              <span>Collapse Sidebar</span>
            </div>
          )}
        </button>
      </div>
    </aside>
  );
};
