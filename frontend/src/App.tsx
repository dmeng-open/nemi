import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { IntegrationsPage } from "@/pages/IntegrationsPage";
import { NewPlanPage } from "@/pages/NewPlanPage";
import { PlanPage } from "@/pages/PlanPage";
import { PreferencesPage } from "@/pages/PreferencesPage";
import { RecentPlansPage } from "@/pages/RecentPlansPage";
import { SettingsPage } from "@/pages/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<NewPlanPage />} />
            <Route path="plans" element={<RecentPlansPage />} />
            <Route path="plans/:planId" element={<PlanPage />} />
            <Route path="preferences" element={<PreferencesPage />} />
            <Route path="integrations" element={<IntegrationsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
