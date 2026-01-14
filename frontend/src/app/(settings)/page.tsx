"use client"
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Label } from "@/components/ui/label";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from "@/components/ui/carousel";
import { UserSettings } from "@/lib/models";
import { useConfigStore } from "@/store/useConfigStore";
import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { findChromePath, chooseChromePath, readEnvFile, writeEnvFile } from "@/lib/settings";
import { getValidModels } from "@/lib/api";

interface Settings {
  settings: UserSettings;
  updateSettings: (updates: UserSettings) => Promise<void>;
}

interface StepProps extends Settings {
  onComplete: () => void;
  onBack: () => void;
  onCompletionChange?: (isCompleted: boolean) => void;
}

export default function Home() {
  const { settings, loadSettings, updateSettings } = useConfigStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [api, setApi] = useState<CarouselApi>();
  const [current, setCurrent] = useState(0);
  const [stepCompletion, setStepCompletion] = useState<boolean[]>([true, false, false, false]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    const isEditMode = searchParams.get("edit") === "true";
    if (settings?.step === 4 && !isEditMode) router.push("/dashboard");
  }, [settings?.step, router, searchParams]);

  // Initialize completion state based on existing settings
  useEffect(() => {
    if (settings) {
      setStepCompletion([
        true, // Step 0 is always completable
        Boolean(settings.chrome_path) || settings.step > 1, // Step 1 completed if chrome_path exists
        settings.step > 2, // Step 2 completed if we've progressed past it
        (settings.selected_models?.length ?? 0) > 0 || settings.step > 3, // Step 3 completed if models selected
      ]);
    }
  }, [settings?.chrome_path, settings?.step, settings?.selected_models]);

  // if user goes back, only update current
  useEffect(() => {
    if (!api) {
      return;
    }

    setCurrent(api.selectedScrollSnap());

    api.on("select", () => {
      setCurrent(api.selectedScrollSnap());
    });
  }, [api]);

  // allow for custom forward/backward func
  useEffect(() => {
    if (api && settings) {
      api.scrollTo(settings.step);
    }
  }, [api, settings?.step]);

  const handleCompletionChange = useCallback((stepIndex: number, isCompleted: boolean) => {
    setStepCompletion((prev) => {
      const newState = [...prev];
      newState[stepIndex] = isCompleted;
      return newState;
    });
  }, []);

  if (!settings) return <div>Loading...</div>;

  // only update settings if moving forward
  const handleStepComplete = async (nextStep: number) => {
    await updateSettings({
      ...settings,
      step: nextStep,
    });
    if (api) {
      api.scrollTo(nextStep);
    }
  };

  const handleBack = () => {
    if (api && current > 0) {
      api.scrollTo(current - 1);
    }
  };

  const canGoBack = current > 0;
  const canGoNext = current < 3 && stepCompletion[current];

  return (
    <div className="flex flex-col justify-center items-center min-h-screen p-8">
      <Carousel
        setApi={setApi}
        opts={{
          align: "start",
          dragFree: false,
        }}
        className="w-full max-w-4xl"
      >
        <CarouselContent>
          <CarouselItem>
            <StartStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleStepComplete(1)}
              onBack={handleBack}
              onCompletionChange={(isCompleted) => handleCompletionChange(0, isCompleted)}
            />
          </CarouselItem>
          <CarouselItem>
            <ChromeStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleStepComplete(2)}
              onBack={handleBack}
              onCompletionChange={(isCompleted) => handleCompletionChange(1, isCompleted)}
            />
          </CarouselItem>
          <CarouselItem>
            <EnvVarsStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleStepComplete(3)}
              onBack={handleBack}
              onCompletionChange={(isCompleted) => handleCompletionChange(2, isCompleted)}
            />
          </CarouselItem>
          <CarouselItem>
            <ProviderModelsStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleStepComplete(4)}
              onBack={handleBack}
              onCompletionChange={(isCompleted) => handleCompletionChange(3, isCompleted)}
            />
          </CarouselItem>
        </CarouselContent>
        {canGoBack && (
          <CarouselPrevious className="left-4" onClick={handleBack} />
        )}
        {canGoNext && (
          <CarouselNext className="right-4" disabled={!stepCompletion[current]} onClick={() => api?.scrollNext()} /> // override normal carousel behavior with api
        )}
      </Carousel>
    </div>
  );
}

function StartStep({ onComplete }: StepProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
      <h1 className="text-2xl font-bold text-center">
        Welcome to Bro, the free, open source, web browser agent dashboard!
      </h1>
      <Button variant="outline" aria-label="Submit" onClick={onComplete}>
        Start Onboarding Now!
      </Button>
    </div>
  );
}

