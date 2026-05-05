"use client";
import { useEffect, useRef, useState } from "react";
import { getRealtimeUrl } from "@/lib/api";

export interface UseWebSocketReturn {
  connected: boolean;
}

export function useWebSocket(
  topics: string[],
  onMessage: (topic: string, payload: unknown) => void,
): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  // Keep a stable ref to the latest onMessage callback to avoid stale closures
  const onMessageRef = useRef(onMessage);
  // Keep a stable ref to the latest topics list so the reconnect logic reads current topics
  const topicsRef = useRef(topics);

  useEffect(() => {
    onMessageRef.current = onMessage;
    topicsRef.current = topics;
  }, [onMessage, topics]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let reconnectTimer: any = null;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(getRealtimeUrl());

      ws.onopen = () => {
        setConnected(true);
        for (const topic of topicsRef.current) {
          ws?.send(`subscribe:${topic}`);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          reconnectTimer = window.setTimeout(connect, 2500);
        }
      };

      ws.onerror = () => {
        setConnected(false);
      };

      ws.onmessage = event => {
        try {
          const message = JSON.parse(event.data as string) as {
            topic?: string;
            payload?: unknown;
          };
          if (message.topic && message.payload !== undefined) {
            onMessageRef.current(message.topic, message.payload);
          }
        } catch {
          // Ignore malformed realtime messages; REST polling remains the fallback.
        }
      };
    };

    connect();

    return () => {
      closed = true;
      setConnected(false);
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
    // topics is intentionally excluded: we use topicsRef to read fresh topics on reconnect
    // but we only want to reconnect when the topic strings themselves change (which would
    // change this component's identity anyway since qcResultId changes).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topics.join(",")]);

  return { connected };
}

export default useWebSocket;
