import { Button } from "@/components/ui/button";
import { UserSettings } from "@/lib/models";
import { useConfigStore } from "@/store/useConfigStore";
import { useEffect, useState } from "react";

interface Settings {
  setStep: () => void;
  updateSettings: (updates: UserSettings) => Promise<void>;
}

export default function Home() {
  const [step, setStep] = useState(0)
  const { settings, loadSettings, updateSettings } = useConfigStore();
  
  useEffect(() => {
    loadSettings();
  }, [loadSettings])

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") {
        setStep((s) => Math.max(0, s - 1));
      } else if (e.key === "ArrowRight") {
        setStep((s) => Math.min(3, s + 1));
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);


  if (!settings) return <div>Loading...</div>

  return (
    <div className="justify-center items-center min-h-screen">
      {step === 0 && <StartStep setStep={() => setStep(1)} updateSettings={updateSettings} />}
      {step === 1 && <ChromeStep setStep={() => setStep(2)} updateSettings={updateSettings} />}
      {step === 2 && <LocalModelsStep setStep={() => setStep(3)} updateSettings={updateSettings} />}
      {step === 3 && <ProviderModelsStep setStep={() => setStep(4)} updateSettings={updateSettings} />}

    </div>
  )
}


function StartStep({setStep, updateSettings} : Settings) {
  return <>
    <h1>Welcome to Bro, the free, open source, web browser agent dashboard!</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => setStep}
    >
      Start Onboarding Now!
    </Button>
  </>;
}



function ChromeStep({setStep, updateSettings} : Settings) {
  return <>
    <h1>Bro uses Chrome to run its browser agent. Lets check if you have chrome installed</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => setStep}
    >
      Continue
    </Button>
  </>
}


function LocalModelsStep({setStep, updateSettings} : Settings) {
  return <>
    <h1>Bro is compatible with all open source models on ollama. Select a few to try!</h1>
    <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => setStep}
    >
      Continue
    </Button>
  </>
}

function ProviderModelsStep({setStep, updateSettings} : Settings) {
  return <>
      <h1>Bro is compatible with all closed source LLMs. Select a few to try!</h1>
      <Button
      variant="outline"
      size="icon"
      aria-label="Submit"
      onClick={() => setStep}
    >
      Continue
    </Button>
  </>
}
