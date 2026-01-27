"use client";
import { useEffect, useState, useCallback } from "react";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { Combobox } from "@/components/ui/combobox";
import { useAgentStore } from "@/store/useAgentStore";
import { useConfigStore } from "@/store/useConfigStore";
import { useRouter } from "next/navigation";
import { ArrowUpIcon } from "lucide-react";
import { createRun, getRunList } from "@/lib/api";

export default function Dashboard() {
  const router = useRouter();
  const { model, setModel, setRunId, setError, setRuns } = useAgentStore();
  const { settings, loadSettings } = useConfigStore();

  const [prompt, setPrompt] = useState("");
  const [models, setModels] = useState({});

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (settings?.selected_models) {
      const modelsRecord = settings.selected_models.reduce((acc, model) => {
        acc[model] = model;
        return acc;
      }, {} as Record<string, string>);
      setModels(modelsRecord);
    }
  }, [settings?.selected_models]);

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
      if (!model) {
        return;
      }

      try {
        const response = await createRun({
          user_prompt: prompt,
          url: url || "", // Keep URL in code but use empty string as default
          max_iterations: 100,
          take_screenshot: true,
          enable_logging: true,
          model: model,
        });
        const run_id = response.run_id;
        setRunId(run_id);
        setModel(model);

        // Refresh the runs list to include the new run
        const updatedRuns = await getRunList();
        setRuns(updatedRuns);

        router.push(`/runs?runId=${run_id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start agent");
      }
    },
    [model, router, setModel, setRunId, setError, setRuns]
  );


  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && prompt) {
        handleStart(prompt)
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [handleStart, prompt])

  return (
    <div className="flex justify-center items-center">
      <div className="w-1/2">
        <InputGroup>
          <InputGroupTextarea
            className="resize-none max-h-48"
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
          <InputGroupAddon align="block-end">
            <Combobox
              options={models}
              display={"Select a model"}
              empty={"No model selected"}
              setter={setModel}
              value={model}
              className="ml-auto"
            />
            <InputGroupButton
              variant="default"
              className="rounded-full"
              size="icon-xs"
              aria-label="Submit"
              disabled={prompt === "" || !model}
              onClick={() => handleStart(prompt)}
            >
              <ArrowUpIcon />
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </div>
    </div>
  );
}
