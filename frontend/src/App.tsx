import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { OverviewPage } from "./features/dashboard/OverviewPage";
import { LiveMonitoringPage } from "./features/monitoring/LiveMonitoringPage";
import { IncidentIntelligencePage } from "./features/incidents/IncidentIntelligencePage";
import { GeospatialIntelligencePage } from "./features/geospatial/GeospatialIntelligencePage";
import { RiskAssessmentPage } from "./features/risk/RiskAssessmentPage";
import { ResponseWorkflowsPage } from "./features/workflows/ResponseWorkflowsPage";
import { ReportsPage } from "./features/reports/ReportsPage";
import { DataSourcesPage } from "./features/datasources/DataSourcesPage";
import { SettingsPage } from "./features/settings/SettingsPage";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="overview" element={<Navigate to="/" replace />} />
          <Route path="monitoring" element={<LiveMonitoringPage />} />
          <Route path="incidents" element={<IncidentIntelligencePage />} />
          <Route path="geospatial" element={<GeospatialIntelligencePage />} />
          <Route path="risk" element={<RiskAssessmentPage />} />
          <Route path="workflows" element={<ResponseWorkflowsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="data-sources" element={<DataSourcesPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
