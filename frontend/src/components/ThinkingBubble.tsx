import type { AgentNode, StateDelta } from "../types";

const NODE_LABEL: Record<AgentNode, string> = {
  clarity: "Reviewing your question",
  clarification: "Waiting for your reply",
  research: "Researching",
  validator: "Validating findings",
  synthesis: "Writing the answer",
};

const NODE_EMOJI: Record<AgentNode, string> = {
  clarity: "🧠",
  clarification: "❓",
  research: "🔍",
  validator: "🕵️",
  synthesis: "✍️",
};

interface Props {
  activeNode: AgentNode | null;
  state: StateDelta;
}

export function ThinkingBubble({ activeNode, state }: Props) {
  const label = activeNode ? NODE_LABEL[activeNode] : "Thinking";
  const emoji = activeNode ? NODE_EMOJI[activeNode] : "💭";

  // Build a contextual suffix from the state so the user sees specifics
  // (e.g. "Researching Tesla · attempt 2" or "Validating · conf 3").
  const bits: string[] = [];
  if (activeNode === "research") {
    if (state.company_name) bits.push(state.company_name);
    if (state.attempts && state.attempts > 1) bits.push(`attempt ${state.attempts}`);
  } else if (activeNode === "validator") {
    if (state.confidence_score !== undefined) bits.push(`conf ${state.confidence_score}`);
  } else if (activeNode === "synthesis") {
    if (state.company_name) bits.push(state.company_name);
  } else if (activeNode === "clarity") {
    if (state.company_name) bits.push(state.company_name);
  }
  const suffix = bits.length ? ` · ${bits.join(" · ")}` : "";

  return (
    <div className="flex justify-start" aria-live="polite" aria-busy="true">
      <div className="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm shadow-sm bg-white text-slate-800 dark:bg-slate-800 dark:text-slate-100 ring-1 ring-slate-200 dark:ring-slate-700 flex items-center gap-3">
        <span className="text-base shrink-0" aria-hidden="true">
          {emoji}
        </span>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-slate-600 dark:text-slate-300 truncate">
            {label}
            <span className="text-slate-400 dark:text-slate-500">{suffix}</span>
          </span>
          <span className="inline-flex items-center gap-1 ml-1" aria-hidden="true">
            <Dot delay="0ms" />
            <Dot delay="150ms" />
            <Dot delay="300ms" />
          </span>
        </div>
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="block h-1.5 w-1.5 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce"
      style={{ animationDelay: delay, animationDuration: "1s" }}
    />
  );
}
