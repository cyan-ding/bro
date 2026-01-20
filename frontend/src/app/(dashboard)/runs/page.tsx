"use client";

import { useEffect, useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";

import AgentChat from "@/components/AgentChat";
import ScreencastViewer from "@/components/ScreencastViewer";
import {
  getRunStatus,
  getAgentState,
  sendInput,
  sendDecision,
  stopRun,
  closeBrowser,
  getRunList,
  getLogs,
  getRun,
} from "@/lib/api";

import { AgentStateResponse } from "@/lib/models";
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
    setAgentState,
    setError,
    setRuns,
    setViewedRunId,
    setViewedRunData,
    setViewedRunLogs,
    viewedRunData,
    viewedRunLogs,
  } = useAgentStore();

  // Determine if we're viewing a historical run or a live run
  const isViewingHistoricalRun = urlRunId && urlRunId !== runId;
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

  // Fetch historical run data when viewing a previous run from URL
  useEffect(() => {
    // If there's a runId in the URL and it's different from the current live run
    if (urlRunId && urlRunId !== runId) {
      const fetchHistoricalRun = async () => {
        try {
          setViewedRunId(urlRunId);
          const [runData, logsData] = await Promise.all([
            getRun(urlRunId),
            getLogs(urlRunId)
          ]);
          setViewedRunData(runData);
          setViewedRunLogs(logsData);
        } catch (err) {
          console.error("Failed to fetch historical run:", err);
          setError(err instanceof Error ? err.message : "Failed to load run");
        }
      };

      fetchHistoricalRun();
    }
  }, [urlRunId, runId, setViewedRunId, setViewedRunData, setViewedRunLogs, setError]);

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
          // pull the data once so it can be shown(the run is complete)
          const runs = await getRun(runId)
          setViewedRunData(runs)
          const logs = await getLogs(runId)
          setViewedRunLogs(logs)
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
    <div className="container mx-auto px-4 py-4">
      <h1 className="text-4xl font-bold mb-2">Bro</h1>

      {error && (
        <div className="mb-4 p-4 bg-destructive/10 border border-destructive rounded-lg">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      <div
        className="grid grid-cols-1 lg:grid-cols-3 gap-6 grid-rows-1"
        style={{ height: "calc(100vh - 120px)" }}
      >
        {/* Left column: Chat Interface */}
        <div className="lg:col-span-1">
          <AgentChat
            isRunning={isRunning && !isViewingHistoricalRun}
            onStop={handleStop}
            onCloseBrowser={handleCloseBrowser}
            onSendInput={handleSendInput}
            onSendDecision={handleSendDecision}
            isAwaitingDecision={isAwaitingDecision && !isViewingHistoricalRun}
            logs={isViewingHistoricalRun ? viewedRunLogs : logs}
            runId={isViewingHistoricalRun ? urlRunId : runId}
            agentState={isViewingHistoricalRun ? (viewedRunData?.metadata as AgentStateResponse | null) : agentState}
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
