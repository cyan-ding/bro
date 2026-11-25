"use client";

import { useEffect, useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AgentChat from "@/components/AgentChat";
import ScreencastViewer from "@/components/ScreencastViewer";
import {
  sendInput,
  sendDecision,
  stopRun,
  closeBrowser,
  getRunList,
  createRun,
} from "@/lib/api";

import { useAgentStore } from "@/store/useAgentStore";
import { buildConversation, withPreviousContext } from "@/lib/conversation";

/**
 * Main dashboard page for controlling and monitoring the Bro agent.
 */
export default function Run() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlRunId = searchParams.get("runId");

  const {
    runId,
    logs,
    runStatus,
    agentState,
    error,
    userPrompt,
    model,
    runConfig,
    setRunId,
    setUserPrompt,
    setRunStatus,
    setError,
    setRuns,
    loadRun,
  } = useAgentStore();

  const isRunning = runStatus === "running";
  const isAwaitingDecision = runStatus === "awaiting_decision";
  const [isDriving, setIsDriving] = useState(false);

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

    return () => {
      useAgentStore.getState().closeEventSource();
      useAgentStore.setState({ isLoadingRun: false });
    };
  }, [urlRunId, loadRun]);


  const handleStop = useCallback(async () => {
    if (!runId) return;

    try {
      await stopRun(runId);
      setRunStatus("stopped");
      useAgentStore.getState().closeEventSource();
      try {
        await closeBrowser();
      } catch {
        // The browser may already be gone.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop agent");
    }
  }, [runId, setRunStatus, setError]);

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

  const handleFollowUp = useCallback(
    async (message: string) => {
      if (!model) {
        setError("Pick a model from a new chat first.");
        return;
      }
      const previousAnswer = buildConversation(userPrompt, logs, agentState?.action_history)
        .filter((item) => item.kind === "answer")
        .pop()?.text;
      const prompt = userPrompt && previousAnswer
        ? withPreviousContext(message, userPrompt, previousAnswer)
        : message;
      try {
        const response = await createRun({
          user_prompt: prompt,
          url: runConfig.url || "",
          max_iterations: runConfig.maxIterations,
          model,
          mode: runConfig.mode,
        });
        setRunId(response.run_id);
        setUserPrompt(message);
        const updatedRuns = await getRunList();
        setRuns(updatedRuns);
        router.push(`/runs?runId=${response.run_id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start agent");
      }
    },
    [model, runConfig, router, setError, setRunId, setRuns, setUserPrompt, userPrompt, logs, agentState]
  );

  return (
    <div className="flex h-full min-h-0 flex-col px-4 py-3">
      {error && (
        <p className="mb-3 text-sm text-destructive">{error}</p>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-[minmax(260px,1fr)_2fr]">
        <AgentChat
          isRunning={isRunning}
          onStop={handleStop}
          onSendInput={handleSendInput}
          onSendDecision={handleSendDecision}
          onFollowUp={handleFollowUp}
          isAwaitingDecision={isAwaitingDecision}
          isPaused={isDriving}
          logs={logs}
          agentState={agentState}
          userPrompt={userPrompt}
        />
        <ScreencastViewer
          key={runId}
          isRunning={isRunning || isAwaitingDecision}
          onDrivingChange={setIsDriving}
        />
      </div>
    </div>
  );
}
