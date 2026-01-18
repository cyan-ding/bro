"use client"
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { toast } from "sonner";
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
  onCompletionChange: (isCompleted: boolean) => void;
  env?: string | undefined;
}

export default function Home() {
  const { settings, loadSettings, updateSettings } = useConfigStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [api, setApi] = useState<CarouselApi>();
  const [current, setCurrent] = useState(0);
  const [stepCompletion, setStepCompletion] = useState<boolean[]>([true, false, false, false, false]);
  const [env, setEnv] = useState("")
  const isEditMode = searchParams.get("edit") === "true";
  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  // pull the env variables so we can make sure the user has them
  useEffect(() => {
    async function loadEnvVars() {
      try {
        const content = await readEnvFile();
        setEnv(content);
      } catch (error) {
        toast.error("Failed to load environment variables. You can still add them manually.");
      }
    }
    void loadEnvVars();
  }, []);

  // Initialize completion state based on existing settings
  useEffect(() => {
    if (settings) {
      setStepCompletion([
        settings.initialized ?? false, // Step 0 is always completable
        Boolean(settings.chrome_path), // chrome path exists
        env !== "", // env vars loaded
        Boolean(settings.storage_mode), // Step 3 completed if storage mode selected
        (settings.selected_models?.length ?? 0) > 0, // Step 4 completed if models selected
      ]);
    }
    console.log(stepCompletion)
  }, [settings?.chrome_path, settings?.storage_mode, settings?.selected_models, env]);

  useEffect(() => {
    if (!api) {
      return;
    }

    setCurrent(api.selectedScrollSnap());
    console.log('[CAROUSEL] Initial current index:', api.selectedScrollSnap());

    api.on("select", () => {
      const newIndex = api.selectedScrollSnap();
      console.log('[CAROUSEL] Select event - new index:', newIndex);
      setCurrent(newIndex);
    });
  }, [api]);

  // Log the carousel position when it initializes
  useEffect(() => {
    if (api) {
      console.log('[CAROUSEL INIT] Carousel initialized at position:', api.selectedScrollSnap());
    }
  }, [api]);

  const handleStepCompleted = useCallback((stepIndex: number, isCompleted: boolean) => {
    setStepCompletion((prev) => {
      const newState = [...prev];
      newState[stepIndex] = isCompleted;
      return newState;
    });
  }, []);

  if (!settings) return <div>Loading...</div>;

  // Move to next step in carousel
  const handleForward = (nextStep: number) => {
    console.log('[HANDLE FORWARD] Called with nextStep:', nextStep);
    console.trace('[HANDLE FORWARD] Stack trace');
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
  const canGoNext = current < 4 && stepCompletion[current];

  console.log('[RENDER] current:', current, 'canGoBack:', canGoBack, 'canGoNext:', canGoNext);

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
              onComplete={() => handleForward(1)}
              onCompletionChange={(isCompleted) => handleStepCompleted(0, isCompleted)}
            />
          </CarouselItem>
          <CarouselItem>
            <ChromeStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleForward(2)}
              onCompletionChange={(isCompleted) => handleStepCompleted(1, isCompleted)}
            />
          </CarouselItem>
          <CarouselItem>
            <EnvVarsStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleForward(3)}
              onCompletionChange={(isCompleted) => handleStepCompleted(2, isCompleted)}
              env={env}
            />
          </CarouselItem>
          <CarouselItem>
            <StorageStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => handleForward(4)}
              onCompletionChange={(isCompleted) => handleStepCompleted(3, isCompleted)}
            />
          </CarouselItem>
          <CarouselItem>
            <ProviderModelsStep
              settings={settings}
              updateSettings={updateSettings}
              onComplete={() => router.push("/dashboard")}
              onCompletionChange={(isCompleted) => handleStepCompleted(4, isCompleted)}
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
      {isEditMode ?
        <Button onClick={() => router.push("/dashboard")}>
          Go back
        </Button> : <div></div>
      }
    </div>
  );
}

