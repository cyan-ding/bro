
export interface ChatMessage {
  id: string;
  type: "user" | "agent" | "system";
  content: string;
  timestamp: Date;
}

export interface CreateRunRequest {
  user_prompt: string;
  url?: string;
  max_iterations: number;
  model: string;
}

// for just the dashboard
export interface ListRunsResponse {
  id: string;
  title?: string;
  status: RunStatus;
  completed_at?: string;
}

export type RunStatus =
  | "pending"
  | "running"
  | "awaiting_decision"
  | "completed"
  | "stopped"
  | "error";

export interface CreateRunResponse {
  run_id: string;
  status: string;
  message: string;
}

export interface AgentStateResponse {
  tabs: Array<{
    index: number;
    url: string;
    title: string;
  }>;
  current_tab_index: number | null;
  extractions: Array<
    | string
    | {
        content: string;
        source_url: string;
        source_title: string;
        content_length: number;
      }
  >;
  todo_list: Array<{
    task: string;
    completed: boolean;
  }>;
  action_history: Array<ActionContext>;
  last_edited: string;
  max_iterations: number;
}

export interface ActionContext {
  iteration: number;
  action_name: string;
  arguments: Record<string, unknown>;
  result: string;
  timestamp?: string;
  description?: string;
  structured_output?: StructuredOutput | null;
}

export interface StructuredOutput {
  thinking: string;
  evaluation_previous_actions: string;
  memory: string;
  next_goal: string;
}

export interface SendDecisionRequest {
  decision: "done" | "modify" | "intervene";
  additional_instructions?: string;
}

export interface LogEvent {
  timestamp: string;
  iteration: number;
  event_type: string;
  message?: string;
  error?: string;
  action_context?: ActionContext;
  thinking_context?: StructuredOutput;
  decision?: SendDecisionRequest;
}

export interface LogEventDB extends LogEvent {
  id: string
  run_id: string
}

export interface RunState {
  id: string;
  title?: string | null;
  status: string;
  user_prompt: string;
  url?: string | null;
  max_iterations: number;
  model: string;
  current_iteration?: number | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface UserSettings {
  selected_models: string[];
  chrome_path: string | null;
  storage_mode?: string;
  supabase_url?: string;
  supabase_api_key?: string;
  initialized?: boolean;
  completed?: boolean;
}