import { useEffect, useState } from "react";
import { Settings, Save, Plus, FolderOpen } from "lucide-react";
import { fetchOfficeConfig, upsertOfficeConfig } from "../api";
import type { OfficeConfigEntry } from "../types";

export default function SettingsPage() {
  const [entries, setEntries] = useState<OfficeConfigEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newCategory, setNewCategory] = useState("general");

  const load = () => {
    setLoading(true);
    fetchOfficeConfig()
      .then((data) => {
        setEntries(data);
        const vals: Record<string, string> = {};
        data.forEach((e: OfficeConfigEntry) => {
          vals[e.key] = e.value;
        });
        setEditValues(vals);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleSave = async (key: string) => {
    const entry = entries.find((e) => e.key === key);
    if (!entry) return;
    setSaving(key);
    try {
      await upsertOfficeConfig(
        key,
        editValues[key] ?? entry.value,
        entry.category
      );
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(null);
    }
  };

  const handleAdd = async () => {
    if (!newKey.trim() || !newValue.trim()) return;
    setSaving("__new__");
    try {
      await upsertOfficeConfig(newKey, newValue, newCategory);
      setNewKey("");
      setNewValue("");
      setNewCategory("general");
      load();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(null);
    }
  };

  const categories = Array.from(new Set(entries.map((e) => e.category))).sort();

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="px-8 py-6 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gray-100 flex items-center justify-center">
            <Settings className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900">
              Office Settings
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Manage office configuration, FAQ, and policies
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8 space-y-6">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin w-8 h-8 border-4 border-brand-600 border-t-transparent rounded-full" />
          </div>
        ) : (
          <>
            {/* Add new entry */}
            <div className="bg-white rounded-[24px] border border-gray-100 custom-shadow p-6">
              <h3 className="font-bold text-gray-800 flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-xl bg-brand-50 flex items-center justify-center">
                  <Plus className="w-4 h-4 text-brand-600" />
                </div>
                Add Configuration
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <input
                  type="text"
                  placeholder="Key"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  className="text-sm border-none rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-gray-50"
                />
                <input
                  type="text"
                  placeholder="Value"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  className="text-sm border-none rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-gray-50 sm:col-span-2"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Category"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="text-sm border-none rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-gray-50 flex-1"
                  />
                  <button
                    onClick={handleAdd}
                    disabled={saving === "__new__"}
                    className="px-5 py-2.5 bg-brand-600 text-white text-sm font-bold rounded-xl hover:bg-brand-700 transition disabled:opacity-50 shrink-0"
                  >
                    Add
                  </button>
                </div>
              </div>
            </div>

            {/* Existing entries by category */}
            {categories.map((cat) => (
              <div
                key={cat}
                className="bg-white rounded-[24px] border border-gray-100 custom-shadow overflow-hidden"
              >
                <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
                  <FolderOpen className="w-4 h-4 text-gray-400" />
                  <h3 className="font-bold text-gray-800 capitalize">{cat}</h3>
                  <span className="text-[10px] font-bold text-gray-400 bg-gray-50 px-2 py-0.5 rounded-full border border-gray-100">
                    {entries.filter((e) => e.category === cat).length}
                  </span>
                </div>
                <div className="divide-y divide-gray-50">
                  {entries
                    .filter((e) => e.category === cat)
                    .map((entry) => (
                      <div
                        key={entry.key}
                        className="px-6 py-4 flex flex-col sm:flex-row sm:items-center gap-3"
                      >
                        <div className="sm:w-48 shrink-0">
                          <p className="text-sm font-bold text-gray-800">
                            {entry.key}
                          </p>
                        </div>
                        <div className="flex-1">
                          <textarea
                            rows={1}
                            value={editValues[entry.key] ?? entry.value}
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                [entry.key]: e.target.value,
                              }))
                            }
                            className="w-full text-sm border-none rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-gray-50 resize-y"
                          />
                        </div>
                        <button
                          onClick={() => handleSave(entry.key)}
                          disabled={saving === entry.key}
                          className="shrink-0 flex items-center gap-1.5 text-xs text-brand-600 hover:text-brand-800 font-bold transition disabled:opacity-50"
                        >
                          <Save className="w-3.5 h-3.5" />
                          {saving === entry.key ? "Saving…" : "Save"}
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            ))}

            {entries.length === 0 && (
              <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                <Settings className="w-10 h-10 mb-2 opacity-20" />
                <p className="text-sm">No configuration entries yet</p>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
