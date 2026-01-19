import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  LogEvent,
  RunStatus,
  AgentStateResponse,
  ChatMessage,
  ListRunsResponse,
  RunState
} from "@/lib/models";
import { createLogStream } from "@/lib/api";

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
  viewedRunId: string | null; // we have to to track currently viewed run, without overriding the runId that could be for a live run
  viewedRunData: RunState | null; 
  viewedRunLogs: LogEvent[]; 


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
  setViewedRunId: (runId: string | null) => void;
  setViewedRunData: (data: RunState | null) => void;
  setViewedRunLogs: (logs: LogEvent[]) => void;
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
      viewedRunId: null,
      viewedRunData: null,
      viewedRunLogs: [],

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
      setViewedRunId: (runId: string | null) => set({ viewedRunId: runId }),
      setViewedRunData: (data: RunState | null) => set({ viewedRunData: data }),
      setViewedRunLogs: (logs: LogEvent[]) => set({ viewedRunLogs: logs }),
      
      closeEventSource: () => {
        const state = get();
        if (state.eventSource) {
          state.eventSource.close();
          set({ eventSource: null });
        }
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
        set({
          runId: null,
          logs: [],
          runStatus: null,
          agentState: null,
          error: null,
          eventSource: null,
          chatMessages: [],
        });
      },
    }),
    {
      name: "agent-storage",
      partialize: (state) => ({
        runId: state.runId,
        runs: state.runs,
        // Don't persist logs, runStatus, agentState as they'll be fetched fresh
      }),
    }
  )
);
