/**
 * API client for Bro Agent backend.
 *
 * Provides typed functions for all backend endpoints.
 */


import type {
  CreateRunRequest,
  CreateRunResponse,
  ListRunsResponse,
  RunStatus,
  AgentStateResponse,
  RunState,
  LogEventDB,
} from "./models";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Create a new agent run.
 */
export async function createRun(
  request: CreateRunRequest
): Promise<CreateRunResponse> {
  const response = await fetch(`${API_BASE_URL}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
export async function getRunStatus(runId: string): Promise<RunStatus> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/status`);

  if (!response.ok) {
    throw new Error(`Failed to get run status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get the full agent state for a run.
 */
export async function getAgentState(
  runId: string
): Promise<AgentStateResponse> {
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
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  decision: "done" | "modify" | "intervene",
  additionalInstructions?: string
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    method: "POST",
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
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Failed to close browser: ${response.statusText}`);
  }
}

/**
 * Create an EventSource for streaming logs from a run.
 */
export function createLogStream(runId: string): EventSource {
  return new EventSource(`${API_BASE_URL}/runs/${runId}/logs/stream`);
}

/**
 * Poll the db to get runs stuff
 */

export async function getRunList(): Promise<ListRunsResponse[]> {
  const response = await fetch(`${API_BASE_URL}/runs`, {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Failed to get database contents ${response.statusText}`);
  }

  return response.json();
}

export async function getRun(runId: string): Promise<RunState> {
  const response = await fetch(`${API_BASE_URL}/${runId}`, {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Failed to get run contents ${response.statusText}`);
  }

  return response.json();
}

export async function getLogs(runId: string): Promise<LogEventDB[]> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/logs`, {
    method: "GET",
  })

  if (!response.ok) {
    throw new Error(`Failed to get database contents ${response.statusText}`);
  }

  return response.json();
}