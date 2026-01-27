"use client";

import { useEffect, useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";

import AgentChat from "@/components/AgentChat";
import ScreencastViewer from "@/components/ScreencastViewer";
import {
  sendInput,
  sendDecision,
  stopRun,
  closeBrowser,
  getRunList,
} from "@/lib/api";

import { useAgentStore } from "@/store/useAgentStore";

/**
 * Main dashboard page for controlling and monitoring the Bro agent.
 */
export default function Run() {
  const searchParams = useSearchParams();
  const urlRunId = searchParams.get("runId");

  const {
    runId,
    logs,
    runStatus,
    agentState,
    error,
    setRunStatus,
    setError,
    setRuns,
    loadRun,
  } = useAgentStore();

  const isRunning = runStatus === "running";
  const isAwaitingDecision = runStatus === "awaiting_decision";

  // Fetch runs list on mount to ensure sidebar is up to date
  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const runs = await getRunList();
        setRuns(runs);
      } catch (err) {
        console.error("Failed to fetch runs list:", err);
      }
    };

    fetchRuns();
  }, [setRuns]);

  // Load run data when URL changes
  useEffect(() => {
    if (urlRunId) {
      loadRun(urlRunId);
    }
  }, [urlRunId, loadRun]);


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

      // Optimistically update status immediately for instant UI feedback
      if (decision === "done") {
        setRunStatus("completed");
      } else {
        // For "modify" or "intervene", set back to running
        setRunStatus("running");
      }

      try {
        await sendDecision(runId, decision, instructions);
        // Polling will eventually confirm the status, but UI updates immediately
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to send decision"
        );
        // On error, status will be corrected by next poll or user can retry
      }
    },
    [runId, setError, setRunStatus]
  );

  return (
    <div className="container mx-auto px-4 py-4">

      {error && (
        <div className="mb-4 p-4 bg-destructive/10 border border-destructive rounded-lg">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      <div
        className="grid grid-cols-1 lg:grid-cols-3 gap-6 grid-rows-1"
        style={{ height: "calc(100vh - 70px)" }}
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
