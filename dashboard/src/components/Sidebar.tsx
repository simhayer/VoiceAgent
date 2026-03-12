import type { Page } from "../types";
import {
  LayoutDashboard,
  Users,
  Phone,
  CalendarDays,
  Stethoscope,
  Settings,
  HelpCircle,
  LogOut,
} from "lucide-react";

const menuItems: { key: Page; label: string; icon: React.ReactNode }[] = [
  {
    key: "dashboard",
    label: "Dashboard",
    icon: <LayoutDashboard className="w-5 h-5" />,
  },
  { key: "clients", label: "Clients", icon: <Users className="w-5 h-5" /> },
  { key: "calls", label: "Live Calls", icon: <Phone className="w-5 h-5" /> },
  {
    key: "appointments",
    label: "Appointments",
    icon: <CalendarDays className="w-5 h-5" />,
  },
  {
    key: "providers",
    label: "Providers",
    icon: <Stethoscope className="w-5 h-5" />,
  },
];

const generalItems: { key: Page; label: string; icon: React.ReactNode }[] = [
  {
    key: "settings",
    label: "Settings",
    icon: <Settings className="w-5 h-5" />,
  },
];

interface Props {
  currentPage: Page;
  onNavigate: (page: Page) => void;
  activeCalls: number;
}

export default function Sidebar({
  currentPage,
  onNavigate,
  activeCalls,
}: Props) {
  return (
    <aside className="w-64 bg-gray-50 border-r border-gray-100 flex flex-col p-6 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2.5 mb-10 px-2">
        <div className="w-8 h-8 bg-brand-800 rounded-full flex items-center justify-center">
          <div className="w-4 h-4 border-2 border-white rounded-full" />
        </div>
        <span className="text-xl font-bold text-gray-800">Bright Smile</span>
      </div>

      {/* Menu Section */}
      <nav className="flex-1 space-y-1">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4 px-2">
          Menu
        </p>
        {menuItems.map((item) => {
          const isActive = currentPage === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
                isActive
                  ? "bg-white text-brand-900 border-l-4 border-brand-500 shadow-sm"
                  : "text-gray-500 hover:text-brand-700"
              }`}
            >
              <div className="flex items-center gap-3">
                {item.icon}
                {item.label}
              </div>
              {item.key === "calls" && activeCalls > 0 && (
                <span className="text-[10px] font-bold bg-brand-100 text-brand-700 px-1.5 py-0.5 rounded-full">
                  {activeCalls}
                </span>
              )}
            </button>
          );
        })}

        {/* General Section */}
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mt-8 mb-4 px-2">
          General
        </p>
        {generalItems.map((item) => {
          const isActive = currentPage === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
                isActive
                  ? "bg-white text-brand-900 border-l-4 border-brand-500 shadow-sm"
                  : "text-gray-500 hover:text-brand-700"
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
        <button className="w-full flex items-center gap-3 px-4 py-3 text-gray-500 hover:text-brand-700 text-sm font-medium transition-colors">
          <HelpCircle className="w-5 h-5" />
          Help
        </button>
        <button className="w-full flex items-center gap-3 px-4 py-3 text-red-400 hover:text-red-600 text-sm font-medium transition-colors">
          <LogOut className="w-5 h-5" />
          Logout
        </button>
      </nav>

      {/* AI Promo Card */}
      <div className="mt-auto bg-gray-900 rounded-2xl p-4 text-white relative overflow-hidden">
        <div className="relative z-10">
          <div className="w-8 h-8 bg-white/20 rounded-lg flex items-center justify-center mb-3">
            <Phone className="w-4 h-4" />
          </div>
          <p className="text-sm font-semibold leading-tight mb-1">
            AI Receptionist
            <br />
            Active
          </p>
          <p className="text-[10px] text-gray-400 mb-4">
            Handling calls 24/7
          </p>
          <div className="w-full bg-brand-700 text-white text-xs font-bold py-2 rounded-lg text-center">
            v0.2.0
          </div>
        </div>
        <div className="absolute -right-4 -bottom-4 w-24 h-24 bg-brand-900/40 rounded-full blur-2xl" />
      </div>
    </aside>
  );
}
