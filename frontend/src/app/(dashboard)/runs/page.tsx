"use client";

import { useEffect, useCallback, useState } from "react";

import AgentChat from "@/components/AgentChat";
import ScreencastViewer from "@/components/ScreencastViewer";
import {
  getRunStatus,
  getAgentState,
  sendInput,
  sendDecision,
  stopRun,
  closeBrowser,
} from "@/lib/api";
import { useAgentStore } from "@/store/useAgentStore";

/**
 * Main dashboard page for controlling and monitoring the Bro agent.
 */
export default function Run() {
  const {
    runId,
    logs,
    runStatus,
    agentState,
    error,
    model,
    setRunId,
    setLogs,
    setRunStatus,
    setAgentState,
    setError,
  } = useAgentStore();

  const isRunning = runStatus === "running";
  const isAwaitingDecision = runStatus === "awaiting_decision";

  // Fetch run status periodically, only when it started
  useEffect(() => {
    if (!runId) return;

    const fetchStatus = async () => {
      try {
        const status = await getRunStatus(runId);
        setRunStatus(status);

        // Stop polling and optionally clear runId if run is complete
        if (
          status === "completed" ||
          status === "stopped" ||
          status === "error"
        ) {
          clearInterval(interval);
        }
      } catch (err) {
        console.error("Failed to fetch run status:", err);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [runId, isRunning, setRunStatus]);

  // Fetch agent state periodically
  useEffect(() => {
    if (!runId || !isRunning) return;

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
  }, [runId, isRunning, runStatus, setAgentState]);

  // Set up log streaming using Zustand store
  useEffect(() => {
    if (!runId || !isRunning) {
      useAgentStore.getState().closeEventSource();
      return;
    }

    // Start log streaming via Zustand store
    useAgentStore.getState().startLogStreaming(runId);

    // Cleanup on unmount or runId change
    return () => {
      // Don't close when component unmounts - let the store manage it
      // This allows streaming to continue when navigating between pages
    };
  }, [runId, isRunning]);

  const handleStop = useCallback(async () => {
    if (!runId) return;

    try {
      await stopRun(runId);
      setRunStatus("stopped");

      // Close event source when stopping
      useAgentStore.getState().closeEventSource();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop agent");
    }
  }, [runId, runStatus, setRunStatus, setError]);

  const handleCloseBrowser = useCallback(async () => {
    try {
      await closeBrowser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to close browser");
    }
  }, [setError]);

  const handleSendInput = useCallback(
    async (message: string) => {
      if (!runId) return;

      try {
        await sendInput(runId, message);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to send input");
      }
    },
    [runId, setError]
  );

  const handleSendDecision = useCallback(
    async (
      decision: "done" | "modify" | "intervene",
      instructions?: string
    ) => {
      if (!runId) return;

      try {
        await sendDecision(runId, decision, instructions);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to send decision"
        );
      }
    },
    [runId, setError]
  );

  return (
    <div className="container mx-auto py-8 px-4">
        <h1 className="text-4xl font-bold mb-2">Bro</h1>

      {error && (
        <div className="mb-6 p-4 bg-destructive/10 border border-destructive rounded-lg">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      <div
        className="grid grid-cols-1 lg:grid-cols-3 gap-6 grid-rows-1"
        style={{ height: "calc(100vh - 150px)" }}
      >
        {/* Left column: Chat Interface */}
        <div className="lg:col-span-1">
          <AgentChat
            isRunning={isRunning}
            onStop={handleStop}
            onCloseBrowser={handleCloseBrowser}
            onSendInput={handleSendInput}
            onSendDecision={handleSendDecision}
            isAwaitingDecision={isAwaitingDecision}
            logs={logs}
            runId={runId}
            agentState={agentState}
          />
        </div>

        {/* Middle + Right columns: Screencast (expanded) */}
        <div className="lg:col-span-2">
          <ScreencastViewer
            currentUrl={
              agentState?.tabs?.[agentState.current_tab_index ?? 0]?.url
            }
            isRunning={isRunning}
          />
        </div>
      </div>
    </div>
  );
}
