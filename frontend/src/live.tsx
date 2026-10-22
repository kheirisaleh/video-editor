import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

export interface LiveEvent {
  id: number;
  type: "workflow" | "step" | "log";
  workflow_id: string | null;
  payload: Record<string, unknown>;
  at: string | null;
}

type Listener = (event: LiveEvent) => void;

interface LiveContextValue {
  connected: boolean;
  subscribe: (listener: Listener) => () => void;
}

const LiveContext = createContext<LiveContextValue | null>(null);

/**
 * One WebSocket for the whole app. After a reconnect it resumes from the last
 * seen event id, so no progress update is lost while the phone was asleep.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const listeners = useRef(new Set<Listener>());
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let lastId: number | null = null;
    let retry = 0;
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const after = lastId === null ? "" : `?after=${lastId}`;
      socket = new WebSocket(`${proto}://${location.host}/api/live${after}`);
      socket.onopen = () => {
        retry = 0;
        setConnected(true);
      };
      socket.onmessage = (msg) => {
        const data = JSON.parse(msg.data);
        if (data.type === "hello") {
          lastId = data.id;
          return;
        }
        lastId = data.id;
        listeners.current.forEach((l) => l(data as LiveEvent));
      };
      socket.onclose = () => {
        setConnected(false);
        if (closed) return;
        retry = Math.min(retry + 1, 6);
        timer = window.setTimeout(connect, 500 * 2 ** (retry - 1));
      };
    };

    connect();
    const onVisible = () => {
      if (document.visibilityState === "visible" && socket?.readyState === WebSocket.CLOSED) {
        window.clearTimeout(timer);
        connect();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      closed = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      socket?.close();
    };
  }, []);

  const subscribe = (listener: Listener) => {
    listeners.current.add(listener);
    return () => listeners.current.delete(listener);
  };

  return <LiveContext.Provider value={{ connected, subscribe }}>{children}</LiveContext.Provider>;
}

export function useLive(listener: Listener) {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive outside LiveProvider");
  const ref = useRef(listener);
  ref.current = listener;
  useEffect(() => ctx.subscribe((e) => ref.current(e)), [ctx]);
}

export function useLiveConnected(): boolean {
  return useContext(LiveContext)?.connected ?? false;
}
