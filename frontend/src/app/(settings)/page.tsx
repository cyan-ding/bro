import { Button } from "@/components/ui/button";
import { UserSettings } from "@/lib/models";
import { useConfigStore } from "@/store/useConfigStore";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

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
    <div className="justify-center items-center min-h-screen">
      {settings.step === 0 && <StartStep settings={settings} updateSettings={updateSettings} />}
      {settings.step === 1 && <ChromeStep settings={settings} updateSettings={updateSettings} />}
      {settings.step === 2 && <LocalModelsStep settings={settings} updateSettings={updateSettings} />}
      {settings.step === 3 && <ProviderModelsStep settings={settings} updateSettings={updateSettings} />}


    </div>
  )
}


function StartStep({ settings, updateSettings }: Settings) {
  return <>
    <h1>Welcome to Bro, the free, open source, web browser agent dashboard!</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => updateSettings({ ...settings, step: settings.step + 1 })}
    >
      Start Onboarding Now!
    </Button>
  </>;
}



function ChromeStep({ settings, updateSettings }: Settings) {
  return <>
    <h1>Bro uses Chrome to run its browser agent. Lets check if you have chrome installed</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => updateSettings({ ...settings, step: settings.step + 1 })}
    >
      Continue
    </Button>
  </>
}


function LocalModelsStep({ settings, updateSettings }: Settings) {
  return <>
    <h1>Bro is compatible with all open source models on ollama. Select a few to try!</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => updateSettings({ ...settings, step: settings.step + 1 })}
    >
      Continue
    </Button>
  </>
}

function ProviderModelsStep({ settings, updateSettings }: Settings) {
  return <>
    <h1>Bro is compatible with all closed source LLMs. Select a few to try!</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => updateSettings({ ...settings, step: settings.step + 1 })}
    >
      Continue
    </Button>
  </>
}
