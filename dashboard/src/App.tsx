import { useState } from "react";
import type { Page } from "./types";
import { useWebSocket } from "./useWebSocket";
import Sidebar from "./components/Sidebar";
import DashboardOverview from "./components/DashboardOverview";
import ClientsPage from "./components/ClientsPage";
import LiveCallsPage from "./components/LiveCallsPage";
import AppointmentsPage from "./components/AppointmentsPage";
import ProvidersPage from "./components/ProvidersPage";
import SettingsPage from "./components/SettingsPage";

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const { sessions, wsStatus } = useWebSocket();

  const activeCalls = Object.values(sessions).filter(
    (s) => s.status === "active"
  ).length;

  return (
    <div className="flex h-screen w-full overflow-hidden font-sans bg-gray-100">
      {/* Stitch-style wrapper */}
      <div className="flex flex-1 bg-white rounded-3xl m-2 shadow-2xl overflow-hidden">
        <Sidebar
          currentPage={page}
          onNavigate={setPage}
          activeCalls={activeCalls}
        />

        {page === "dashboard" && <DashboardOverview sessions={sessions} />}
        {page === "clients" && <ClientsPage sessions={sessions} />}
        {page === "calls" && (
          <LiveCallsPage sessions={sessions} wsStatus={wsStatus} />
        )}
        {page === "appointments" && <AppointmentsPage />}
        {page === "providers" && <ProvidersPage />}
        {page === "settings" && <SettingsPage />}
      </div>
    </div>
  );
}
