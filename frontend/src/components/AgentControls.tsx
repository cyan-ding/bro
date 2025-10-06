"use client";


import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

interface AgentControlsProps {
  onStart: (prompt: string, url?: string) => void;
  onStop: () => void;
  onSendInput: (message: string) => void;
  onSendDecision: (decision: "done" | "modify" | "intervene", instructions?: string) => void;
  isRunning: boolean;
  isAwaitingDecision: boolean;
}

/**
 * Component for controlling the agent: start, stop, send input, and send decisions.
 */
export default function AgentControls({
  onStart,
  onStop,
  onSendInput,
  onSendDecision,
  isRunning,
  isAwaitingDecision,
}: AgentControlsProps) {
  const [prompt, setPrompt] = useState("");
  const [url, setUrl] = useState("");
  const [inputMessage, setInputMessage] = useState("");
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [showModifyInput, setShowModifyInput] = useState(false);

  const handleStart = () => {
    if (prompt.trim()) {
      onStart(prompt, url || undefined);
    }
  };

  const handleSendInput = () => {
    if (inputMessage.trim()) {
      onSendInput(inputMessage);
      setInputMessage("");
    }
  };

  const handleDecision = (decision: "done" | "modify" | "intervene") => {
    if (decision === "modify") {
      if (!showModifyInput) {
        setShowModifyInput(true);
        return;
      }
      if (additionalInstructions.trim()) {
        onSendDecision(decision, additionalInstructions);
        setAdditionalInstructions("");
        setShowModifyInput(false);
      }
    } else {
      onSendDecision(decision);
      setShowModifyInput(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent Controls</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!isRunning && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-2">Task Prompt</label>
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                placeholder="Describe the task for the agent..."
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Starting URL (optional)</label>
              <Input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com"
              />
            </div>

            <Button onClick={handleStart} disabled={!prompt.trim()} className="w-full">
              Start Agent
            </Button>
          </div>
        )}

        {isRunning && !isAwaitingDecision && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <Badge variant="outline" className="border-green-500">
                Agent Running
              </Badge>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Send Additional Instructions</label>
              <div className="flex gap-2">
                <Input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="Type a message to the agent..."
                  onKeyDown={(e) => e.key === "Enter" && handleSendInput()}
                  className="flex-1"
                />
                <Button onClick={handleSendInput} disabled={!inputMessage.trim()}>
                  Send
                </Button>
              </div>
            </div>

            <Button onClick={onStop} variant="destructive" className="w-full">
              Stop Agent
            </Button>
          </div>
        )}

        {isAwaitingDecision && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
              <Badge variant="outline" className="border-yellow-500">
                Awaiting Decision
              </Badge>
            </div>

            <p className="text-sm text-muted-foreground">
              The agent believes the task is complete. Choose an action:
            </p>

            {!showModifyInput ? (
              <div className="grid grid-cols-3 gap-2">
                <Button onClick={() => handleDecision("done")} variant="default" size="sm">
                  ✅ Done
                </Button>
                <Button onClick={() => handleDecision("modify")} variant="default" size="sm">
                  🔄 Modify
                </Button>
                <Button onClick={() => handleDecision("intervene")} variant="default" size="sm">
                  🛠️ Intervene
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <Textarea
                  value={additionalInstructions}
                  onChange={(e) => setAdditionalInstructions(e.target.value)}
                  rows={3}
                  placeholder="Provide additional instructions..."
                />
                <div className="flex gap-2">
                  <Button
                    onClick={() => handleDecision("modify")}
                    disabled={!additionalInstructions.trim()}
                    className="flex-1"
                  >
                    Submit Instructions
                  </Button>
                  <Button onClick={() => setShowModifyInput(false)} variant="outline">
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
