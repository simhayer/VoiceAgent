// ── Shared types ──

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool_start" | "tool_end";
  content: string;
  timestamp: string;
  toolName?: string;
  toolArgs?: unknown;
  toolCallId?: string;
}

export interface CallSession {
  callSid: string;
  callerPhone: string;
  startTime: string;
  status: "active" | "ended";
  messages: ChatMessage[];
}

// ── API models ──

export interface Patient {
  id: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string | null;
  date_of_birth: string | null;
  insurance_provider: string | null;
}

export interface Provider {
  id: string;
  name: string;
  title: string;
  specialties: string | null;
}

export interface Appointment {
  id: string;
  provider_id: string;
  provider_name: string | null;
  patient_name: string | null;
  patient_phone: string | null;
  procedure_type: string;
  duration_minutes: number;
  start_time: string;
  end_time: string;
  status: string;
  notes: string | null;
}

export interface OfficeConfigEntry {
  key: string;
  value: string;
  category: string;
}

// ── Navigation ──

export type Page =
  | "dashboard"
  | "clients"
  | "calls"
  | "appointments"
  | "providers"
  | "settings";
