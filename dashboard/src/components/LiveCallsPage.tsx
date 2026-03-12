import { useRef, useEffect, useState, useMemo } from "react";
import {
  Phone,
  PhoneOff,
  User,
  Bot,
  Loader2,
  MessageSquare,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import type { CallSession, ChatMessage } from "../types";

interface Props {
  sessions: Record<string, CallSession>;
  wsStatus: "connecting" | "connected" | "error";
}

export default function LiveCallsPage({ sessions, wsStatus }: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [activeCallSid, setActiveCallSid] = useState<string | null>(null);

  const allSessions = useMemo(
    () =>
      Object.values(sessions).sort(
        (a, b) =>
          new Date(b.startTime).getTime() - new Date(a.startTime).getTime()
      ),
    [sessions]
  );

  const resolvedCallSid =
    activeCallSid && sessions[activeCallSid]
      ? activeCallSid
      : allSessions[0]?.callSid ?? null;

  const activeSession = resolvedCallSid ? sessions[resolvedCallSid] : null;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessions, resolvedCallSid]);

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="px-8 py-6 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-brand-50 flex items-center justify-center">
            <Phone className="w-5 h-5 text-brand-600" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900">
              Live Calls
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Real-time call transcripts
            </p>
          </div>
        </div>
        <WsStatusBadge status={wsStatus} />
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar: call list */}
        <div className="w-80 bg-gray-50/50 border-r border-gray-100 flex flex-col shrink-0">
          <div className="flex-1 overflow-y-auto">
            {allSessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                <MessageSquare className="w-8 h-8 mb-2 opacity-20" />
                <p className="text-sm">Waiting for calls…</p>
              </div>
            ) : (
              allSessions.map((session) => (
                <button
                  key={session.callSid}
                  onClick={() => setActiveCallSid(session.callSid)}
                  className={`w-full text-left p-4 border-b border-gray-100/60 transition-all ${
                    resolvedCallSid === session.callSid
                      ? "bg-brand-50 border-l-4 border-l-brand-500"
                      : "hover:bg-white border-l-4 border-l-transparent"
                  }`}
                >
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-bold text-gray-800 text-sm">
                      {session.callerPhone}
                    </span>
                    <span className="text-[10px] text-gray-400">
                      {new Date(session.startTime).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-400 truncate pr-4">
                      {session.messages.length > 0
                        ? session.messages[session.messages.length - 1].content
                        : "Connecting…"}
                    </span>
                    {session.status === "active" ? (
                      <span className="px-2 py-0.5 bg-brand-100 text-brand-700 text-[9px] uppercase font-bold rounded-full border border-brand-200 shrink-0 flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
                        Live
                      </span>
                    ) : (
                      <PhoneOff className="w-3 h-3 text-gray-400 shrink-0" />
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Chat area */}
        <div className="flex-1 flex flex-col bg-gray-50/50 overflow-hidden">
          {activeSession ? (
            <>
              <div className="h-16 px-6 bg-white border-b border-gray-100 flex items-center gap-3 shrink-0">
                <div className="w-10 h-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center">
                  <User className="w-5 h-5 text-brand-600" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900">
                    {activeSession.callerPhone}
                  </h3>
                  <p className="text-xs text-gray-400 flex items-center gap-1">
                    {activeSession.status === "active" ? (
                      <>
                        <span className="w-1.5 h-1.5 bg-brand-500 rounded-full" />
                        Call in progress
                      </>
                    ) : (
                      "Call ended"
                    )}
                  </p>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-4 max-w-3xl mx-auto pb-4">
                  {activeSession.messages.map((msg) => renderMessage(msg))}
                  <div ref={messagesEndRef} />
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
              <div className="w-20 h-20 rounded-[28px] bg-gray-100 flex items-center justify-center mb-4">
                <Phone className="w-10 h-10 text-gray-300" />
              </div>
              <p className="text-lg font-bold text-gray-500">
                No call selected
              </p>
              <p className="text-sm text-gray-400 mt-1">
                Select a call from the list to view the transcript
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/* ── Helpers ── */

function WsStatusBadge({
  status,
}: {
  status: "connecting" | "connected" | "error";
}) {
  if (status === "connected")
    return (
      <span className="flex items-center gap-1.5 text-xs text-brand-700 font-bold bg-brand-50 px-3 py-1.5 rounded-full border border-brand-100">
        <span className="w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
        Live
      </span>
    );
  if (status === "connecting")
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-600 font-bold bg-amber-50 px-3 py-1.5 rounded-full border border-amber-100">
        <Loader2 className="w-3 h-3 animate-spin" />
        Connecting
      </span>
    );
  return (
    <span className="flex items-center gap-1.5 text-xs text-red-600 font-bold bg-red-50 px-3 py-1.5 rounded-full border border-red-100">
      <AlertCircle className="w-3 h-3" />
      Offline
    </span>
  );
}

function renderMessage(msg: ChatMessage) {
  if (msg.role === "tool_start") {
    return (
      <div key={msg.id} className="flex justify-center my-3">
        <div className="bg-white border border-gray-100 text-gray-500 text-xs px-4 py-2 rounded-2xl flex items-center gap-2 custom-shadow font-medium animate-pulse">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />
          Checking {msg.toolName}…
        </div>
      </div>
    );
  }
  if (msg.role === "tool_end") {
    return (
      <div key={msg.id} className="flex justify-center my-3">
        <div className="bg-white border border-brand-100 text-brand-700 text-xs px-4 py-2 rounded-2xl flex items-center gap-2 font-medium">
          <CheckCircle2 className="w-3.5 h-3.5 text-brand-500" />
          Used {msg.toolName}
        </div>
      </div>
    );
  }

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
