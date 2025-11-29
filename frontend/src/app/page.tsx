"use client";
import { useEffect, useState, useCallback } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Combobox } from "@/components/ui/combobox";
import { useAgentStore } from "@/store/useAgentStore";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { ArrowUpIcon } from "lucide-react";
import { createRun, getRuns } from "@/lib/api";
import { useAuthStore } from "@/store/useAuthStore";



export default function Home() {
    const router = useRouter();
    const { model, setModel, setRunId, setError, setRuns } = useAgentStore();

    const { authToken } = useAuthStore();

    const [prompt, setPrompt] = useState("");
    const [models, setModels] = useState({});

    useEffect(() => {
        fetch("/models.json")
            .then((res) => res.json())
            .then((data) => {
                setModels(data);
            });
    }, []);


    useEffect(() => {
        if (authToken) {
            const fetchRuns = async () => {
                const runs = await getRuns(authToken);
                setRuns(runs);
            }

            fetchRuns()
        }
    },
        [setRuns, authToken]
    );

    const handleStart = useCallback(
        async (prompt: string, url?: string) => {
            try {
                const response = await createRun({
                    user_prompt: prompt,
                    url: url || "", // Keep URL in code but use empty string as default
                    max_iterations: 100,
                    take_screenshot: true,
                    enable_logging: true,
                    model: model || "gemini/gemini-2.5-flash-preview-09-2025",
                });
                const run_id = response.run_id;
                setRunId(run_id);
                setModel(model || "gemini/gemini-2.5-flash-preview-09-2025");
                router.push(`/runs?runId=${run_id}`);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to start agent");
            }
        },
        [model, router, setModel, setRunId, setError]
    );

    return (
        <div className="flex justify-center items-center min-h-screen">
            <div className="relative w-1/2">
                <Textarea
                    className="resize-none h-[25vh] focus:border-none focus:ring-0"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Message Bro"
                />
                <div className="absolute bottom-0 right-2 flex flex-row gap-2 mt-2">
                    <Combobox
                        options={models}
                        display={"Select a model"}
                        empty={"No model selected"}
                        setter={setModel}
                    />
                    <Button
                        variant="outline"
                        size="icon"
                        aria-label="Submit"
                        onClick={() => handleStart(prompt)}
                        className="hover:bg-accent"
                    >
                        <ArrowUpIcon />
                    </Button>
                </div>
            </div>
        </div>
    );
}
