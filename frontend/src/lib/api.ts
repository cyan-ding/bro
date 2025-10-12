/**
 * API client for Bro Agent backend.
 *
 * Provides typed functions for all backend endpoints.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface CreateRunRequest {
  user_prompt: string;
  url?: string;
  max_iterations?: number;
  take_screenshot?: boolean;
  model?: string;
  user_id?: string;
  session_id?: string;
  enable_logging?: boolean;
}

export interface CreateRunResponse {
  run_id: string;
  session_id: string;
  user_id: string;
  status: string;
  message: string;
}

export interface RunStatusResponse {
  run_id: string;
  session_id: string;
  user_id: string;
  status: string;
  current_iteration: number;
  max_iterations: number;
  last_action: string | null;
  message?: string;
}

export interface AgentStateResponse {
  run_id: string;
  user_id: string;
  session_id: string;
  tabs: Array<{
    index: number;
    url: string;
    title: string;
  }>;
  current_tab_index: number | null;
  extractions: Array<string | {
    content: string;
    source_url: string;
    source_title: string;
    content_length: number;
  }>;
  todo_list: Array<{
    task: string;
    completed: boolean;
  }>;
  action_history: Array<ActionContext>;
  last_edited: string;
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
  decision: 'done' | 'modify' | 'intervene';
  additional_instructions?: string;
}

export interface LogEvent {
  timestamp: string;
  iteration: number;
  run_id: string;
  event_type: string;
  message?: string;
  error?: string;  
  action_context?: ActionContext;
  decision?: SendDecisionRequest
}

/**
 * Create a new agent run.
 */
export async function createRun(request: CreateRunRequest): Promise<CreateRunResponse> {
  const response = await fetch(`${API_BASE_URL}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to create run: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get the current status of a run.
 */
export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}`);

  if (!response.ok) {
    throw new Error(`Failed to get run status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get the full agent state for a run.
 */
export async function getAgentState(runId: string): Promise<AgentStateResponse> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/state`);

  if (!response.ok) {
    throw new Error(`Failed to get agent state: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Send additional instructions to a running agent.
 */
export async function sendInput(runId: string, message: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    throw new Error(`Failed to send input: ${response.statusText}`);
  }
}

/**
 * Send a decision response to an agent awaiting user decision.
 */
export async function sendDecision(
  runId: string,
  decision: 'done' | 'modify' | 'intervene',
  additionalInstructions?: string
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      decision,
      additional_instructions: additionalInstructions,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to send decision: ${response.statusText}`);
  }
}

/**
 * Stop a running agent.
 */
export async function stopRun(runId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/stop`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Failed to stop run: ${response.statusText}`);
  }
}

/**
 * Close the Chrome browser subprocess.
 */
export async function closeBrowser(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/browser/close`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Failed to close browser: ${response.statusText}`);
  }
}

/**
 * Create an EventSource for streaming logs from a run.
 */
export function createLogStream(runId: string): EventSource {
  return new EventSource(`${API_BASE_URL}/runs/${runId}/logs`);
}
