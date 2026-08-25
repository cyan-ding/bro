"use client"

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import AgentState from "@/components/AgentState";
import LogStream from "@/components/LogStream";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { useAgentStore } from "@/store/useAgentStore";

export default function Logs() {
    const searchParams = useSearchParams();
    const urlRunId = searchParams.get("runId");
    const router = useRouter();
    const { logs, agentState, runStatus, loadRun } = useAgentStore();
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

    return (
        <div className="container mx-auto p-6">
            <div className="flex items-center gap-4 mb-6">
                <Button variant="ghost" size="icon" onClick={() => router.back()}>
                    <ArrowLeft className="h-5 w-5" />
                </Button>
                <h1 className="text-3xl font-bold">Agent Logs</h1>
            </div>
            {!urlRunId && (
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
                />
            </div>
        </div>
    );
}