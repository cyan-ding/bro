"use client";

import { useState, useEffect, useCallback } from "react";
import AgentControls from "@/components/AgentControls";
import LogStream from "@/components/LogStream";
import AgentState from "@/components/AgentState";
import {
  createRun,
  getRunStatus,
  getAgentState,
  sendInput,
  sendDecision,
  stopRun,
  createLogStream,
  type LogEvent,
  type RunStatusResponse,
  type AgentStateResponse,
} from "@/lib/api";

/**
 * Main dashboard page for controlling and monitoring the Bro agent.
 */
export default function Dashboard() {
  const [runId, setRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [agentState, setAgentState] = useState<AgentStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch run status periodically
  useEffect(() => {
    if (!runId) return;

    const fetchStatus = async () => {
      try {
        const status = await getRunStatus(runId);
        setRunStatus(status);
      } catch (err) {
        console.error("Failed to fetch run status:", err);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [runId]);

  // Fetch agent state periodically
  useEffect(() => {
    if (!runId) return;

    const fetchState = async () => {
      try {
        const state = await getAgentState(runId);
        setAgentState(state);
      } catch (err) {
        console.error("Failed to fetch agent state:", err);
      }
    };

    fetchState();
    const interval = setInterval(fetchState, 3000);
    return () => clearInterval(interval);
  }, [runId]);

  // Set up log streaming
  useEffect(() => {
    if (!runId) return;

    const eventSource = createLogStream(runId);

    eventSource.onmessage = (event) => {
      try {
        // Skip empty or keepalive messages
        if (!event.data || event.data.trim() === "") {
          return;
        }

        const logEvent: LogEvent = JSON.parse(event.data);
        setLogs((prev) => [...prev, logEvent]);
      } catch (err) {
        console.error("Failed to parse log event:", err, "Data:", event.data);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource error:", err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [runId]);

  const handleStart = useCallback(async (prompt: string, url?: string) => {
    try {
      setError(null);
      setLogs([]);
      setAgentState(null);
      setRunStatus(null);

      const response = await createRun({
        user_prompt: prompt,
        url,
        max_iterations: 100,
        take_screenshot: true,
        enable_logging: true,
      });

      setRunId(response.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start agent");
    }
  }, []);

  const handleStop = useCallback(async () => {
    if (!runId) return;

    try {
      await stopRun(runId);
      setRunStatus((prev) => prev ? { ...prev, status: "stopped" } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop agent");
    }
  }, [runId]);

  const handleSendInput = useCallback(async (message: string) => {
    if (!runId) return;

    try {
      await sendInput(runId, message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send input");
    }
  }, [runId]);

  const handleSendDecision = useCallback(
    async (decision: "done" | "modify" | "intervene", instructions?: string) => {
      if (!runId) return;

      try {
        await sendDecision(runId, decision, instructions);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send decision");
      }
    },
    [runId]
  );

  const isRunning = runStatus?.status === "running";
  const isAwaitingDecision = runStatus?.status === "awaiting_decision";

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto py-8 px-4">
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2">Bro Agent Dashboard</h1>
          <p className="text-muted-foreground">
            Control and monitor your web automation agent
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-destructive/10 border border-destructive rounded-lg">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Controls */}
          <div className="lg:col-span-1">
            <AgentControls
              onStart={handleStart}
              onStop={handleStop}
              onSendInput={handleSendInput}
              onSendDecision={handleSendDecision}
              isRunning={isRunning}
              isAwaitingDecision={isAwaitingDecision}
            />
          </div>

          {/* Middle column: Logs */}
          <div className="lg:col-span-1">
            <LogStream logs={logs} />
          </div>

          {/* Right column: Agent State */}
          <div className="lg:col-span-1">
            <AgentState state={agentState} runStatus={runStatus} />
          </div>
        </div>
      </div>
    </div>
  );
}
