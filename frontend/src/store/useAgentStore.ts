import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  LogEvent,
  RunStatus,
  AgentStateResponse,
  ChatMessage,
  ListRunsResponse
} from "@/lib/models";
import { createLogStream, getRunStatus, getRun, getLogs, getAgentState } from "@/lib/api";

interface AgentStore {
  // State
  runId: string | null;
  runs: ListRunsResponse[];
  logs: LogEvent[];
  runStatus: RunStatus | null;
  agentState: AgentStateResponse | null;
  error: string | null;
  eventSource: EventSource | null;
  chatMessages: ChatMessage[];
  model: string | null;
  pollingInterval: NodeJS.Timeout | null;
  isLoadingRun: boolean;

  // Actions
  setModel: (model: string | null) => void;
  setRunId: (runId: string | null) => void;
  setLogs: (logs: LogEvent[]) => void;
  setRuns: (runs: ListRunsResponse[]) => void;
  addLog: (log: LogEvent) => void;
  setRunStatus: (status: RunStatus | null) => void;
  setAgentState: (state: AgentStateResponse | null) => void;
  setError: (error: string | null) => void;
  setEventSource: (eventSource: EventSource | null) => void;
  closeEventSource: () => void;
  startLogStreaming: (runId: string) => void;
  addChatMessage: (message: ChatMessage) => void;
  setChatMessages: (messages: ChatMessage[]) => void;
  clearAll: () => void;
  loadRun: (runId: string) => Promise<void>;
  stopPolling: () => void;
}

export const useAgentStore = create<AgentStore>()(
  persist(
    (set, get) => ({
      // Initial state
      runId: null,
      runs: [],
      logs: [],
      runStatus: null,
      agentState: null,
      error: null,
      eventSource: null,
      chatMessages: [],
      model: null,
      pollingInterval: null,
      isLoadingRun: false,

      // Actions
      setModel: (model) => set({ model }),
      setRunId: (runId) => set({ runId }),
      setRuns: (runs) => set({ runs }),
      setLogs: (logs) => set({ logs }),
      addLog: (log) => set((state) => ({ logs: [...state.logs, log] })),
      setRunStatus: (runStatus) => set({ runStatus }),
      setAgentState: (agentState) => set({ agentState }),
      setError: (error) => set({ error }),
      setEventSource: (eventSource) => set({ eventSource }),
      addChatMessage: (message) =>
        set((state) => ({ chatMessages: [...state.chatMessages, message] })),
      setChatMessages: (chatMessages) => set({ chatMessages }),

      stopPolling: () => {
        const state = get();
        if (state.pollingInterval) {
          clearInterval(state.pollingInterval);
          set({ pollingInterval: null });
        }
      },

      closeEventSource: () => {
        const state = get();
        if (state.eventSource) {
          const oldEventSource = state.eventSource;
          oldEventSource.onmessage = null;
          oldEventSource.onerror = null;
          oldEventSource.close();
          set({ eventSource: null });
        }
        // Also stop polling when closing event source
        state.stopPolling();
      },

      startLogStreaming: (runId: string) => {
        const state = get();

        // Don't create a new connection if we already have one for this runId
        if (state.eventSource && state.runId === runId) {
          return;
        }

        // Close existing event source if any
        if (state.eventSource) {
          state.closeEventSource();
        }

        const newEventSource = createLogStream(runId);
        const eventSourceRunId = runId;
        
        newEventSource.onmessage = (event) => {
          try {
            // Skip empty or keepalive messages
            if (!event.data || event.data.trim() === "") {
              return;
            }

            const logEvent: LogEvent = JSON.parse(event.data);
            set((state) => ({ logs: [...state.logs, logEvent] }));

            // Close event source when run ends
            if (logEvent.event_type === "final_status") {
              newEventSource.onmessage = null;
              newEventSource.onerror = null;
              newEventSource.close();
              set({ eventSource: null });
              const finalState = get();
              finalState.stopPolling();
            }
          } catch (err) {
            console.error(
              "Failed to parse log event:",
              err,
              "Data:",
              event.data
            );
          }
        };

        newEventSource.onerror = (err) => {
          const currentState = get();
          // Only log if this EventSource is still active
          if (currentState.eventSource === newEventSource) {
            console.error("EventSource error:", err);
          }
          newEventSource.onmessage = null;
          newEventSource.onerror = null;
          newEventSource.close();
          set({ eventSource: null });
        };
        
        state.setEventSource(newEventSource);
      },

      clearAll: () => {
        const state = get();
        if (state.eventSource) {
          state.closeEventSource();
        } else {
          state.stopPolling();
        }
        set({
          runId: null,
          logs: [],
          runStatus: null,
          agentState: null,
          error: null,
          eventSource: null,
          chatMessages: [],
          pollingInterval: null,
          isLoadingRun: false,
          // Keep runs and model - these are useful across sessions
        });
      },

      loadRun: async (runId: string) => {
        const state = get();

        // Prevent concurrent loads of the same run
        if (state.isLoadingRun && state.runId === runId) {
          return;
        }

        // Set loading flag immediately to prevent concurrent calls
        set({ isLoadingRun: true });

        // Close any existing event source and stop polling
        if (state.eventSource) {
          state.closeEventSource();
        } else {
          state.stopPolling();
        }

        // Clear existing data and set the new runId
        set({
          runId,
          logs: [],
          agentState: null,
          runStatus: null,
          error: null
        });

        try {
          // Fetch run status first
          const status = await getRunStatus(runId);
          set({ runStatus: status });

          const isComplete = status === "completed" || status === "stopped" || status === "error";

          if (isComplete) {
            // For completed runs, fetch data once (no streaming/polling)
            const [runData, logsData] = await Promise.all([
              getRun(runId),
              getLogs(runId)
            ]);

            set({
              logs: logsData,
              agentState: runData.metadata as AgentStateResponse | null,
              isLoadingRun: false
            });
          } else {
            // For running runs, start streaming and polling
            state.startLogStreaming(runId);

            // Start polling for status and agent state
            let hasStopped = false;
            const pollRunData = async () => {
              try {
                const currentState = get();
                // Don't poll if we're no longer loading this run or already stopped
                if (currentState.runId !== runId || hasStopped) {
                  return;
                }

                const [status, agentState] = await Promise.all([
                  getRunStatus(runId),
                  getAgentState(runId)
                ]);

                set({ runStatus: status, agentState });

                if (status === "completed" || status === "stopped" || status === "error") {
                  hasStopped = true;
                  const finalState = get();
                  if (finalState.eventSource) {
                    finalState.closeEventSource();
                  } else {
                    finalState.stopPolling();
                  }
                  set({ isLoadingRun: false });
                }
              } catch (err) {
                console.error("Failed to poll run data:", err);
              }
            };

            pollRunData();
            const interval = setInterval(pollRunData, 1000);
            set({ pollingInterval: interval });
          }
        } catch (err) {
          console.error("Failed to load run:", err);
          set({
            error: err instanceof Error ? err.message : "Failed to load run",
            isLoadingRun: false
          });
        }
      },
    }),
    {
      name: "agent-storage",
      partialize: (state) => ({
        runId: state.runId,
        runs: state.runs,
        model: state.model
        // Don't persist logs, runStatus, agentState as they'll be fetched fresh
      }),
    }
  )
);
