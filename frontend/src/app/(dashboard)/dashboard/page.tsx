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
import { ArrowUpIcon, Settings } from "lucide-react";
import { createRun, getLocalModels, getRunList } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";

export default function Dashboard() {
  const router = useRouter();
  const { model, setModel, setRunId, setError, error, setRuns, setUserPrompt, runConfig, setRunConfig } = useAgentStore();
  const { settings, loadSettings } = useConfigStore();

  const [prompt, setPrompt] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [showSettings, setShowSettings] = useState(false);
  const [starting, setStarting] = useState(false);
  const [tempMaxIterations, setTempMax] = useState(runConfig.maxIterations || 1);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    let cancelled = false;

    const loadModels = async (): Promise<void> => {
      const record: Record<string, string> = {};
      for (const id of settings?.selected_models ?? []) {
        record[id] = id;
      }
      try {
        const local = await getLocalModels();
        for (const id of local.models) {
          record[id] = id;
        }
        if (!cancelled && !useAgentStore.getState().model) {
          const qwen = local.models.find((id) => id.toLowerCase().includes("qwen"));
          if (qwen) {
            setModel(qwen);
          }
        }
      } catch {
        // Saved cloud models still show when the local list cannot be loaded.
      }
      if (!cancelled) {
        setModels(record);
      }
    };

    void loadModels();
    return () => {
      cancelled = true;
    };
  }, [settings?.selected_models, setModel]);

  useEffect(() => {
    const fetchRuns = async () => {
      // get the List of runs
      const runs = await getRunList();
      setRuns(runs);
    };

    fetchRuns();
  }, [setRuns]);

  const handleStart = useCallback(
    async (prompt: string) => {
      if (!model || starting) {
        return;
      }

      setStarting(true);
      try {
        const response = await createRun({
          user_prompt: prompt,
          url: runConfig.url || "",
          max_iterations: runConfig.maxIterations,
          model: model,
          mode: runConfig.mode,
        });
        const run_id = response.run_id;
        setRunId(run_id);
        setUserPrompt(prompt);
        setModel(model);

        // Refresh the runs list to include the new run
        const updatedRuns = await getRunList();
        setRuns(updatedRuns);

        router.push(`/runs?runId=${run_id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start agent");
        setStarting(false);
      }
    },
    [model, starting, router, setModel, setRunId, setUserPrompt, setError, setRuns, runConfig]
  );


  return (
    <div className="flex h-full items-center justify-center px-6">
      <div className="w-full max-w-2xl space-y-4">
        <h1 className="text-center text-2xl font-medium">What should Bro do?</h1>
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
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (prompt.trim()) handleStart(prompt);
              }
            }}
            placeholder="Find a vegetarian lasagna with 100+ reviews"
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
              variant="ghost"
              size="icon-xs"
              aria-label="Settings"
              onClick={() => {
                setTempMax(runConfig.maxIterations || 1);
                setShowSettings(true);
              }}
            >
              <Settings />
            </InputGroupButton>
            <InputGroupButton
              variant="default"
              className="rounded-full"
              size="icon-xs"
              aria-label="Submit"
              disabled={prompt === "" || !model || starting}
              onClick={() => handleStart(prompt)}
            >
              <ArrowUpIcon />
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
        {starting && <p className="text-center text-sm text-muted-foreground">Starting Bro…</p>}
        {error && <p className="text-center text-sm text-destructive">{error}</p>}
      </div>

      <Dialog open={showSettings} onOpenChange={setShowSettings}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>This chat</DialogTitle>
            <DialogDescription>
              Optional. Bro picks a page and a pace on its own.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="url">Start on a page</Label>
              <Input
                id="url"
                type="text"
                value={runConfig.url}
                onChange={(e) => setRunConfig({ url: e.target.value })}
                placeholder="https://example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="maxIterations">Step limit</Label>
              <Input
                id="maxIterations"
                type="number"
                value={String(tempMaxIterations)}
                onChange={
                  (e) => {
                    const val = parseInt(e.target.value);
                    setTempMax(val)
                    if (val > 0) setRunConfig({ maxIterations: val})
                  }
                }
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="classicLoop"
                checked={runConfig.mode === "legacy"}
                onCheckedChange={(checked) =>
                  setRunConfig({ mode: checked ? "legacy" : "fast" })
                }
              />
              <Label htmlFor="classicLoop">
                Slower, and look at the page
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setShowSettings(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
