import { useEffect, useState, useRef } from "react";
import {
  Users,
  Search,
  Phone as PhoneIcon,
  MessageSquare,
  Bot,
  User,
  Loader2,
  ChevronLeft,
} from "lucide-react";
import { fetchPatients } from "../api";
import type { Patient, CallSession, ChatMessage } from "../types";

interface Props {
  sessions: Record<string, CallSession>;
}

export default function ClientsPage({ sessions }: Props) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedPhone, setSelectedPhone] = useState<string | null>(null);
  const [selectedCallSid, setSelectedCallSid] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchPatients()
      .then(setPatients)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [selectedCallSid, sessions]);

  // ── Build a map: phone → CallSession[] ──
  const sessionsByPhone: Record<string, CallSession[]> = {};
  Object.values(sessions).forEach((s) => {
    const phone = s.callerPhone;
    if (!sessionsByPhone[phone]) sessionsByPhone[phone] = [];
    sessionsByPhone[phone].push(s);
  });
  Object.values(sessionsByPhone).forEach((arr) =>
    arr.sort(
      (a, b) =>
        new Date(b.startTime).getTime() - new Date(a.startTime).getTime()
    )
  );

  // ── Build client list ──
  interface ClientEntry {
    id: string;
    name: string;
    phone: string;
    isPatient: boolean;
    hasActiveCall: boolean;
    lastMessageTime: string | null;
    lastMessagePreview: string | null;
    totalMessages: number;
  }

  const clientMap = new Map<string, ClientEntry>();

  patients.forEach((p) => {
    const chats = sessionsByPhone[p.phone] || [];
    const lastSession = chats[0];
    const lastMsg = lastSession?.messages[lastSession.messages.length - 1];
    clientMap.set(p.phone, {
      id: p.id,
      name: `${p.first_name} ${p.last_name}`,
      phone: p.phone,
      isPatient: true,
      hasActiveCall: chats.some((c) => c.status === "active"),
      lastMessageTime: lastMsg?.timestamp ?? lastSession?.startTime ?? null,
      lastMessagePreview: lastMsg?.content ?? null,
      totalMessages: chats.reduce((n, c) => n + c.messages.length, 0),
    });
  });

  Object.entries(sessionsByPhone).forEach(([phone, chats]) => {
    if (clientMap.has(phone)) return;
    const lastSession = chats[0];
    const lastMsg = lastSession?.messages[lastSession.messages.length - 1];
    clientMap.set(phone, {
      id: phone,
      name: phone,
      phone,
      isPatient: false,
      hasActiveCall: chats.some((c) => c.status === "active"),
      lastMessageTime: lastMsg?.timestamp ?? lastSession?.startTime ?? null,
      lastMessagePreview: lastMsg?.content ?? null,
      totalMessages: chats.reduce((n, c) => n + c.messages.length, 0),
    });
  });

  let clients = Array.from(clientMap.values());
  clients.sort((a, b) => {
    if (a.hasActiveCall !== b.hasActiveCall) return a.hasActiveCall ? -1 : 1;
    if (a.lastMessageTime && b.lastMessageTime)
      return (
        new Date(b.lastMessageTime).getTime() -
        new Date(a.lastMessageTime).getTime()
      );
    return a.name.localeCompare(b.name);
  });

  if (search.trim()) {
    const q = search.toLowerCase();
    clients = clients.filter(
      (c) =>
        c.name.toLowerCase().includes(q) || c.phone.toLowerCase().includes(q)
    );
  }

  const selectedClientChats = selectedPhone
    ? sessionsByPhone[selectedPhone] || []
    : [];
  const selectedSession = selectedCallSid
    ? sessions[selectedCallSid] ?? null
    : null;
  const selectedClient = selectedPhone
    ? clientMap.get(selectedPhone) ?? null
    : null;

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white">
        <div className="animate-spin w-8 h-8 border-4 border-brand-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Page Header */}
      <div className="px-8 py-6 border-b border-gray-100">
        <h1 className="text-2xl font-extrabold text-gray-900 flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-brand-50 flex items-center justify-center">
            <Users className="w-5 h-5 text-brand-600" />
          </div>
          Clients
        </h1>
        <p className="text-sm text-gray-400 mt-1 ml-[52px]">
          View all clients and their conversation history
        </p>
      </div>

      {/* Body: 3-column layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Column 1: Client list */}
        <div className="w-80 border-r border-gray-100 bg-gray-50/50 flex flex-col shrink-0">
          <div className="p-3 border-b border-gray-100">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search clients..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 text-sm border-none rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {clients.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                <Users className="w-8 h-8 mb-2 opacity-20" />
                <p className="text-sm">No clients found</p>
              </div>
            ) : (
              clients.map((client) => {
                const isSelected = selectedPhone === client.phone;
                return (
                  <button
                    key={client.id}
                    onClick={() => {
                      setSelectedPhone(client.phone);
                      setSelectedCallSid(null);
                    }}
                    className={`w-full text-left p-4 border-b border-gray-100/60 transition-all ${
                      isSelected
                        ? "bg-brand-50 border-l-4 border-l-brand-500"
                        : "hover:bg-white border-l-4 border-l-transparent"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 flex items-center justify-center shrink-0">
                          <User className="w-5 h-5 text-gray-400" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-bold text-gray-800 truncate">
                              {client.name}
                            </p>
                            {client.hasActiveCall && (
                              <span className="shrink-0 flex items-center gap-1 text-[9px] font-bold uppercase bg-brand-100 text-brand-700 px-2 py-0.5 rounded-full border border-brand-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
                                Active
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-400 flex items-center gap-1 mt-0.5">
                            <PhoneIcon className="w-3 h-3" />
                            {client.phone}
                          </p>
                        </div>
                      </div>
                      {client.lastMessageTime && (
                        <span className="text-[10px] text-gray-400 shrink-0 mt-1">
                          {new Date(client.lastMessageTime).toLocaleTimeString(
                            [],
                            { hour: "2-digit", minute: "2-digit" }
                          )}
                        </span>
                      )}
                    </div>
                    {client.lastMessagePreview && (
                      <p className="text-xs text-gray-400 mt-2 truncate pl-[52px]">
                        {client.lastMessagePreview}
                      </p>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Column 2: Conversations for selected client */}
        {selectedPhone && !selectedCallSid ? (
          <div className="w-80 border-r border-gray-100 bg-gray-50/30 flex flex-col shrink-0">
            <div className="px-4 py-3 border-b border-gray-100 bg-white">
              <h3 className="text-sm font-bold text-gray-800">
                Conversations
              </h3>
              <p className="text-xs text-gray-400">
                {selectedClientChats.length} call
                {selectedClientChats.length !== 1 ? "s" : ""}
              </p>
            </div>
            <div className="flex-1 overflow-y-auto">
              {selectedClientChats.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                  <MessageSquare className="w-8 h-8 mb-2 opacity-20" />
                  <p className="text-sm">No conversations yet</p>
                </div>
              ) : (
                selectedClientChats.map((chat) => (
                  <button
                    key={chat.callSid}
                    onClick={() => setSelectedCallSid(chat.callSid)}
                    className="w-full text-left p-4 border-b border-gray-100 hover:bg-white transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-bold text-gray-800">
                        {new Date(chat.startTime).toLocaleDateString([], {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                      {chat.status === "active" ? (
                        <span className="flex items-center gap-1 text-[9px] font-bold uppercase bg-brand-100 text-brand-700 px-2 py-0.5 rounded-full border border-brand-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
                          Live
                        </span>
                      ) : (
                        <span className="text-[9px] font-bold uppercase bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full border border-gray-200">
                          Ended
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400">
                      {new Date(chat.startTime).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}{" "}
                      · {chat.messages.length} messages
                    </p>
                    {chat.messages.length > 0 && (
                      <p className="text-xs text-gray-400 mt-1 truncate">
                        {chat.messages[chat.messages.length - 1].content}
                      </p>
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        ) : null}

        {/* Column 3: Chat transcript */}
        <div className="flex-1 flex flex-col bg-gray-50/50 overflow-hidden">
          {selectedSession ? (
            <>
              {/* Chat header */}
              <div className="h-16 px-6 bg-white border-b border-gray-100 flex items-center gap-3 shrink-0">
                <button
                  onClick={() => setSelectedCallSid(null)}
                  className="p-1.5 hover:bg-gray-100 rounded-xl transition lg:hidden"
                >
                  <ChevronLeft className="w-5 h-5 text-gray-500" />
                </button>
                <div className="w-10 h-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center">
                  <User className="w-5 h-5 text-brand-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-bold text-gray-900 truncate">
                    {selectedClient?.name ?? selectedSession.callerPhone}
                  </h3>
                  <p className="text-xs text-gray-400 flex items-center gap-1">
                    {selectedSession.status === "active" ? (
                      <>
                        <span className="w-1.5 h-1.5 bg-brand-500 rounded-full" />
                        Call in progress
                      </>
                    ) : (
                      "Call ended"
                    )}
                  </p>
                </div>
                <span className="text-[10px] text-gray-300 font-mono bg-gray-50 px-2 py-1 rounded-lg">
                  {selectedSession.callSid.slice(0, 8)}…
                </span>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-4 max-w-3xl mx-auto pb-4">
                  {selectedSession.messages.map((msg) => renderMessage(msg))}
                  <div ref={messagesEndRef} />
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
              <div className="w-20 h-20 rounded-[28px] bg-gray-100 flex items-center justify-center mb-4">
                <MessageSquare className="w-10 h-10 text-gray-300" />
              </div>
              <p className="text-lg font-bold text-gray-500">
                {selectedPhone
                  ? "Select a conversation"
                  : "Select a client to view chats"}
              </p>
              <p className="text-sm text-gray-400 mt-1">
                Conversations will appear here
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/* ── Message renderer ── */

function renderMessage(msg: ChatMessage) {
  if (msg.role === "tool_start") {
    return (
      <div key={msg.id} className="flex justify-center my-4">
        <div className="bg-white border border-gray-100 text-gray-500 text-xs px-4 py-2 rounded-2xl flex items-center gap-2 custom-shadow font-medium animate-pulse">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />
          Agent checking {msg.toolName}…
        </div>
      </div>
    );
  }
  if (msg.role === "tool_end") return null;

  const isUser = msg.role === "user";
  return (
    <div
      key={msg.id}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`flex max-w-[80%] ${isUser ? "flex-row-reverse" : "flex-row"} items-end gap-2`}
      >
        {!isUser && (
          <div className="w-8 h-8 rounded-xl bg-brand-50 border border-brand-100 shrink-0 flex items-center justify-center mb-1">
            <Bot className="w-4 h-4 text-brand-600" />
          </div>
        )}
        <div
          className={`relative px-4 py-2.5 text-[15px] leading-relaxed ${
            isUser
              ? "bg-brand-600 text-white rounded-2xl rounded-br-md"
              : "bg-white text-gray-800 rounded-2xl rounded-bl-md border border-gray-100 custom-shadow"
          }`}
        >
          {msg.content}
          <div
            className={`text-[10px] mt-1 text-right ${isUser ? "text-brand-200" : "text-gray-400"}`}
          >
            {new Date(msg.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