function ChromeStep({ settings, updateSettings, onComplete, onCompletionChange }: StepProps) {
  const [detectedPath, setDetectedPath] = useState<string | null>(settings.chrome_path);
  const [detecting, setDetecting] = useState(false);

  useEffect(() => {
    const chromeFound = Boolean(detectedPath);
    onCompletionChange?.(chromeFound);
  }, [detectedPath]);

  const autoDetect = useCallback(async () => {
    if (settings.chrome_path) {
      setDetectedPath(settings.chrome_path);
      return;
    }
    setDetecting(true);
    try {
      const paths = await findChromePath();
      if (paths.length) {
        setDetectedPath(paths[0]);
      }
    } catch (error) {
      // ignore if detection is unavailable (e.g., non-Electron env)
    } finally {
      setDetecting(false);
    }
  }, [settings.chrome_path]);

  useEffect(() => {
    void autoDetect();
  }, [autoDetect]);

  const handlePick = async () => {
    const chosen = await chooseChromePath();
    if (chosen) {
      setDetectedPath(chosen);
    }
  };

  const handleContinue = async () => {
    await updateSettings({
      ...settings,
      chrome_path: detectedPath || settings.chrome_path,
      step: Math.max(settings.step, 1),
    });
    onComplete();
  };

  const chromeFound = Boolean(detectedPath);

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 px-4">
      <h1 className="text-2xl font-bold text-center">Bro uses Chrome to run its browser agent.</h1>
      <p className="text-center">
        {chromeFound
          ? `Chrome detected at: ${detectedPath}`
          : "We couldn't find Chrome automatically."}
      </p>
      {!chromeFound && (
        <div className="space-y-2">
          <Button variant="outline" aria-label="Pick Chrome" onClick={handlePick}>
            {detecting ? "Scanning..." : "Pick Chrome manually"}
          </Button>
          <p className="text-sm text-center">
            If you don't have Chrome installed, please download it and return here.
          </p>
        </div>
      )}
      {chromeFound && (
        <Button className="mt-4" variant="outline" aria-label="Continue" onClick={handleContinue}>
          Continue
        </Button>
      )}
    </div>
  );
}

function EnvVarsStep({ settings, updateSettings, onComplete, onCompletionChange }: StepProps) {
  const [envText, setEnvText] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Step is completed if there's content in envText
    const isCompleted = envText.trim().length > 0;
    onCompletionChange?.(isCompleted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [envText]);

  useEffect(() => {
    async function loadEnvVars() {
      try {
        const content = await readEnvFile();
        setEnvText(content);
      } catch (error) {
        // Ignore if not in Electron environment
      }
    }
    void loadEnvVars();
  }, []);

  const handleContinue = async () => {
    setLoading(true);
    try {
      await writeEnvFile(envText);
      await updateSettings({
        ...settings,
        step: Math.max(settings.step, 2),
      });
      onComplete();
    } catch (error) {
      // Handle error - could show a toast notification
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 px-4">
      <h1 className="text-2xl font-bold text-center">Add your API keys</h1>
      <p className="text-sm text-muted-foreground text-center">
        Paste your environment variables here. These will be saved to your .env file.
      </p>
      <Textarea
        value={envText}
        onChange={(e) => setEnvText(e.target.value)}
        className="w-full max-w-2xl h-64 text-sm"
        placeholder="OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=..."
      />
      <Button
        variant="outline"
        aria-label="Continue"
        onClick={handleContinue}
        disabled={loading}
      >
        {loading ? "Saving..." : "Continue"}
      </Button>
    </div>
  );
}

function ProviderModelsStep({ settings, updateSettings, onComplete, onCompletionChange }: StepProps) {
  const [validModels, setValidModels] = useState<string[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>(settings.selected_models || []);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Step is completed if models are selected or there's an error
    const isCompleted = selectedModels.length > 0 || error !== null;
    onCompletionChange?.(isCompleted);
  }, [selectedModels, error]);


  useEffect(() => {
    async function fetchValidModels() {
      setLoading(true);
      setError(null);
      try {
        const response = await getValidModels();
        setValidModels(response.models || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load models");
      } finally {
        setLoading(false);
      }
    }
    void fetchValidModels();
  }, []);

  const handleModelToggle = (model: string) => {
    setSelectedModels((prev) =>
      prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
    );
  };

  const handleContinue = async () => {
    await updateSettings({
      ...settings,
      selected_models: selectedModels,
      step: Math.max(settings.step, 3),
    });
    onComplete();
    onCompletionChange?.(true);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <h1 className="text-2xl font-bold text-center">Detecting available models...</h1>
        <p className="text-sm text-muted-foreground text-center">
          Checking which models are available with your API keys.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 px-4">
        <h1 className="text-2xl font-bold text-center">Error loading models</h1>
        <p className="text-sm text-red-500 text-center">{error}</p>
        <p className="text-sm text-muted-foreground text-center">
          Please check your API keys in the previous step.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 px-4">
      <h1 className="text-2xl font-bold text-center">Select models to use</h1>
      <p className="text-sm text-muted-foreground text-center">
        {validModels.length > 0
          ? `Found ${validModels.length} available model(s) based on your API keys. Select the ones you want to use.`
          : "No models found. Please check your API keys in the previous step."}
      </p>
      {validModels.length > 0 && (
        <ScrollArea className="w-full h-96 border rounded-md p-4">
          <div className="space-y-3">
            {validModels.map((model) => (
              <div key={model} className="flex items-center space-x-2">
                <Checkbox
                  id={model}
                  checked={selectedModels.includes(model)}
                  onCheckedChange={() => handleModelToggle(model)}
                />
                <Label
                  htmlFor={model}
                  className="text-sm font-normal cursor-pointer flex-1"
                >
                  {model}
                </Label>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
      <Button
        variant="outline"
        aria-label="Continue"
        onClick={handleContinue}
        disabled={validModels.length > 0 && selectedModels.length === 0}
      >
        Continue
      </Button>
    </div>
  );
}
