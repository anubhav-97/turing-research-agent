import { create } from "zustand";
import { nanoid } from "nanoid";

import { fetchHistory, streamChat, streamResume } from "../api/client";
import type {
  AgentNode,
  AgentTraceStep,
  ChatMessage,
  SSEEvent,
  StateDelta,
  TimestampedEvent,
} from "../types";

// Mirrors backend routing functions — derives a human-readable reason for why
// the graph picked the next node. Keeps the FE side of the contract honest.
function routingReasonFor(from: AgentNode, to: AgentNode, delta?: Partial<StateDelta>): string {
  if (from === "clarity") {
    return to === "clarification"
      ? `needs_clarification (no company)`
      : `clear (company=${delta?.company_name ?? "?"})`;
  }
  if (from === "research") {
    const c = delta?.confidence_score ?? 0;
    return to === "synthesis" ? `conf ${c} ≥ 6` : `conf ${c} < 6`;
  }
  if (from === "validator") {
    const v = delta?.validation_result;
    const a = delta?.attempts ?? 0;
    if (to === "research") return `insufficient · attempt ${a}/3`;
    if (v === "sufficient") return "sufficient";
    return `attempt cap reached (${a}/3)`;
  }
  if (from === "clarification") return "resumed → re-evaluate clarity";
  return "";
}

const THREAD_KEY = "turing.thread_id";
const THEME_KEY = "theme";
const ACTIVITY_COLLAPSED_KEY = "turing.activity_collapsed";

function getOrCreateThreadId(): string {
  const existing = localStorage.getItem(THREAD_KEY);
  if (existing) return existing;
  const fresh = `t-${nanoid(12)}`;
  localStorage.setItem(THREAD_KEY, fresh);
  return fresh;
}

interface ChatState {
  threadId: string;
  messages: ChatMessage[];
  trace: AgentTraceStep[];
  events: TimestampedEvent[];
  activeNode: AgentNode | null;
  pendingQuestion: string | null;
  streaming: boolean;
  lastState: StateDelta;
  errorMessage: string | null;
  theme: "light" | "dark";
  activityCollapsed: boolean;

  // actions
  sendMessage: (text: string) => Promise<void>;
  resume: (clarification: string) => Promise<void>;
  hydrateFromServer: () => Promise<void>;
  resetThread: () => void;
  toggleTheme: () => void;
  clearError: () => void;
  clearTrace: () => void;
  toggleActivityCollapsed: () => void;
}

function applyTheme(theme: "light" | "dark") {
  if (theme === "dark") document.documentElement.classList.add("dark");
  else document.documentElement.classList.remove("dark");
  localStorage.setItem(THEME_KEY, theme);
}