function StartStep({ settings, updateSettings, onComplete }: StepProps) {
  const handleStart = async () => {
    // Set initialized to true when user starts onboarding
    await updateSettings({
      ...settings,
      initialized: true,
    });
    onComplete();
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
      <h1 className="text-2xl font-bold text-center">
        Welcome to Bro, the free, open source, web browser agent dashboard!
      </h1>
      <Button variant="outline" aria-label="Submit" onClick={handleStart}>
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
    onCompletionChange(chromeFound);
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
      toast.error("Failed to detect Chrome automatically. Please select it manually.");
    } finally {
      setDetecting(false);
    }
  }, [settings.chrome_path]);

  useEffect(() => {
    void autoDetect();
  }, [autoDetect]);

  const handlePick = async () => {
    try {
      const chosen = await chooseChromePath();
      if (chosen) {
        setDetectedPath(chosen);
        toast.success("Chrome path selected successfully");
      }
    } catch (error) {
      toast.error("Failed to select Chrome path");
    }
  };

  const handleContinue = async () => {
    await updateSettings({
      ...settings,
      chrome_path: detectedPath || settings.chrome_path,
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

function EnvVarsStep({ onComplete, onCompletionChange, env }: StepProps) {
  const [envText, setEnvText] = useState<string>(env ?? "");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Step is completed if there's content in envText
    const isCompleted = envText.trim().length > 0;
    onCompletionChange(isCompleted);
  }, [envText]);

  const handleContinue = async () => {
    setLoading(true);
    try {
      await writeEnvFile(envText);
      toast.success("Environment variables saved successfully");
      onComplete();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save environment variables");
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

function StorageStep({ settings, updateSettings, onComplete, onCompletionChange }: StepProps) {
  const [storageMode, setStorageMode] = useState<string>(settings.storage_mode || "");
  const [supabaseUrl, setSupabaseUrl] = useState<string>(settings.supabase_url || "");
  const [supabaseApiKey, setSupabaseApiKey] = useState<string>(settings.supabase_api_key || "");

  useEffect(() => {
    const isCompleted =
      storageMode === "local" ||
      (storageMode === "cloud" && supabaseUrl.trim() !== "" && supabaseApiKey.trim() !== "");
    onCompletionChange(isCompleted);
  }, [storageMode, supabaseUrl, supabaseApiKey]);

  const handleContinue = async () => {
    try {
      await updateSettings({
        ...settings,
        storage_mode: storageMode,
        supabase_url: storageMode === "cloud" ? supabaseUrl : undefined,
        supabase_api_key: storageMode === "cloud" ? supabaseApiKey : undefined,
      });
      toast.success(`Storage mode set to ${storageMode === "local" ? "local" : "cloud"}`);
      onComplete();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save storage settings");
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] space-y-6 px-4">
      <h1 className="text-2xl font-bold text-center">Choose Storage Type</h1>
      <p className="text-sm text-muted-foreground text-center max-w-2xl">
        Select how you want to store your runs and logs. Local storage is private and works offline.
        Cloud storage allows access from multiple devices.
      </p>

      <RadioGroup
        value={storageMode}
        onValueChange={setStorageMode}
        className="w-full max-w-2xl space-y-4"
      >
        <Card
          className={`cursor-pointer transition-colors ${storageMode === "local" ? "border-primary" : ""
            }`}
          onClick={() => setStorageMode("local")}
        >
          <CardHeader>
            <div className="flex items-start space-x-3">
              <RadioGroupItem value="local" id="local" />
              <div>
                <CardTitle>Local Storage</CardTitle>
                <CardDescription>
                  Store runs and logs locally on your machine. Private and works offline.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
        </Card>

        <Card
          className={`cursor-pointer transition-colors ${storageMode === "cloud" ? "border-primary" : ""
            }`}
          onClick={() => setStorageMode("cloud")}
        >
          <CardHeader>
            <div className="flex items-start space-x-3">
              <RadioGroupItem value="cloud" id="cloud" />
              <div className="flex-1">
                <CardTitle>Cloud Storage (Supabase)</CardTitle>
                <CardDescription>
                  Store runs and logs in your Supabase database. Accessible from anywhere.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          {storageMode === "cloud" && (
            <CardContent className="space-y-3">
              <div>
                <Label htmlFor="supabase-url" className="text-sm">Supabase URL</Label>
                <Input
                  id="supabase-url"
                  type="text"
                  value={supabaseUrl}
                  onChange={(e) => setSupabaseUrl(e.target.value)}
                  placeholder="https://your-project.supabase.co"
                  className="mt-1"
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
              <div>
                <Label htmlFor="supabase-key" className="text-sm">Supabase API Key</Label>
                <Input
                  id="supabase-key"
                  type="password"
                  value={supabaseApiKey}
                  onChange={(e) => setSupabaseApiKey(e.target.value)}
                  placeholder="Your anon/service key"
                  className="mt-1"
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </CardContent>
          )}
        </Card>
      </RadioGroup>

      <Button
        variant="outline"
        aria-label="Continue"
        onClick={handleContinue}
        disabled={storageMode === "cloud" && (!supabaseUrl.trim() || !supabaseApiKey.trim())}
      >
        Continue
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
    onCompletionChange(isCompleted);
  }, [selectedModels, error]);


  useEffect(() => {
    async function fetchValidModels() {
      setLoading(true);
      setError(null);
      try {
        const response = await getValidModels();
        setValidModels(response.models || []);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "Failed to load models";
        setError(errorMessage);
        toast.error(errorMessage);
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
    });
    onComplete();
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
        <Command className="border rounded-md w-full max-w-2xl">
          <CommandInput placeholder="Search models..." />
          <CommandList className="max-h-96">
            <CommandEmpty>No models found.</CommandEmpty>
            <CommandGroup>
              {validModels.map((model) => (
                <CommandItem
                  key={model}
                  onSelect={() => handleModelToggle(model)}
                  className="flex items-center space-x-2 cursor-pointer"
                >
                  <Checkbox
                    checked={selectedModels.includes(model)}
                    onCheckedChange={() => handleModelToggle(model)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <Label
                    htmlFor={model}
                    className="text-sm font-normal cursor-pointer flex-1"
                  >
                    {model}
                  </Label>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      )}
      <Button
        variant="outline"
        aria-label="Continue"
        onClick={handleContinue}
        disabled={validModels.length > 0 && selectedModels.length === 0}
      >
        Continue to Dashboard
      </Button>
    </div>
  );
}
