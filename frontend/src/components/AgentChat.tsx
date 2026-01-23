"use client";

import { useState, useRef, useEffect } from "react";
import { LogEvent, AgentStateResponse } from "@/lib/models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAgentStore } from "@/store/useAgentStore";
import { ChatMessage } from "@/lib/models";
import Link from "next/link";

interface AgentChatProps {
  onStop: () => void;
  onCloseBrowser: () => void;
  onSendInput?: (message: string) => void;
  onSendDecision?: (
    decision: "done" | "modify" | "intervene",
    instructions?: string
  ) => void;
  isRunning: boolean;
  isAwaitingDecision?: boolean;
  logs: LogEvent[];
  runId: string | null;
  agentState: AgentStateResponse | null;
}

export default function AgentChat({
  onStop,
  onCloseBrowser,
  onSendInput,
  onSendDecision,
  isRunning,
  isAwaitingDecision = false,
  logs,
  runId,
  agentState,
}: AgentChatProps) {
  const { model, chatMessages, addChatMessage } = useAgentStore();
  const [input, setInput] = useState("");
  const [url, setUrl] = useState("");
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [showModifyInput, setShowModifyInput] = useState(false);
  const [showStopDialog, setShowStopDialog] = useState(false);
  const [showExtractions, setShowExtractions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastTodoListRef = useRef<string>("");

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages]);

  // Detect todo list changes and display them
  useEffect(() => {
    if (!agentState?.todo_list || agentState.todo_list.length === 0) {
      return;
    }

    const todoListStr = JSON.stringify(agentState.todo_list);
    if (
      todoListStr !== lastTodoListRef.current &&
      lastTodoListRef.current !== ""
    ) {
      // Todo list changed, add a message showing the current todos
      const todoItems = agentState.todo_list
        .map(
          (todo, idx) =>
            `${idx + 1}. ${todo.completed ? "✅" : "⬜"} ${todo.task}`
        )
        .join("\n");

      const todoMessage: ChatMessage = {
        id: `todo-${Date.now()}`,
        type: "agent",
        content: `📋 Todo List Updated:\n${todoItems}`,
        timestamp: new Date(),
      };

      addChatMessage(todoMessage);
    }

    lastTodoListRef.current = todoListStr;
  }, [agentState?.todo_list, addChatMessage]);

  useEffect(() => {
    // Filter and convert logs to chat messages
    const newMessages: ChatMessage[] = [];

    logs.forEach((log) => {
      const logId = crypto.randomUUID();

      let content = "";
      let messageType: "user" | "agent" | "system" = "agent";

      // Process different event types
      switch (log.event_type) {
        case "status":
          content = log.message || "Status update";
          break;
        case "error":
          content = `Error: ${log.error || log.message || "Unknown error"}`;
          messageType = "system";
          break;
        case "thinking":
          if (log.thinking_context?.thinking) {
            content = `💭 ${log.thinking_context.thinking}`;
          }
          break;
        case "action":
          const actionName = log.action_context?.action_name;

          // Create message for the action
          if (actionName === "done") {
            content = `✅ ${log.action_context?.result || "Task completed"}`;
          } else if (actionName) {
            content = `Action: ${actionName}${log.action_context?.result ? `\n${log.action_context.result}` : ""}`;
            if (actionName === "extract") content = content.slice(0, 50);
          }
          break;
        case "user_input":
          content = log.message || "User sent additional instructions";
          messageType = "user";
          break;
        case "final_status":
          content = "Run completed";
          messageType = "system";
          break;
        // no default; we want to silently ignore unknown types
      }

      if (content) {
        newMessages.push({
          id: logId,
          type: messageType,
          content,
          timestamp: new Date(log.timestamp),
        });
      }
    });

    if (newMessages.length > 0) {
      newMessages.forEach((msg) => addChatMessage(msg));
    }
  }, [logs, addChatMessage]);

  const handleSendAdditionalInput = () => {
    if (!input.trim() || !onSendInput) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: "user",
      content: input,
      timestamp: new Date(),
    };

    addChatMessage(userMessage);
    onSendInput(input);
    setInput("");
  };

  const handleDecision = (decision: "done" | "modify" | "intervene") => {
    if (!onSendDecision) return;

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

  const handleStopConfirm = (closeBrowser: boolean) => {
    onStop();
    if (closeBrowser) {
      onCloseBrowser();
    }
    setShowStopDialog(false);

    const systemMessage: ChatMessage = {
      id: Date.now().toString(),
      type: "system",
      content: closeBrowser
        ? "Agent stopped and browser closed"
        : "Agent stopped",
      timestamp: new Date(),
    };
    addChatMessage(systemMessage);
  };

  return (
    <div className="bg-card rounded-lg border flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p>Model: {model}</p>
          {isRunning && !isAwaitingDecision && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <Badge variant="outline" className="border-green-500 text-xs">
                Running
              </Badge>
            </div>
          )}
          {isAwaitingDecision && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
              <Badge variant="outline" className="border-yellow-500 text-xs">
                Awaiting Decision
              </Badge>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {runId &&
            agentState?.extractions &&
            agentState.extractions.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowExtractions(true)}
                className="text-xs"
              >
                View Extractions ({agentState.extractions.length})
              </Button>
            )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatMessages.length === 0 ? (
          <div className="text-center text-muted-foreground py-8">
            <p className="mb-2">Run starting...</p>
          </div>
        ) : (
          chatMessages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.type === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  message.type === "user"
                    ? "bg-primary text-primary-foreground"
                    : message.type === "agent"
                      ? "bg-secondary"
                      : "bg-destructive/10 text-destructive"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t space-y-3">
        {/* Decision Buttons */}
        {isAwaitingDecision && !showModifyInput && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              The agent believes the task is complete. Choose an action:
            </p>
            <div className="grid grid-cols-3 gap-2">
              <Button
                onClick={() => handleDecision("done")}
                variant="default"
                size="sm"
              >
                ✅ Done
              </Button>
              <Button
                onClick={() => handleDecision("modify")}
                variant="default"
                size="sm"
              >
                🔄 Modify
              </Button>
              <Button
                onClick={() => handleDecision("intervene")}
                variant="default"
                size="sm"
              >
                🛠️ Intervene
              </Button>
            </div>
          </div>
        )}

        {/* Modify Instructions Input */}
        {isAwaitingDecision && showModifyInput && (
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Additional Instructions
            </label>
            <Textarea
              value={additionalInstructions}
              onChange={(e) => setAdditionalInstructions(e.target.value)}
              rows={3}
              placeholder="Provide additional instructions..."
              className="w-full px-3 py-2 bg-background border rounded-md focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
            <div className="flex gap-2">
              <Button
                onClick={() => handleDecision("modify")}
                disabled={!additionalInstructions.trim()}
                className="flex-1"
              >
                Submit Instructions
              </Button>
              <Button
                onClick={() => setShowModifyInput(false)}
                variant="outline"
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Main Input Form */}
        {!isAwaitingDecision && (
          <form className="space-y-2">
            {/* URL Input (optional, collapsible) */}
            {!isRunning && showUrlInput && (
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Starting URL (optional)
                </label>
                <Input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com"
                  className="mt-1"
                />
              </div>
            )}

            {/* Main textarea and buttons */}
            <div className="flex gap-2">
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  isRunning
                    ? "Send additional instructions... (Shift+Enter for new line)"
                    : "Run ended"
                }
                rows={3}
                className="flex-1 px-3 py-2 bg-background border rounded-md focus:outline-none focus:ring-1 focus:ring-ring resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (isRunning) {
                      handleSendAdditionalInput();
                    }
                  }
                }}
                disabled={!isRunning}
              />
              <div className="flex flex-col gap-2">
                {isRunning ? (
                  <>
                    <Button
                      type="button"
                      onClick={handleSendAdditionalInput}
                      disabled={!input.trim()}
                      size="sm"
                    >
                      Send
                    </Button>
                    <Button
                      type="button"
                      onClick={() => setShowStopDialog(true)}
                      variant="destructive"
                      size="sm"
                    >
                      Stop
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      type="submit"
                      disabled={!input.trim()}
                      className="h-full"
                    >
                      Start
                    </Button>
                  </>
                )}
              </div>
            </div>
          </form>
        )}
      </div>

      {/* Extractions Dialog */}
      <Dialog open={showExtractions} onOpenChange={setShowExtractions}>
        <DialogContent className="max-w-3xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle>Extracted Content</DialogTitle>
            <DialogDescription>
              The agent extracted the following content during this run
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] pr-4">
            <div className="space-y-4">
              {agentState?.extractions && agentState.extractions.length > 0 ? (
                agentState.extractions.map((extraction, index) => {
                  const isString = typeof extraction === "string";
                  const extractionObj = !isString ? extraction : null;

                  return (
                    <Card key={index}>
                      <CardHeader>
                        <CardTitle className="text-sm flex items-center justify-between">
                          <span>Extraction {index + 1}</span>
                          {extractionObj?.source_title && (
                            <Badge variant="outline">
                              {extractionObj.source_title}
                            </Badge>
                          )}
                        </CardTitle>
                        {extractionObj?.source_url && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Source: {extractionObj.source_url}
                          </p>
                        )}
                      </CardHeader>
                      <CardContent>
                        <div className="bg-muted p-3 rounded-lg">
                          <pre className="text-sm whitespace-pre-wrap break-words">
                            {isString ? extraction : extractionObj?.content}
                          </pre>
                        </div>
                        {extractionObj?.content_length && (
                          <p className="text-xs text-muted-foreground mt-2">
                            Length: {extractionObj.content_length} characters
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  );
                })
              ) : (
                <p className="text-center text-muted-foreground py-8">
                  No extractions available
                </p>
              )}
            </div>
          </ScrollArea>
          <DialogFooter>
            <Button
              onClick={() => setShowExtractions(false)}
              className="w-full"
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Stop Confirmation Dialog */}
      <Dialog open={showStopDialog} onOpenChange={setShowStopDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Stop Agent</DialogTitle>
            <DialogDescription>
              Do you want to close the browser or just stop the agent?
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-2">
            <p className="text-sm text-muted-foreground">
              <strong>Stop Only:</strong> Stops the agent but keeps the browser
              open.
            </p>
            <p className="text-sm text-muted-foreground">
              <strong>Close Browser:</strong> Stops the agent and closes the
              browser completely.
            </p>
          </div>
          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button
              variant="outline"
              onClick={() => handleStopConfirm(false)}
              className="w-full sm:w-auto"
            >
              Stop Only
            </Button>
            <Button
              variant="destructive"
              onClick={() => handleStopConfirm(true)}
              className="w-full sm:w-auto"
            >
              Close Browser
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
