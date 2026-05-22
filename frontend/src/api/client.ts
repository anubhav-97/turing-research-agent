import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { SSEEvent, ThreadHistory } from "../types";

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface StreamHandlers {
  onEvent: (event: SSEEvent) => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
  signal?: AbortSignal;
}

async function streamPost(
  path: string,
  body: Record<string, unknown>,
  handlers: StreamHandlers,
): Promise<void> {
  await fetchEventSource(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal: handlers.signal,
    openWhenHidden: true,
    onmessage(ev) {
      if (!ev.data) return;
      try {
        const parsed = JSON.parse(ev.data) as SSEEvent;
        handlers.onEvent(parsed);
      } catch (err) {
        handlers.onError?.(err);
      }
    },
    onerror(err) {
      handlers.onError?.(err);
      throw err; // stop retrying
    },
    onclose() {
      handlers.onClose?.();
    },
  });
}

export function streamChat(
  threadId: string,
  message: string,
  handlers: StreamHandlers,
): Promise<void> {
  return streamPost("/chat", { thread_id: threadId, message }, handlers);
}

export function streamResume(
  threadId: string,
  clarification: string,
  handlers: StreamHandlers,
): Promise<void> {
  return streamPost(
    "/chat/resume",
    { thread_id: threadId, clarification },
    handlers,
  );
}

export async function fetchHistory(threadId: string): Promise<ThreadHistory | null> {
  const res = await fetch(`${BASE_URL}/threads/${encodeURIComponent(threadId)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`history fetch failed: ${res.status}`);
  return (await res.json()) as ThreadHistory;
}

export async function health(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export const API_BASE_URL = BASE_URL;
