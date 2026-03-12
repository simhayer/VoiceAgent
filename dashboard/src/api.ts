const API_BASE = "http://localhost:8000";

export async function fetchPatients() {
  const res = await fetch(`${API_BASE}/admin/patients`);
  if (!res.ok) throw new Error("Failed to fetch patients");
  return res.json();
}

export async function fetchProviders() {
  const res = await fetch(`${API_BASE}/admin/providers`);
  if (!res.ok) throw new Error("Failed to fetch providers");
  return res.json();
}

export async function fetchAppointments(params?: {
  status?: string;
  date_from?: string;
  date_to?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.date_from) qs.set("date_from", params.date_from);
  if (params?.date_to) qs.set("date_to", params.date_to);
  const res = await fetch(`${API_BASE}/admin/appointments?${qs.toString()}`);
  if (!res.ok) throw new Error("Failed to fetch appointments");
  return res.json();
}

export async function cancelAppointment(id: string) {
  const res = await fetch(`${API_BASE}/admin/appointments/${id}/cancel`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to cancel appointment");
  return res.json();
}

export async function fetchOfficeConfig(category?: string) {
  const qs = category ? `?category=${category}` : "";
  const res = await fetch(`${API_BASE}/admin/office-config${qs}`);
  if (!res.ok) throw new Error("Failed to fetch office config");
  return res.json();
}

export async function upsertOfficeConfig(
  key: string,
  value: string,
  category = "general"
) {
  const res = await fetch(
    `${API_BASE}/admin/office-config/${key}?value=${encodeURIComponent(value)}&category=${encodeURIComponent(category)}`,
    { method: "PUT" }
  );
  if (!res.ok) throw new Error("Failed to upsert office config");
  return res.json();
}

export async function fetchCallLogs() {
  const res = await fetch(`${API_BASE}/admin/call-logs`);
  if (!res.ok) throw new Error("Failed to fetch call logs");
  return res.json();
}
