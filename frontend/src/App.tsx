import { useEffect, useMemo, useRef } from "react";

import { AgentTimeline } from "./components/AgentTimeline";
import { ClarificationBanner } from "./components/ClarificationBanner";
import { ComposerInput } from "./components/ComposerInput";
import { DevInspector } from "./components/DevInspector";
import { GraphTopology } from "./components/GraphTopology";
import { Header } from "./components/Header";
import { MessageBubble } from "./components/MessageBubble";
import { SuggestedQueries } from "./components/SuggestedQueries";
import { ThinkingBubble } from "./components/ThinkingBubble";
import { ValidatorFeedback } from "./components/ValidatorFeedback";
import { useChat } from "./store/chat";
import type { AgentNode } from "./types";

export default function App() {
  const {
    threadId,
    messages,
    trace,
    events,
    activeNode,
    pendingQuestion,
    streaming,
    lastState,
    errorMessage,
    activityCollapsed,
    sendMessage,
    resume,
    hydrateFromServer,
    clearError,
    toggleActivityCollapsed,
  } = useChat();

  // Restore previous conversation on page load.
  useEffect(() => {
    hydrateFromServer();
  }, [hydrateFromServer]);

  // Auto-scroll to latest message.
  const bottomRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, trace.length, pendingQuestion]);

  const visited = useMemo(() => new Set<AgentNode>(trace.map((t) => t.node)), [trace]);
  const empty = messages.length === 0 && trace.length === 0;

  return (
    <div className="flex flex-col h-screen">
      <Header />

      <main className="flex-1 overflow-hidden flex flex-col lg:flex-row gap-4 p-4 max-w-7xl w-full mx-auto">
        {/* Left rail (visible on lg+): graph topology + dev inspector */}
        <aside className="hidden lg:flex flex-col gap-4 w-80 shrink-0 overflow-y-auto">
          <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">
              Graph Topology
            </h3>
            <div className="flex justify-center">
              <GraphTopology activeNode={activeNode} visitedNodes={visited} />
            </div>
          </section>

          <DevInspector
            lastState={lastState}
            messages={messages}
            events={events}
            threadId={threadId}
          />
        </aside>

        {/* Chat column */}
        <section className="flex-1 min-w-0 flex flex-col gap-3">
          {/* Trace bar (collapsible) */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <button
              type="button"
              onClick={toggleActivityCollapsed}
              aria-expanded={!activityCollapsed}
              aria-controls="agent-activity-body"
              className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-slate-50 dark:hover:bg-slate-800/40 rounded-lg transition-colors"
            >
              <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <span
                  className={`inline-block transition-transform ${
                    activityCollapsed ? "" : "rotate-90"
                  }`}
                >
                  ▶
                </span>
                Agent Activity
                {streaming && (
                  <span className="text-blue-500 normal-case font-normal">· streaming…</span>
                )}
                {activityCollapsed && trace.length > 0 && (
                  <span className="normal-case font-normal text-slate-500 dark:text-slate-400">
                    · {trace.length} step{trace.length === 1 ? "" : "s"}
                    {activeNode ? ` · ${activeNode}` : ""}
                  </span>
                )}
              </span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">
                {activityCollapsed ? "show" : "hide"}
              </span>
            </button>
            {!activityCollapsed && (
              <div
                id="agent-activity-body"
                className="px-4 pb-3 pt-1 space-y-2 border-t border-slate-100 dark:border-slate-800"
              >
                <AgentTimeline trace={trace} activeNode={activeNode} />
                <ValidatorFeedback trace={trace} />
              </div>
            )}
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
            {empty && <EmptyState onPick={sendMessage} disabled={streaming} />}
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {/* Live "thinking" indicator — visible while the graph is running
                and the assistant hasn't produced the final message yet. */}
            {streaming && messages[messages.length - 1]?.role === "user" && (
              <ThinkingBubble activeNode={activeNode} state={lastState} />
            )}
            {errorMessage && (
              <div className="rounded-md border border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-800 p-3 text-sm flex justify-between gap-3">
                <span className="text-red-700 dark:text-red-200">{errorMessage}</span>
                <button
                  onClick={clearError}
                  className="text-xs text-red-700 dark:text-red-300 underline"
                >
                  dismiss
                </button>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Composer */}
          <div className="space-y-3">
            {pendingQuestion && (
              <ClarificationBanner
                question={pendingQuestion}
                onResume={(answer) => void resume(answer)}
                disabled={streaming}
              />
            )}
            {!pendingQuestion && (
              <ComposerInput onSend={(t) => void sendMessage(t)} disabled={streaming} />
            )}
            {!empty && (
              <SuggestedQueries onPick={(t) => void sendMessage(t)} disabled={streaming} />
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

function EmptyState({
  onPick,
  disabled,
}: {
  onPick: (t: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-12 px-4">
      <div className="h-14 w-14 rounded-2xl bg-gradient-to-br from-blue-500 via-violet-500 to-emerald-500 flex items-center justify-center text-white text-2xl shadow mb-4">
        🔎
      </div>
      <h2 className="text-lg font-semibold mb-1">Ask about a company</h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mb-6">
        Four specialized agents collaborate to research, validate, and synthesize an
        answer. If your question is vague, the system pauses and asks you to clarify.
      </p>
      <SuggestedQueries onPick={onPick} disabled={disabled} />
    </div>
  );
}
