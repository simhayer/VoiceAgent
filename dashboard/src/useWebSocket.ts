import { useEffect, useRef, useState, useCallback } from "react";
import type { CallSession, ChatMessage } from "./types";
import { fetchCallLogs } from "./api";

/**
 * Check if the last visible (user/assistant) message already has the same
 * content — prevents duplicates caused by the backend publishing the same
 * transcript twice.
 */
function isDuplicate(messages: ChatMessage[], role: string, text: string): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === role && m.content === text) return true;
    // Only look back through recent tool bubbles, stop at the first
    // real user/assistant message that doesn't match.
    if (m.role === "user" || m.role === "assistant") break;
  }
  return false;
}

export function useWebSocket() {
  const [sessions, setSessions] = useState<Record<string, CallSession>>({});
  const [wsStatus, setWsStatus] = useState<
    "connecting" | "connected" | "error"
  >("connecting");
  const wsRef = useRef<WebSocket | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      if (!data.call_sid) return;

      setSessions((prev) => {
        const currentSession: CallSession = prev[data.call_sid] || {
          callSid: data.call_sid,
          callerPhone: "Unknown",
          startTime: data.timestamp,
          status: "active",
          messages: [],
        };

        let newMessages = [...currentSession.messages];

        if (data.type === "call_started") {
          currentSession.callerPhone = data.caller_phone || "Unknown Caller";
          currentSession.status = "active";
        } else if (data.type === "call_ended") {
          currentSession.status = "ended";
        } else if (data.type === "user_transcript") {
          if (!isDuplicate(newMessages, "user", data.text)) {
            newMessages.push({
              id: crypto.randomUUID(),
              role: "user",
              content: data.text,
              timestamp: data.timestamp,
            });
          }
        } else if (data.type === "agent_transcript") {
          if (!isDuplicate(newMessages, "assistant", data.text)) {
            newMessages.push({
              id: crypto.randomUUID(),
              role: "assistant",
              content: data.text,
              timestamp: data.timestamp,
            });
          }
        } else if (data.type === "tool_start") {
          newMessages.push({
            id: crypto.randomUUID(),
            role: "tool_start",
            content: `Using tool: ${data.tool_name}`,
            timestamp: data.timestamp,
            toolName: data.tool_name,
            toolArgs: data.tool_args,
            toolCallId: data.tool_call_id,
          });
        } else if (data.type === "tool_end") {
          // Replace only the first matching tool_start with the same toolCallId
          let replaced = false;
          newMessages = newMessages.map((m) => {
            if (!replaced && m.role === "tool_start" && m.toolCallId === data.tool_call_id) {
              replaced = true;
              return { ...m, role: "tool_end" as const, content: `Used tool: ${data.tool_name}` };
            }
            return m;
          });
        }

        return {
          ...prev,
          [data.call_sid]: { ...currentSession, messages: newMessages },
        };
      });
    } catch (e) {
      console.error("Error parsing WS message", e);
    }
  }, []);

  useEffect(() => {
    // Load persisted call logs from the database on mount
    fetchCallLogs()
      .then((logs: Record<string, unknown>[]) => {
        const loaded: Record<string, CallSession> = {};
        for (const log of logs) {
          const sid = log.call_sid as string;
          const msgs = (log.messages as Record<string, unknown>[]) || [];
          const rawMsgs = msgs.map((m) => ({
              id: m.id as string,
              role: m.role as ChatMessage["role"],
              content: m.content as string,
              timestamp: m.timestamp as string,
              toolName: (m.tool_name as string) ?? undefined,
              toolArgs: (m.tool_args as unknown) ?? undefined,
            }));
          // For completed tools the DB has both tool_start and tool_end.
          // Keep only tool_end rows; drop their paired tool_start.
          const endIds = new Set<string>();
          const messages: ChatMessage[] = [];
          // First pass: collect indices of tool_start that precede a tool_end
          for (let i = 0; i < rawMsgs.length; i++) {
            if (rawMsgs[i].role === "tool_end") {
              // Find the nearest preceding tool_start with same toolName
              for (let j = i - 1; j >= 0; j--) {
                if (rawMsgs[j].role === "tool_start" && rawMsgs[j].toolName === rawMsgs[i].toolName && !endIds.has(rawMsgs[j].id)) {
                  endIds.add(rawMsgs[j].id);
                  break;
                }
              }
            }
          }
          for (const m of rawMsgs) {
            if (endIds.has(m.id)) continue; // skip paired tool_start
            messages.push(m);
          }
          loaded[sid] = {
            callSid: sid,
            callerPhone: (log.caller_phone as string) || "Unknown",
            startTime: log.started_at as string,
            status: log.status === "active" ? "active" : "ended",
            messages,
          };
        }
        setSessions((prev) => ({ ...loaded, ...prev }));
      })
      .catch((err) => console.error("Failed to load call logs:", err));
  }, []);

  useEffect(() => {
    const connectWs = () => {
      const ws = new WebSocket("ws://localhost:8000/dashboard/ws");
      wsRef.current = ws;
      ws.onopen = () => setWsStatus("connected");
      ws.onclose = () => {
        setWsStatus("error");
        setTimeout(connectWs, 3000);
      };
      ws.onerror = () => setWsStatus("error");
      ws.onmessage = handleMessage;
    };

    connectWs();
    return () => {
      wsRef.current?.close();
    };
  }, [handleMessage]);

  return { sessions, wsStatus };
}
