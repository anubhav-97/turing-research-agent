import type { AgentNode, AgentTraceStep } from "../types";

const NODE_COLOR: Record<AgentNode, string> = {
  clarity: "bg-clarity",
  clarification: "bg-interrupt",
  research: "bg-research",
  validator: "bg-validator",
  synthesis: "bg-synthesis",
};

const NODE_LABEL: Record<AgentNode, string> = {
  clarity: "Clarity",
  clarification: "Waiting",
  research: "Research",
  validator: "Validator",
  synthesis: "Synthesis",
};

const ROUTE_FN: Record<AgentNode, string | null> = {
  clarity: "route_after_clarity",
  clarification: null,
  research: "route_after_research",
  validator: "route_after_validator",
  synthesis: null,
};

interface Props {
  trace: AgentTraceStep[];
  activeNode: AgentNode | null;
}

export function AgentTimeline({ trace, activeNode }: Props) {
  if (trace.length === 0) {
    return (
      <div className="text-xs text-slate-400 dark:text-slate-500 italic">
        No agent activity yet — ask a question below.
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-3">
      {trace.map((step, idx) => {
        const isActive = step.node === activeNode && step.status === "running";
        const color = NODE_COLOR[step.node] ?? "bg-slate-500";
        const elapsed = step.endedAt ? step.endedAt - step.startedAt : null;
        const routeFn = ROUTE_FN[step.node];

        return (
          <div key={`${step.node}-${idx}`} className="flex items-center gap-2">
            <div className="flex flex-col items-start gap-1">
              <div
                className={[
                  "px-3 py-1 rounded-full text-white text-xs font-medium flex items-center gap-2",
                  color,
                  isActive
                    ? "animate-pulse-slow ring-2 ring-offset-1 ring-offset-transparent ring-white/40"
                    : "opacity-90",
                ].join(" ")}
              >
                <span>{NODE_LABEL[step.node]}</span>
                {step.delta?.confidence_score !== undefined && (
                  <span className="bg-white/25 rounded px-1.5 text-[10px]">
                    c={step.delta.confidence_score}
                  </span>
                )}
                {step.delta?.attempts !== undefined && step.node === "research" && (
                  <span className="bg-white/25 rounded px-1.5 text-[10px]">
                    #{step.delta.attempts}
                  </span>
                )}
                {step.delta?.validation_result && (
                  <span className="bg-white/25 rounded px-1.5 text-[10px]">
                    {step.delta.validation_result === "sufficient" ? "✓" : "↻"}
                  </span>
                )}
                {elapsed !== null && (
                  <span className="text-[10px] opacity-70">{Math.round(elapsed)}ms</span>
                )}
              </div>
              {step.routingReason && routeFn && (
                <div
                  className="text-[10px] font-mono text-slate-500 dark:text-slate-400 ml-1"
                  title={`Backend routing function: ${routeFn}`}
                >
                  <span className="text-slate-400 dark:text-slate-500">{routeFn}</span>
                  <span className="text-slate-300 dark:text-slate-600"> → </span>
                  <span className="text-slate-700 dark:text-slate-200">
                    {step.routingReason}
                  </span>
                </div>
              )}
            </div>
            {idx < trace.length - 1 && (
              <span className="text-slate-400 dark:text-slate-600 text-xs self-start mt-1">
                →
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