const initialTheme: "light" | "dark" =
  (localStorage.getItem(THEME_KEY) as "light" | "dark" | null) ??
  (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

applyTheme(initialTheme);

const initialActivityCollapsed = localStorage.getItem(ACTIVITY_COLLAPSED_KEY) === "1";

export const useChat = create<ChatState>((set, get) => ({
  threadId: getOrCreateThreadId(),
  messages: [],
  trace: [],
  events: [],
  activeNode: null,
  pendingQuestion: null,
  streaming: false,
  lastState: {},
  errorMessage: null,
  theme: initialTheme,
  activityCollapsed: initialActivityCollapsed,

  resetThread: () => {
    localStorage.removeItem(THREAD_KEY);
    set({
      threadId: getOrCreateThreadId(),
      messages: [],
      trace: [],
      events: [],
      activeNode: null,
      pendingQuestion: null,
      streaming: false,
      lastState: {},
      errorMessage: null,
    });
  },

  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    set({ theme: next });
  },

  clearError: () => set({ errorMessage: null }),

  clearTrace: () =>
    set({ trace: [], events: [], lastState: {}, activeNode: null, errorMessage: null }),

  toggleActivityCollapsed: () => {
    const next = !get().activityCollapsed;
    localStorage.setItem(ACTIVITY_COLLAPSED_KEY, next ? "1" : "0");
    set({ activityCollapsed: next });
  },

  hydrateFromServer: async () => {
    const { threadId } = get();
    try {
      const hist = await fetchHistory(threadId);
      if (!hist) return;
      const messages: ChatMessage[] = hist.messages
        .filter((m) => m.role !== "system")
        .map((m, i) => ({
          id: `${threadId}-h-${i}`,
          role: m.role,
          content: m.content,
          ts: Date.now() - (hist.messages.length - i) * 1000,
        }));
      set({
        messages,
        pendingQuestion: hist.interrupted ? hist.pending_question ?? null : null,
      });
    } catch (err) {
      console.warn("hydrate failed", err);
    }
  },

  sendMessage: async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || get().streaming) return;

    const { threadId } = get();
    const userMsg: ChatMessage = {
      id: nanoid(8),
      role: "user",
      content: trimmed,
      ts: Date.now(),
    };
    set((s) => ({
      messages: [...s.messages, userMsg],
      trace: [],
      events: [],
      activeNode: null,
      pendingQuestion: null,
      streaming: true,
      lastState: {},
      errorMessage: null,
    }));

    try {
      await streamChat(threadId, trimmed, makeHandlers(set));
    } catch (err) {
      console.error("chat stream failed", err);
      set({ errorMessage: humanizeError(err), streaming: false });
    }
  },

  resume: async (clarification: string) => {
    const trimmed = clarification.trim();
    if (!trimmed || get().streaming) return;

    const { threadId } = get();
    const userMsg: ChatMessage = {
      id: nanoid(8),
      role: "user",
      content: trimmed,
      ts: Date.now(),
    };
    set((s) => ({
      messages: [...s.messages, userMsg],
      activeNode: null,
      pendingQuestion: null,
      streaming: true,
      errorMessage: null,
    }));

    try {
      await streamResume(threadId, trimmed, makeHandlers(set));
    } catch (err) {
      console.error("resume stream failed", err);
      set({ errorMessage: humanizeError(err), streaming: false });
    }
  },
}));

function makeHandlers(set: (fn: (s: ChatState) => Partial<ChatState>) => void) {
  return {
    onEvent: (event: SSEEvent) => {
      // Always record into the developer event log first
      set((s) => ({
        events: [
          ...s.events,
          { id: nanoid(8), ts: Date.now(), event },
        ],
      }));

      if (event.type === "node_start" && event.node) {
        const startedAt = Date.now();
        set((s) => {
          // Back-fill the previous (done) trace step's nextNode + routingReason
          // so the pill can render "→ research (clear)" etc.
          const trace = [...s.trace];
          for (let i = trace.length - 1; i >= 0; i--) {
            if (trace[i].status === "done" && !trace[i].nextNode) {
              trace[i] = {
                ...trace[i],
                nextNode: event.node!,
                routingReason: routingReasonFor(trace[i].node, event.node!, trace[i].delta),
              };
              break;
            }
          }
          return {
            activeNode: event.node!,
            trace: [...trace, { node: event.node!, startedAt, status: "running" }],
          };
        });
      } else if (event.type === "node_end" && event.node) {
        const endedAt = Date.now();
        set((s) => {
          const idx = [...s.trace].reverse().findIndex(
            (t) => t.node === event.node && t.status === "running",
          );
          if (idx === -1) return {};
          const realIdx = s.trace.length - 1 - idx;
          const next = [...s.trace];
          next[realIdx] = {
            ...next[realIdx],
            endedAt,
            status: "done",
            delta: event.state_delta,
          };
          return {
            trace: next,
            lastState: { ...s.lastState, ...(event.state_delta ?? {}) },
          };
        });
      } else if (event.type === "interrupt") {
        set(() => ({
          pendingQuestion: event.question ?? "Could you clarify?",
          streaming: false,
          activeNode: null,
        }));
      } else if (event.type === "final_message" && event.content) {
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: nanoid(8),
              role: "assistant",
              content: event.content!,
              ts: Date.now(),
            },
          ],
        }));
      } else if (event.type === "error") {
        set(() => ({
          errorMessage: event.message ?? "Unknown error from server",
        }));
      }
    },
    onClose: () => {
      set(() => ({ streaming: false, activeNode: null }));
    },
    onError: (err: unknown) => {
      set(() => ({
        streaming: false,
        activeNode: null,
        errorMessage: humanizeError(err),
      }));
    },
  };
}

function humanizeError(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return "Connection to the research server failed.";
}
