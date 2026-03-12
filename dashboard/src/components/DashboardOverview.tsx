import { useEffect, useState } from "react";
import {
  Users,
  CalendarDays,
  Phone,
  Stethoscope,
  TrendingUp,
  Activity,
  ArrowUpRight,
  Clock,
  Search,
  Bell,
} from "lucide-react";
import { fetchPatients, fetchProviders, fetchAppointments } from "../api";
import type { Patient, Provider, Appointment, CallSession } from "../types";

interface Props {
  sessions: Record<string, CallSession>;
}

export default function DashboardOverview({ sessions }: Props) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchPatients(), fetchProviders(), fetchAppointments()])
      .then(([p, prov, a]) => {
        setPatients(p);
        setProviders(prov);
        setAppointments(a);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const activeCalls = Object.values(sessions).filter(
    (s) => s.status === "active"
  ).length;
  const totalCalls = Object.values(sessions).length;
  const todayStr = new Date().toISOString().split("T")[0];
  const todayAppointments = appointments.filter((a) =>
    a.start_time.startsWith(todayStr)
  );
  const scheduledToday = todayAppointments.filter(
    (a) => a.status === "scheduled"
  ).length;
  const completedToday = todayAppointments.filter(
    (a) => a.status === "completed"
  ).length;

  const recentAppointments = [...appointments]
    .sort(
      (a, b) =>
        new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
    )
    .slice(0, 5);

  // Procedure breakdown for chart
  const procedureCounts: Record<string, number> = {};
  appointments.forEach((a) => {
    procedureCounts[a.procedure_type] =
      (procedureCounts[a.procedure_type] || 0) + 1;
  });
  const topProcedures = Object.entries(procedureCounts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 7);
  const maxProcCount = Math.max(...topProcedures.map(([, c]) => c), 1);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white rounded-3xl m-2">
        <div className="animate-spin w-8 h-8 border-4 border-brand-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <main className="flex-1 overflow-y-auto p-8 bg-white">
      {/* Header */}
      <header className="flex items-center justify-between mb-8">
        <div className="relative w-96">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3">
            <Search className="h-5 w-5 text-gray-400" />
          </span>
          <input
            className="w-full bg-gray-50 border-none rounded-xl py-2.5 pl-10 pr-4 text-sm focus:ring-2 focus:ring-brand-500 outline-none"
            placeholder="Search patients, appointments..."
            type="text"
            readOnly
          />
        </div>
        <div className="flex items-center gap-6">
          <button className="relative hover:text-brand-600 text-gray-400 transition-colors">
            <Bell className="w-6 h-6" />
            {activeCalls > 0 && (
              <span className="absolute top-0 right-0 block h-2 w-2 rounded-full bg-red-500 ring-2 ring-white" />
            )}
          </button>
          <div className="flex items-center gap-3 border-l pl-6 border-gray-100">
            <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-bold text-sm">
              AD
            </div>
            <div className="text-left">
              <p className="text-sm font-bold text-gray-800 leading-none">
                Admin
              </p>
              <p className="text-[10px] text-gray-400 mt-1">
                Bright Smile Dental
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Title */}
      <section className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-gray-900">Dashboard</h1>
          <p className="text-gray-400 mt-1">
            Monitor your dental practice, calls, and appointments at a glance.
          </p>
        </div>
      </section>

      {/* ── Stat Cards (Stitch-style) ── */}
      <section className="grid grid-cols-4 gap-4 mb-8">
        {/* Featured Card — Active Calls */}
        <div className="bg-brand-800 p-6 rounded-[32px] text-white flex flex-col justify-between custom-shadow min-h-[160px]">
          <div className="flex justify-between items-start">
            <p className="text-sm font-medium opacity-90">Active Calls</p>
            <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
              <Phone className="w-4 h-4" />
            </div>
          </div>
          <div>
            <p className="text-4xl font-bold mb-2">{activeCalls}</p>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold bg-brand-700/50 w-max px-2 py-1 rounded-full">
              <span className="bg-white text-brand-800 rounded px-1">
                {totalCalls}
              </span>{" "}
              Total calls today
            </div>
          </div>
        </div>

        {/* Total Patients */}
        <div className="bg-white p-6 rounded-[32px] border border-gray-100 flex flex-col justify-between custom-shadow min-h-[160px]">
          <div className="flex justify-between items-start">
            <p className="text-sm font-medium text-gray-500">Total Patients</p>
            <div className="w-8 h-8 rounded-full border border-gray-200 flex items-center justify-center text-gray-400">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div>
            <p className="text-4xl font-bold text-gray-800 mb-2">
              {patients.length}
            </p>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold text-gray-400 bg-gray-50 w-max px-2 py-1 rounded-full border border-gray-100">
              <span className="bg-brand-100 text-brand-700 rounded px-1">
                <ArrowUpRight className="w-3 h-3 inline" />
              </span>{" "}
              Registered patients
            </div>
          </div>
        </div>

        {/* Today's Appointments */}
        <div className="bg-white p-6 rounded-[32px] border border-gray-100 flex flex-col justify-between custom-shadow min-h-[160px]">
          <div className="flex justify-between items-start">
            <p className="text-sm font-medium text-gray-500">
              Today's Appointments
            </p>
            <div className="w-8 h-8 rounded-full border border-gray-200 flex items-center justify-center text-gray-400">
              <CalendarDays className="w-4 h-4" />
            </div>
          </div>
          <div>
            <p className="text-4xl font-bold text-gray-800 mb-2">
              {todayAppointments.length}
            </p>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold text-gray-400 bg-gray-50 w-max px-2 py-1 rounded-full border border-gray-100">
              <span className="bg-blue-100 text-blue-700 rounded px-1">
                {scheduledToday}
              </span>{" "}
              Scheduled ·{" "}
              <span className="bg-brand-100 text-brand-700 rounded px-1">
                {completedToday}
              </span>{" "}
              Done
            </div>
          </div>
        </div>

        {/* Providers */}
        <div className="bg-white p-6 rounded-[32px] border border-gray-100 flex flex-col justify-between custom-shadow min-h-[160px]">
          <div className="flex justify-between items-start">
            <p className="text-sm font-medium text-gray-500">Providers</p>
            <div className="w-8 h-8 rounded-full border border-gray-200 flex items-center justify-center text-gray-400">
              <Stethoscope className="w-4 h-4" />
            </div>
          </div>
          <div>
            <p className="text-4xl font-bold text-gray-800 mb-2">
              {providers.length}
            </p>
            <p className="text-[10px] font-semibold text-gray-400">
              Active dentists
            </p>
          </div>
        </div>
      </section>

      {/* ── Middle Row ── */}
      <section className="grid grid-cols-12 gap-8 mb-8">
        {/* Procedure Analytics (bar chart) */}
        <div className="col-span-5 bg-white rounded-[32px] p-6 border border-gray-100 custom-shadow">
          <h3 className="font-bold text-gray-800 mb-6 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-brand-600" />
            Procedure Breakdown
          </h3>
          <div className="flex items-end justify-between h-48 px-2">
            {topProcedures.map(([proc, count], i) => {
              const h = Math.round((count / maxProcCount) * 100);
              const colors = [
                "bg-brand-700",
                "bg-brand-400",
                "bg-brand-900",
                "bg-brand-600",
                "bg-gray-200",
                "bg-gray-300",
                "bg-gray-200",
              ];
              return (
                <div key={proc} className="flex flex-col items-center gap-2">
                  <div
                    className={`w-12 rounded-full ${colors[i % colors.length]}`}
                    style={{ height: `${Math.max(h, 16)}%` }}
                  />
                  <span className="text-[10px] font-semibold text-gray-400 capitalize truncate max-w-[3rem] text-center">
                    {proc.slice(0, 5)}
                  </span>
                </div>
              );
            })}
            {topProcedures.length === 0 && (
              <p className="text-sm text-gray-400 m-auto">No data yet</p>
            )}
          </div>
        </div>

        {/* Live Call Activity */}
        <div className="col-span-3 bg-white rounded-[32px] p-6 border border-gray-100 custom-shadow flex flex-col justify-between">
          <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-brand-500" />
            Live Activity
          </h3>
          <div className="space-y-4 flex-1">
            {activeCalls > 0 ? (
              Object.values(sessions)
                .filter((s) => s.status === "active")
                .slice(0, 2)
                .map((s) => (
                  <div key={s.callSid} className="border-l-4 border-brand-600 pl-4">
                    <p className="text-sm font-bold text-gray-800 leading-tight">
                      {s.callerPhone}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {s.messages.length} messages · Live
                    </p>
                  </div>
                ))
            ) : (
              <div className="border-l-4 border-gray-200 pl-4">
                <p className="text-sm font-bold text-gray-800 leading-tight">
                  No active calls
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Waiting for incoming calls...
                </p>
              </div>
            )}
          </div>
          <div className="w-full bg-brand-700 hover:bg-brand-800 text-white font-bold py-3 rounded-2xl flex items-center justify-center gap-2 transition-all mt-4 text-sm cursor-default">
            <Phone className="w-4 h-4" />
            {activeCalls} Active Now
          </div>
        </div>

        {/* Recent Appointments List */}
        <div className="col-span-4 bg-white rounded-[32px] p-6 border border-gray-100 custom-shadow">
          <div className="flex items-center justify-between mb-6">
            <h3 className="font-bold text-gray-800">Upcoming</h3>
            <span className="text-[10px] font-bold text-gray-600 border border-gray-200 px-2 py-1 rounded-lg">
              {appointments.length} total
            </span>
          </div>
          <div className="space-y-4">
            {recentAppointments.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8">
                No appointments yet
              </p>
            ) : (
              recentAppointments.map((a) => {
                const iconColors: Record<string, string> = {
                  cleaning: "bg-brand-50 text-brand-600",
                  exam: "bg-blue-50 text-blue-600",
                  crown: "bg-amber-50 text-amber-600",
                  filling: "bg-purple-50 text-purple-600",
                  extraction: "bg-red-50 text-red-600",
                  whitening: "bg-indigo-50 text-indigo-600",
                  emergency: "bg-orange-50 text-orange-600",
                };
                const color =
                  iconColors[a.procedure_type] || "bg-gray-50 text-gray-600";
                return (
                  <div
                    key={a.id}
                    className="flex items-center gap-3 group cursor-pointer"
                  >
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center ${color} group-hover:opacity-80 transition-opacity`}
                    >
                      <CalendarDays className="w-5 h-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-gray-800 truncate">
                        {a.patient_name || "Unknown"}
                      </p>
                      <p className="text-[10px] text-gray-400 capitalize">
                        {a.procedure_type} ·{" "}
                        {new Date(a.start_time).toLocaleDateString([], {
                          month: "short",
                          day: "numeric",
                        })}
                      </p>
                    </div>
                    <StatusBadge status={a.status} />
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>

      {/* ── Bottom Row ── */}
      <section className="grid grid-cols-12 gap-8">
        {/* Provider List */}
        <div className="col-span-6 bg-white rounded-[32px] p-6 border border-gray-100 custom-shadow">
          <div className="flex items-center justify-between mb-6">
            <h3 className="font-bold text-gray-800">Providers</h3>
          </div>
          <div className="space-y-5">
            {providers.map((p) => (
              <div key={p.id} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-brand-50 flex items-center justify-center text-brand-700 font-bold text-xs border border-brand-100">
                    {p.name
                      .split(" ")
                      .map((w) => w[0])
                      .join("")
                      .slice(0, 2)}
                  </div>
                  <div>
                    <p className="text-xs font-bold text-gray-800 leading-none">
                      {p.name}
                    </p>
                    <p className="text-[10px] text-gray-400 mt-1">
                      {p.title}{" "}
                      {p.specialties && (
                        <span className="text-gray-600 font-medium">
                          · {p.specialties.split(",")[0]}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <span className="text-[9px] font-bold text-brand-600 bg-brand-50 px-2 py-0.5 rounded border border-brand-100">
                  Active
                </span>
              </div>
            ))}
            {providers.length === 0 && (
              <p className="text-sm text-gray-400 text-center">
                No providers
              </p>
            )}
          </div>
        </div>

        {/* Appointment Completion Gauge */}
        <div className="col-span-3 bg-white rounded-[32px] p-6 border border-gray-100 custom-shadow flex flex-col items-center">
          <div className="w-full text-left">
            <h3 className="font-bold text-gray-800 mb-6">Completion Rate</h3>
          </div>
          <div className="relative mt-4">
            <GaugeChart
              value={
                appointments.length > 0
                  ? Math.round(
                      (appointments.filter((a) => a.status === "completed")
                        .length /
                        appointments.length) *
                        100
                    )
                  : 0
              }
            />
          </div>
          <div className="flex gap-4 mt-8">
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500">
              <div className="w-2.5 h-2.5 bg-brand-700 rounded-full" />{" "}
              Completed
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500">
              <div className="w-2.5 h-2.5 bg-blue-400 rounded-full" />{" "}
              Scheduled
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-500">
              <div className="w-2.5 h-2.5 bg-gray-200 rounded-full" />{" "}
              Cancelled
            </div>
          </div>
        </div>

        {/* Call Stats / Timer-style card */}
        <div className="col-span-3 bg-brand-950 rounded-[32px] p-6 text-white custom-shadow relative overflow-hidden">
          <div className="relative z-10 flex flex-col h-full">
            <h3 className="font-bold text-sm mb-6 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Call Summary
            </h3>
            <div className="flex-1 flex flex-col items-center justify-center">
              <p className="text-5xl font-extrabold tracking-tight mb-2">
                {totalCalls}
              </p>
              <p className="text-sm text-brand-200 mb-6">Calls Handled</p>
              <div className="flex gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold">{activeCalls}</p>
                  <p className="text-[10px] text-brand-300">Active</p>
                </div>
                <div className="w-px bg-brand-700" />
                <div>
                  <p className="text-2xl font-bold">
                    {totalCalls - activeCalls}
                  </p>
                  <p className="text-[10px] text-brand-300">Ended</p>
                </div>
              </div>
            </div>
          </div>
          {/* Background wave pattern */}
          <div className="absolute inset-0 pointer-events-none opacity-20">
            <svg
              className="h-full w-full"
              preserveAspectRatio="none"
              viewBox="0 0 100 100"
            >
              <path
                d="M0 100 Q 25 20 50 100 T 100 100"
                fill="none"
                stroke="white"
                strokeWidth="2"
              />
              <path
                d="M0 90 Q 25 10 50 90 T 100 90"
                fill="none"
                stroke="white"
                strokeWidth="2"
              />
            </svg>
          </div>
        </div>
      </section>
    </main>
  );
}

/* ── Helpers ── */

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    scheduled:
      "text-[9px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-100",
    completed:
      "text-[9px] font-bold text-brand-600 bg-brand-50 px-2 py-0.5 rounded border border-brand-100",
    cancelled:
      "text-[9px] font-bold text-red-500 bg-red-50 px-2 py-0.5 rounded border border-red-100",
    no_show:
      "text-[9px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-100",
  };
  return (
    <span
      className={
        styles[status] ||
        "text-[9px] font-bold text-gray-500 bg-gray-50 px-2 py-0.5 rounded border border-gray-100"
      }
    >
      {status.replace("_", " ")}
    </span>
  );
}

function GaugeChart({ value }: { value: number }) {
  // Rotation: 0% = -90deg (left), 100% = 90deg (right)
  const rotation = -90 + (value / 100) * 180;
  return (
    <div className="relative">
      <div
        className="w-[180px] h-[90px] rounded-t-full border-[18px] border-gray-200 border-b-0 relative overflow-hidden"
      >
        <div
          className="absolute top-[-18px] left-[-18px] w-[180px] h-[90px] rounded-t-full border-[18px] border-brand-700 border-b-0"
          style={{
            transformOrigin: "bottom center",
            transform: `rotate(${rotation - 90}deg)`,
            clipPath: "inset(0 0 0 0)",
          }}
        />
      </div>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <p className="text-3xl font-extrabold text-gray-900 leading-none">
          {value}%
        </p>
        <p className="text-[10px] text-gray-400 mt-1">Completed</p>
      </div>
    </div>
  );
}
