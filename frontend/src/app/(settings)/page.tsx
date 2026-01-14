"use client"
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { UserSettings } from "@/lib/models";
import { useConfigStore } from "@/store/useConfigStore";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { findChromePath, chooseChromePath, readEnvFile, writeEnvFile } from "@/lib/settings";

interface Settings {
  settings: UserSettings;
  updateSettings: (updates: UserSettings) => Promise<void>;
}

export default function Home() {
  const { settings, loadSettings, updateSettings } = useConfigStore();
  const router = useRouter();
  useEffect(() => {
    loadSettings();
  }, [loadSettings])

  useEffect(() => {
    if (settings?.step === 4) router.push("/dashboard")
  }, [settings?.step, router]) // if user has completed onboarding, send directly to dashboard. 

  if (!settings) return <div>Loading...</div>

  return (
    <div className="flex flex-col justify-center items-center min-h-screen">
      {settings.step === 0 && <StartStep settings={settings} updateSettings={updateSettings} />}
      {settings.step === 1 && <ChromeStep settings={settings} updateSettings={updateSettings} />}
      {settings.step === 2 && <EnvVarsStep settings={settings} updateSettings={updateSettings} />}
      {settings.step === 3 && <ProviderModelsStep settings={settings} updateSettings={updateSettings} />}
    </div>
  )
}


function StartStep({ settings, updateSettings }: Settings) {
  return <>
    <h1>Welcome to Bro, the free, open source, web browser agent dashboard!</h1>
    <Button
      variant="outline"
      aria-label="Submit"
      onClick={() => updateSettings({ ...settings, step: settings.step + 1 })}
    >
      Start Onboarding Now!
    </Button>
  </>;
}



function ChromeStep({ settings, updateSettings }: Settings) {
  const [detectedPath, setDetectedPath] = useState<string | null>(settings.chrome_path);
  const [detecting, setDetecting] = useState(false);

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
      step: settings.step + 1,
    });
  };

  const chromeFound = Boolean(detectedPath);

  return (
    <>
      <h1>Bro uses Chrome to run its browser agent.</h1>
      <p className="mt-2">
        {chromeFound
          ? `Chrome detected at: ${detectedPath}`
          : "We couldn't find Chrome automatically."}
      </p>
      {!chromeFound && (
        <div className="mt-4 space-y-2">
          <Button
            variant="outline"
            aria-label="Pick Chrome"
            onClick={handlePick}
          >
            {detecting ? "Scanning..." : "Pick Chrome manually"}
          </Button>
          <p className="text-sm">
            If you don't have Chrome installed, please download it and return here.
          </p>
        </div>
      )}
      {chromeFound && (
        <Button
          className="mt-4"
          variant="outline"
          aria-label="Continue"
          onClick={handleContinue}
        >
          Continue
        </Button>
      )}
    </>
  );
}

function EnvVarsStep({ settings, updateSettings }: Settings) {
  const [envText, setEnvText] = useState<string>("");
  const [loading, setLoading] = useState(false);

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
        step: settings.step + 1,
      });
    } catch (error) {
      // Handle error - could show a toast notification
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1>Add your API keys</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Paste your environment variables here. These will be saved to your .env file.
      </p>
      <Textarea
        value={envText}
        onChange={(e) => setEnvText(e.target.value)}
        className="mt-4 w-full max-w-2xl h-64 text-sm"
        placeholder="OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=..."
      />
      <Button
        className="mt-4"
        variant="outline"
        aria-label="Continue"
        onClick={handleContinue}
        disabled={loading}
      >
        {loading ? "Saving..." : "Continue"}
      </Button>
    </>
  );
}

function ProviderModelsStep({ settings, updateSettings }: Settings) {
  return <>
    <h1>Bro is compatible with all closed source LLMs. Select a few to try!</h1>
    <Button
      variant="outline"
      aria-label="Submit"
      onClick={() => updateSettings({ ...settings, step: settings.step + 1 })}
    >
      Continue
    </Button>
  </>
}
