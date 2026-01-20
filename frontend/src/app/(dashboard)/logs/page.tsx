"use client"

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import AgentState from "@/components/AgentState";
import LogStream from "@/components/LogStream";
import type { AgentStateResponse, LogEvent } from "@/lib/models";
import { getAgentState, getRunStatus, createLogStream } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";

export default function Logs() {
    const searchParams = useSearchParams();
    const runId = searchParams.get("runId");
    const router = useRouter();
    const [logs, setLogs] = useState<LogEvent[]>([]);
    const [agentState, setAgentState] = useState<AgentStateResponse | null>(null);
    const [runStatus, setRunStatus] = useState<string | null>(null);
    const [maxIterations, setMaxIterations] = useState<number | null>(null);
    const finished =
        (runStatus === "completed" ||
            runStatus === "stopped" ||
            runStatus === "error")
    // Set up log streaming using EventSource
    useEffect(() => {
        if (
            !runId
        ) return;

        const eventSource = createLogStream(runId);

        eventSource.onmessage = (event) => {
            try {
                const logEvent: LogEvent = JSON.parse(event.data);
                setLogs((prev) => [...prev, logEvent]);
            } catch (err) {
                console.error("Failed to parse log event:", err);
            }
        };

        eventSource.onerror = (error) => {
            console.error("EventSource error:", error);
            eventSource.close();
        };

        return () => {
            eventSource.close();
        };
    }, [runId]);

    // Fetch run status periodically
    useEffect(() => {
        if (!runId) return;

        const fetchStatus = async () => {
            try {
                const status = await getRunStatus(runId);
                setRunStatus(status);

                // Stop polling if run is complete
                if (
                    finished
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
    }, [runId]);

    // Fetch agent state periodically
    useEffect(() => {
        if (!runId) return;

        const fetchState = async () => {
            try {
                const state = await getAgentState(runId);
                setAgentState(state);

                // Stop polling if run is complete
                if (
                    finished
                ) {
                    clearInterval(interval);
                }
            } catch (err) {
                console.error("Failed to fetch agent state:", err);
            }
        };

        fetchState();
        const interval = setInterval(fetchState, 3000);
        return () => clearInterval(interval);
    }, [runId, runStatus]);

    return (
        <div className="container mx-auto p-6">
            <div className="flex items-center gap-4 mb-6">
                <Button variant="ghost" size="icon" onClick={() => router.back()}>
                    <ArrowLeft className="h-5 w-5" />
                </Button>
                <h1 className="text-3xl font-bold">Agent Logs</h1>
            </div>
            {!runId && (
                <div className="mb-4 p-4 bg-muted border rounded-lg">
                    <p className="text-sm text-muted-foreground">
                        No run selected. Please select a run from the dashboard.
                    </p>
                </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <LogStream logs={logs} />
                <AgentState
                    state={agentState}
                    runStatus={runStatus}
                    max_iterations={maxIterations}
                />
            </div>
        </div>
    );
}