"use client"
import { useEffect, useState, useCallback } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Combobox } from "@/components/ui/combobox"
import { useAgentStore } from "@/store/useAgentStore"
import { Button } from "@/components/ui/button"
import { useRouter } from "next/navigation"
import { ArrowUpIcon } from "lucide-react"
import { NavigationMenuDemo } from "@/components/ui/navbar"
import { createClient } from "@supabase/supabase-js"

import {
    createRun,
} from "@/lib/api";

const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

export default function Home() {
    const router = useRouter()
    const {
        model,
        setModel,
        setRunId,
        setError,
    } = useAgentStore();

    const [prompt, setPrompt] = useState("")
    let [models, setModels] = useState({})

    useEffect(() => {
        fetch("/models.json")
            .then((res) => res.json())
            .then((data) => {
                setModels(data)
            });
    }, []
    )

    supabase.auth.onAuthStateChange(async (event, session) => {
            if (event === "SIGNED_IN" && session) {
                
            }
        }

    )

    const handleStart = useCallback(async (prompt: string, url?: string) => {
        try {
            const response = await createRun({
                user_prompt: prompt,
                url: url || "", // Keep URL in code but use empty string as default
                max_iterations: 100,
                take_screenshot: true,
                enable_logging: true,
                model: model || "gemini/gemini-2.5-flash-preview-09-2025",
            });
            const run_id = response.run_id
            setRunId(run_id);
            setModel(model || "gemini/gemini-2.5-flash-preview-09-2025")
            router.push(`/runs?runId=${run_id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to start agent");
        }
    }, [setRunId, setError]);


    return (
        <div>
            <NavigationMenuDemo
                onGoogleSignin={
                    () => supabase.auth.signInWithOAuth({
                        provider: 'google',
                    })
                }
            />
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
        </div>

    )
}