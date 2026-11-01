import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { workflowsApi } from "../../services";

export const AppLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);

  // Poll pending approvals count for live badge in sidebar
  const { data: pendingApprovals = [] } = useQuery({
    queryKey: ["pending-approvals-count"],
    queryFn: () => workflowsApi.listPendingApprovals(),
    refetchInterval: 15000,
    staleTime: 10000,
  });

  return (
    <div className="min-h-screen bg-scout-bg text-scout-text-primary flex">
      {/* Sidebar */}
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        pendingApprovalsCount={pendingApprovals.length}
      />

      {/* Main Content Area */}
      <div
        className={`flex-1 flex flex-col min-h-screen transition-all duration-300 ease-in-out ${
          collapsed ? "ml-20" : "ml-64"
        }`}
      >
        <Topbar collapsed={collapsed} />

        <main className="flex-1 p-6 md:p-8 max-w-[1700px] w-full mx-auto animate-in fade-in duration-200">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
