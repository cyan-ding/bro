"use client";

import { useState, useEffect, useCallback } from "react";
import AgentControls from "@/components/AgentControls";
import LogStream from "@/components/LogStream";
import AgentState from "@/components/AgentState";
import ScreencastViewer from "@/components/ScreencastViewer";
import {
  createRun,
  getRunStatus,
  getAgentState,
  sendInput,
  sendDecision,
  stopRun,
  closeBrowser,
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
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  // Fetch run status periodically
  useEffect(() => {
    if (!runId) return;

    const fetchStatus = async () => {
      try {
        const status = await getRunStatus(runId);
        setRunStatus(status);

        // Stop polling if run is complete
        if (status.status === "completed" || status.status === "stopped" || status.status === "error") {
          clearInterval(interval);
        }
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

    // Don't poll if run is complete
    if (runStatus?.status === "completed" || runStatus?.status === "stopped" || runStatus?.status === "error") {
      return;
    }

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
  }, [runId, runStatus]);

  // Set up log streaming
  useEffect(() => {
    if (!runId) return;

    const newEventSource = createLogStream(runId);
    setEventSource(newEventSource);

    newEventSource.onmessage = (event) => {
      try {
        // Skip empty or keepalive messages
        if (!event.data || event.data.trim() === "") {
          return;
        }

        const logEvent: LogEvent = JSON.parse(event.data);
        console.log(logEvent)
        setLogs((prev) => [...prev, logEvent]);

        // Close event source when run ends
        if (logEvent.event_type === "final_status") {
          newEventSource.close();
          setEventSource(null);
        }
      } catch (err) {
        console.error("Failed to parse log event:", err, "Data:", event.data);
      }
    };

    newEventSource.onerror = (err) => {
      console.error("EventSource error:", err);
      newEventSource.close();
      setEventSource(null);
    };

    return () => {
      newEventSource.close();
      setEventSource(null);
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

      // Close event source when stopping
      if (eventSource) {
        eventSource.close();
        setEventSource(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop agent");
    }
  }, [runId, eventSource]);

  const handleCloseBrowser = useCallback(async () => {
    try {
      await closeBrowser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to close browser");
    }
  }, []);

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
          {/* Left column: Controls + Logs */}
          <div className="lg:col-span-1 space-y-6">
            <AgentControls
              onStart={handleStart}
              onStop={handleStop}
              onCloseBrowser={handleCloseBrowser}
              onSendInput={handleSendInput}
              onSendDecision={handleSendDecision}
              isRunning={isRunning}
              isAwaitingDecision={isAwaitingDecision}
            />
            <LogStream logs={logs} />
          </div>

          {/* Middle column: Screencast */}
          <div className="lg:col-span-1">
            {runId ? (
              <ScreencastViewer runId={runId} />
            ) : (
              <div className="bg-card rounded-lg border shadow-sm p-8 text-center text-muted-foreground">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-16 w-16 mx-auto mb-4 opacity-20"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
                </svg>
                <p>Start an agent run to view browser screencast</p>
              </div>
            )}
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
