"use client";
import { useEffect, useState, useCallback } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Combobox } from "@/components/ui/combobox";
import { useAgentStore } from "@/store/useAgentStore";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";
import { ArrowUpIcon } from "lucide-react";
import { createRun, getRunList } from "@/lib/api";

export default function Dashboard() {
  const router = useRouter();
  const { model, setModel, setRunId, setError, setRuns } = useAgentStore();

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
    const fetchRuns = async () => {
      // get the List of runs
      const runs = await getRunList();
      setRuns(runs);
    };

    fetchRuns();
  }, [setRuns]);

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
    <div className="flex justify-center items-center">
      <div className="w-1/2">
        <Textarea
          className="resize-none border-none max-h-48"
          onInput={e => {
            const target = e.currentTarget;
            target.style.height = "auto"
            target.style.height = `${target.scrollHeight}px`
          }}
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Message Bro"
        />
        <div className="bottom-0 w-full flex items-center">
            <div className="ml-auto flex items-center">
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
              >
                <ArrowUpIcon />
              </Button>
            </div>
        </div>
      </div>
    </div>
  );
}
