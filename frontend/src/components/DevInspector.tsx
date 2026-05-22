import { useState } from "react";

import type { ChatMessage, StateDelta, TimestampedEvent } from "../types";

type Tab = "state" | "messages" | "events";

interface Props {
  lastState: StateDelta;
  messages: ChatMessage[];
  events: TimestampedEvent[];
  threadId: string;
}

const EVENT_COLOR: Record<string, string> = {
  node_start: "text-blue-500",
  node_end: "text-emerald-500",
  interrupt: "text-amber-500",
  final_message: "text-violet-500",
  error: "text-red-500",
  ping: "text-slate-400",
};

export function DevInspector({ lastState, messages, events, threadId }: Props) {
  const [tab, setTab] = useState<Tab>("state");

  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col overflow-hidden">
      <div className="flex border-b border-slate-200 dark:border-slate-800 text-xs">
        <TabButton active={tab === "state"} onClick={() => setTab("state")}>
          State
        </TabButton>
        <TabButton active={tab === "messages"} onClick={() => setTab("messages")}>
          Messages
          <Badge>{messages.length}</Badge>
        </TabButton>
        <TabButton active={tab === "events"} onClick={() => setTab("events")}>
          Events
          <Badge>{events.length}</Badge>
        </TabButton>
      </div>

      <div className="p-3 overflow-y-auto" style={{ maxHeight: 320 }}>
        {tab === "state" && <StateView lastState={lastState} threadId={threadId} />}
        {tab === "messages" && <MessagesView messages={messages} />}
        {tab === "events" && <EventsView events={events} />}
      </div>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "flex-1 px-3 py-2 flex items-center justify-center gap-1.5 transition-colors",
        active
          ? "border-b-2 border-blue-500 text-slate-900 dark:text-slate-100 font-semibold"
          : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/60",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] bg-slate-200 dark:bg-slate-700 rounded px-1.5 py-0.5">
      {children}
    </span>
  );
}

function StateView({ lastState, threadId }: { lastState: StateDelta; threadId: string }) {
  const rows: [string, string | number | null | undefined][] = [
    ["thread_id", threadId],
    ["company_name", lastState.company_name ?? null],
    ["clarity_status", lastState.clarity_status ?? null],
    ["confidence_score", lastState.confidence_score ?? null],
    ["attempts", lastState.attempts ?? 0],
    ["validation_result", lastState.validation_result ?? null],
    ["validation_feedback", lastState.validation_feedback ?? null],
  ];
  return (
    <dl className="text-xs font-mono space-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-3">
          <dt className="text-slate-500 dark:text-slate-400 shrink-0">{k}</dt>
          <dd
            className="text-right text-slate-800 dark:text-slate-200 truncate max-w-[60%]"
            title={v == null ? "—" : String(v)}
          >
            {v == null || v === "" ? (
              <span className="text-slate-300 dark:text-slate-600">null</span>
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MessagesView({ messages }: { messages: ChatMessage[] }) {
  if (messages.length === 0) {
    return (
      <div className="text-xs italic text-slate-400 dark:text-slate-500">
        No messages yet — LangChain message history will appear here as turns happen.
      </div>
    );
  }
  return (
    <ol className="text-xs space-y-2">
      {messages.map((m, i) => (
        <li
          key={m.id}
          className="border-l-2 border-slate-200 dark:border-slate-700 pl-2 py-0.5"
        >
          <div className="font-mono text-[10px] text-slate-500 dark:text-slate-400 flex justify-between">
            <span>
              #{i} · {m.role === "user" ? "HumanMessage" : "AIMessage"}
            </span>
            <span>{new Date(m.ts).toLocaleTimeString()}</span>
          </div>
          <div className="whitespace-pre-wrap break-words text-slate-800 dark:text-slate-200">
            {m.content.length > 240 ? m.content.slice(0, 240) + "…" : m.content}
          </div>
        </li>
      ))}
    </ol>
  );
}

function EventsView({ events }: { events: TimestampedEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="text-xs italic text-slate-400 dark:text-slate-500">
        No SSE events yet — every <code>data:</code> frame from <code>POST /chat</code>{" "}
        will appear here as it arrives.
      </div>
    );
  }
  return (
    <ol className="text-[11px] font-mono space-y-1.5">
      {events.map((e) => {
        const ts = new Date(e.ts).toISOString().slice(11, 23);
        const color = EVENT_COLOR[e.event.type] ?? "text-slate-500";
        const summary =
          e.event.node ??
          e.event.question ??
          (e.event.content ? "(final_message)" : null) ??
          e.event.message ??
          "";
        return (
          <li key={e.id} className="leading-tight">
            <div className="flex items-baseline gap-2">
              <span className="text-slate-400 dark:text-slate-500">{ts}</span>
              <span className={`${color} font-semibold`}>{e.event.type}</span>
              {summary && <span className="text-slate-700 dark:text-slate-300">{summary}</span>}
            </div>
            {e.event.state_delta && Object.keys(e.event.state_delta).length > 0 && (
              <pre className="ml-14 text-[10px] text-slate-500 dark:text-slate-400 whitespace-pre-wrap break-all">
                {JSON.stringify(e.event.state_delta)}
              </pre>
            )}
          </li>
        );
      })}
    </ol>
  );
}
