import type { AgentNode } from "../types";

interface Props {
  activeNode: AgentNode | null;
  visitedNodes: Set<AgentNode>;
}

// Static SVG diagram of the 4-node graph with edges.
// Highlights the active node + nodes already visited this run.
export function GraphTopology({ activeNode, visitedNodes }: Props) {
  const isActive = (n: AgentNode) => n === activeNode;
  const wasVisited = (n: AgentNode) => visitedNodes.has(n);

  const nodeClass = (n: AgentNode, base: string) =>
    [
      base,
      isActive(n) ? "stroke-yellow-300 stroke-[3px]" : wasVisited(n) ? "stroke-white" : "stroke-slate-400 dark:stroke-slate-700",
      isActive(n) ? "animate-pulse-slow" : "",
    ].join(" ");

  return (
    <svg viewBox="0 0 320 220" className="w-full max-w-xs h-auto">
      {/* edges */}
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M0,0 L10,5 L0,10 z" className="fill-slate-400 dark:fill-slate-500" />
        </marker>
      </defs>

      {/* clarity -> research */}
      <line x1="160" y1="40" x2="160" y2="78" className="stroke-slate-400 dark:stroke-slate-600" strokeWidth="1.5" markerEnd="url(#arrow)" />
      {/* research -> validator */}
      <line x1="160" y1="118" x2="160" y2="148" className="stroke-slate-400 dark:stroke-slate-600" strokeWidth="1.5" markerEnd="url(#arrow)" />
      {/* validator -> research (loopback) */}
      <path d="M125 170 Q60 170 60 95 Q60 80 130 95" fill="none" className="stroke-amber-500" strokeWidth="1.5" strokeDasharray="4 3" markerEnd="url(#arrow)" />
      {/* research -> synthesis */}
      <path d="M195 100 Q260 100 260 180 Q260 195 240 195" fill="none" className="stroke-slate-400 dark:stroke-slate-600" strokeWidth="1.5" markerEnd="url(#arrow)" />
      {/* validator -> synthesis */}
      <line x1="180" y1="178" x2="220" y2="190" className="stroke-slate-400 dark:stroke-slate-600" strokeWidth="1.5" markerEnd="url(#arrow)" />

      {/* nodes */}
      <g>
        <rect x="120" y="10" width="80" height="30" rx="14" className={nodeClass("clarity", "fill-clarity")} strokeWidth="1.5" />
        <text x="160" y="29" textAnchor="middle" className="fill-white text-[11px] font-medium">Clarity</text>
      </g>
      <g>
        <rect x="120" y="80" width="80" height="40" rx="14" className={nodeClass("research", "fill-research")} strokeWidth="1.5" />
        <text x="160" y="105" textAnchor="middle" className="fill-white text-[11px] font-medium">Research</text>
      </g>
      <g>
        <rect x="120" y="150" width="80" height="30" rx="14" className={nodeClass("validator", "fill-validator")} strokeWidth="1.5" />
        <text x="160" y="169" textAnchor="middle" className="fill-white text-[11px] font-medium">Validator</text>
      </g>
      <g>
        <rect x="220" y="185" width="80" height="30" rx="14" className={nodeClass("synthesis", "fill-synthesis")} strokeWidth="1.5" />
        <text x="260" y="204" textAnchor="middle" className="fill-white text-[11px] font-medium">Synthesis</text>
      </g>

      <text x="10" y="200" className="fill-slate-500 dark:fill-slate-400 text-[9px]">↻ loop ≤ 3</text>
    </svg>
  );
}
