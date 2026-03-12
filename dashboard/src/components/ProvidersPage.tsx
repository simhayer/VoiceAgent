import { useEffect, useState } from "react";
import { Stethoscope, Calendar, Briefcase } from "lucide-react";
import { fetchProviders } from "../api";
import type { Provider } from "../types";

interface ProviderDetail extends Provider {
  availability?: {
    day_of_week: number;
    start_time: string;
    end_time: string;
  }[];
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetchProviders()
      .then(setProviders)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const loadDetail = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    try {
      const res = await fetch(`http://localhost:8000/admin/providers/${id}`);
      const data = await res.json();
      setProviders((prev) =>
        prev.map((p) =>
          p.id === id ? { ...p, availability: data.availability } : p
        )
      );
      setExpandedId(id);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="px-8 py-6 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-amber-50 flex items-center justify-center">
            <Stethoscope className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900">
              Providers
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Dental providers and their schedules
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin w-8 h-8 border-4 border-brand-600 border-t-transparent rounded-full" />
          </div>
        ) : providers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <Stethoscope className="w-10 h-10 mb-2 opacity-20" />
            <p className="text-sm">No providers found</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {providers.map((p) => (
              <div
                key={p.id}
                className="bg-white rounded-[24px] border border-gray-100 custom-shadow overflow-hidden transition-all hover:shadow-md"
              >
                <div className="p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-brand-50 flex items-center justify-center shrink-0 border border-brand-100">
                      <span className="text-brand-700 font-extrabold text-lg">
                        {p.name
                          .split(" ")
                          .map((w) => w[0])
                          .join("")
                          .slice(0, 2)}
                      </span>
                    </div>
                    <div>
                      <h3 className="font-extrabold text-gray-900">
                        {p.name}
                      </h3>
                      <p className="text-sm text-gray-400 flex items-center gap-1.5 mt-1">
                        <Briefcase className="w-3.5 h-3.5" />
                        {p.title}
                      </p>
                      {p.specialties && (
                        <div className="flex flex-wrap gap-1.5 mt-3">
                          {p.specialties.split(",").map((s) => (
                            <span
                              key={s}
                              className="text-[9px] uppercase font-bold bg-brand-50 text-brand-700 px-2 py-0.5 rounded-full border border-brand-100"
                            >
                              {s.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="border-t border-gray-100 px-6 py-4">
                  <button
                    onClick={() => loadDetail(p.id)}
                    className="text-xs text-brand-600 hover:text-brand-800 font-bold flex items-center gap-1.5 transition"
                  >
                    <Calendar className="w-3.5 h-3.5" />
                    {expandedId === p.id ? "Hide schedule" : "View schedule"}
                  </button>

                  {expandedId === p.id && p.availability && (
                    <div className="mt-3 space-y-1.5">
                      {p.availability.length === 0 ? (
                        <p className="text-xs text-gray-400">
                          No availability rules set.
                        </p>
                      ) : (
                        p.availability.map((rule, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between text-xs text-gray-600 bg-gray-50 px-4 py-2 rounded-xl"
                          >
                            <span className="font-bold text-gray-700">
                              {DAYS[rule.day_of_week] ??
                                `Day ${rule.day_of_week}`}
                            </span>
                            <span className="text-gray-400 font-medium">
                              {rule.start_time} – {rule.end_time}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
