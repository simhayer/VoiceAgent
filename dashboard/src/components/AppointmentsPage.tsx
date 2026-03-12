import { useEffect, useState } from "react";
import {
  CalendarDays,
  Search,
  XCircle,
  Clock,
  User,
  Stethoscope,
} from "lucide-react";
import { fetchAppointments, cancelAppointment } from "../api";
import type { Appointment } from "../types";

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [cancelling, setCancelling] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    fetchAppointments()
      .then(setAppointments)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleCancel = async (id: string) => {
    if (!confirm("Cancel this appointment?")) return;
    setCancelling(id);
    try {
      await cancelAppointment(id);
      load();
    } catch (e) {
      console.error(e);
    } finally {
      setCancelling(null);
    }
  };

  let filtered = appointments;
  if (statusFilter !== "all") {
    filtered = filtered.filter((a) => a.status === statusFilter);
  }
  if (search.trim()) {
    const q = search.toLowerCase();
    filtered = filtered.filter(
      (a) =>
        a.patient_name?.toLowerCase().includes(q) ||
        a.patient_phone?.toLowerCase().includes(q) ||
        a.procedure_type.toLowerCase().includes(q) ||
        a.provider_name?.toLowerCase().includes(q)
    );
  }

  const statuses = ["all", "scheduled", "completed", "cancelled", "no_show"];

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="px-8 py-6 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-purple-50 flex items-center justify-center">
            <CalendarDays className="w-5 h-5 text-purple-600" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900">
              Appointments
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Manage all scheduled appointments
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="px-8 py-4 border-b border-gray-100 flex flex-wrap items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search by patient, provider, procedure…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 text-sm border-none rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 bg-gray-50"
          />
        </div>
        <div className="flex gap-1.5">
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`text-xs font-bold px-3 py-1.5 rounded-full capitalize transition-all ${
                statusFilter === s
                  ? "bg-brand-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              {s === "all" ? "All" : s.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto p-8">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin w-8 h-8 border-4 border-brand-600 border-t-transparent rounded-full" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <CalendarDays className="w-10 h-10 mb-2 opacity-20" />
            <p className="text-sm">No appointments found</p>
          </div>
        ) : (
          <div className="bg-white rounded-[24px] border border-gray-100 custom-shadow overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 text-left text-[10px] text-gray-400 uppercase tracking-wider font-bold">
                  <th className="px-6 py-4">Patient</th>
                  <th className="px-6 py-4">Procedure</th>
                  <th className="px-6 py-4">Provider</th>
                  <th className="px-6 py-4">Date & Time</th>
                  <th className="px-6 py-4">Duration</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((a) => (
                  <tr
                    key={a.id}
                    className="hover:bg-gray-50/50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                          <User className="w-4 h-4 text-gray-400" />
                        </div>
                        <div>
                          <p className="font-bold text-gray-800 text-sm">
                            {a.patient_name || "—"}
                          </p>
                          <p className="text-[10px] text-gray-400">
                            {a.patient_phone}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 capitalize text-gray-700 font-medium">
                      {a.procedure_type}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1.5 text-gray-700">
                        <Stethoscope className="w-3.5 h-3.5 text-gray-400" />
                        {a.provider_name || "—"}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-gray-700">
                      <div className="font-medium">
                        {new Date(a.start_time).toLocaleDateString()}
                      </div>
                      <div className="text-[10px] text-gray-400">
                        {new Date(a.start_time).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}{" "}
                        –{" "}
                        {new Date(a.end_time).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="flex items-center gap-1 text-gray-500 font-medium">
                        <Clock className="w-3.5 h-3.5" />
                        {a.duration_minutes}m
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-6 py-4">
                      {a.status === "scheduled" && (
                        <button
                          onClick={() => handleCancel(a.id)}
                          disabled={cancelling === a.id}
                          className="text-red-400 hover:text-red-600 transition disabled:opacity-50"
                          title="Cancel appointment"
                        >
                          <XCircle className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    scheduled:
      "text-[9px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100",
    completed:
      "text-[9px] font-bold text-brand-600 bg-brand-50 px-2 py-0.5 rounded-full border border-brand-100",
    cancelled:
      "text-[9px] font-bold text-red-500 bg-red-50 px-2 py-0.5 rounded-full border border-red-100",
    no_show:
      "text-[9px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-100",
  };
  return (
    <span
      className={
        styles[status] ||
        "text-[9px] font-bold text-gray-500 bg-gray-50 px-2 py-0.5 rounded-full border border-gray-100"
      }
    >
      {status.replace("_", " ")}
    </span>
  );
}
