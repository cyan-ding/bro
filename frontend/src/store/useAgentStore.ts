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
          state.eventSource.close();
          set({ eventSource: null });
        }
        // Also stop polling when closing event source
        const actions = get();
        actions.stopPolling();
      },

      startLogStreaming: (runId: string) => {
        const state = get();

        // Don't create a new connection if we already have one for this runId
        if (state.eventSource && state.runId === runId) {
          console.log("[LogStream] Already connected to runId:", runId);
          return;
        }

        // Close existing event source if any
        if (state.eventSource) {
          console.log("[LogStream] Closing existing connection");
          state.eventSource.close();
        }

        console.log("[LogStream] Starting new connection for runId:", runId);
        const newEventSource = createLogStream(runId);

        newEventSource.onmessage = (event) => {
          try {
            // Skip empty or keepalive messages
            if (!event.data || event.data.trim() === "") {
              return;
            }

            const logEvent: LogEvent = JSON.parse(event.data);
            console.log("[LogStream]", logEvent);

            // Add log to store
            const currentState = get();
            set({ logs: [...currentState.logs, logEvent] });

            // Close event source when run ends
            if (logEvent.event_type === "final_status") {
              newEventSource.close();
              set({ eventSource: null });
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
          console.error("EventSource error:", err);
          newEventSource.close();
          set({ eventSource: null });
        };

        set({ eventSource: newEventSource });
      },

      clearAll: () => {
        const state = get();
        if (state.eventSource) {
          state.eventSource.close();
        }
        const actions = get();
        actions.stopPolling();
        set({
          runId: null,
          logs: [],
          runStatus: null,
          agentState: null,
          error: null,
          eventSource: null,
          chatMessages: [],
          pollingInterval: null,
          // Keep runs and model - these are useful across sessions
        });
      },

      loadRun: async (runId: string) => {
        const state = get();

        // Close any existing event source and stop polling
        if (state.eventSource) {
          state.eventSource.close();
        }
        const actions = get();
        actions.stopPolling();

        // Clear existing data and set the new runId
        set({
          runId,
          logs: [],
          agentState: null,
          runStatus: null,
          eventSource: null,
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
              agentState: runData.metadata as AgentStateResponse | null
            });
          } else {
            // For running runs, start streaming and polling
            actions.startLogStreaming(runId);

            // Start polling for status and agent state
            const pollRunData = async () => {
              try {
                const [status, state] = await Promise.all([
                  getRunStatus(runId),
                  getAgentState(runId)
                ]);

                set({ runStatus: status, agentState: state });

                // If run completed, reload to get final data
                if (status === "completed" || status === "stopped" || status === "error") {
                  const currentActions = get();
                  currentActions.stopPolling();
                  // Reload to get final data from storage
                  currentActions.loadRun(runId);
                }
              } catch (err) {
                console.error("Failed to poll run data:", err);
              }
            };

            // Poll immediately and then every 2 seconds
            pollRunData();
            const interval = setInterval(pollRunData, 1000);
            set({ pollingInterval: interval });
          }
        } catch (err) {
          console.error("Failed to load run:", err);
          set({
            error: err instanceof Error ? err.message : "Failed to load run"
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
