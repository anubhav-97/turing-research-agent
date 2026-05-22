// Mirrors backend Pydantic models in backend/app/api/schemas.py.
// Keep these in sync.

export type AgentNode =
  | "clarity"
  | "clarification"
  | "research"
  | "validator"
  | "synthesis";

export type EventType =
  | "node_start"
  | "node_end"
  | "interrupt"
  | "final_message"
  | "error"
  | "ping";

export interface SSEEvent {
  type: EventType;
  node?: AgentNode;
  state_delta?: Partial<StateDelta>;
  question?: string;
  content?: string;
  message?: string;
}

export interface StateDelta {
  clarity_status?: "clear" | "needs_clarification" | "unknown";
  company_name?: string | null;
  clarification_question?: string | null;
  confidence_score?: number;
  attempts?: number;
  validation_result?: "sufficient" | "insufficient" | "unknown";
  validation_feedback?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  ts: number;
}

export interface AgentTraceStep {
  node: AgentNode;
  startedAt: number;
  endedAt?: number;
  delta?: Partial<StateDelta>;
  status: "running" | "done";
  // Populated when the NEXT node begins — derived on the client so we can
  // surface the routing-function verdict next to each pill.
  nextNode?: AgentNode;
  routingReason?: string;
}

export interface TimestampedEvent {
  id: string;
  ts: number;
  event: SSEEvent;
}

export interface MessageSnapshot {
  role: "user" | "assistant" | "system";
  content: string;
  name?: string | null;
}

export interface ThreadHistory {
  thread_id: string;
  messages: MessageSnapshot[];
  interrupted: boolean;
  pending_question?: string | null;
}
