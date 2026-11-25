"use client";

import { useState } from "react";
import { ArrowUpIcon, ChevronDown, ChevronRight } from "lucide-react";
import { LogEvent, AgentStateResponse } from "@/lib/models";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { buildConversation, type ConversationItem } from "@/lib/conversation";

interface AgentChatProps {
  onStop: () => void;
  onSendInput?: (message: string) => void;
  onSendDecision?: (
    decision: "done" | "modify" | "intervene",
    instructions?: string
  ) => void;
  onFollowUp?: (message: string) => void;
  isRunning: boolean;
  isAwaitingDecision?: boolean;
  isPaused?: boolean;
  logs: LogEvent[];
  agentState: AgentStateResponse | null;
  userPrompt: string | null;
}

type Group = {
  id: string;
  kind: ConversationItem["kind"] | "steps";
  texts: string[];
};

function groupItems(items: ConversationItem[]): Group[] {
  const groups: Group[] = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (item.kind === "step" && last?.kind === "steps") {
      last.texts.push(item.text);
      continue;
    }
    if (item.kind === "step") {
      groups.push({ id: item.id, kind: "steps", texts: [item.text] });
      continue;
    }
    groups.push({ id: item.id, kind: item.kind, texts: [item.text] });
  }
  return groups;
}

function StepList({ steps }: { steps: string[] }) {
  return (
    <ul className="space-y-1 text-sm text-muted-foreground">
      {steps.map((step, index) => (
        <li key={`${step}-${index}`} className="break-words">{step}</li>
      ))}
    </ul>
  );
}

function Activity({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  if (steps.length <= 3) {
    return <StepList steps={steps} />;
  }
  return (
    <div className="space-y-1">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-auto px-0 text-sm font-normal text-muted-foreground hover:bg-transparent hover:text-foreground"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        {open ? "Hide steps" : `${steps.length} steps`}
      </Button>
      {open && <StepList steps={steps} />}
    </div>
  );
}

export default function AgentChat({
  onStop,
  onSendInput,
  onSendDecision,
  onFollowUp,
  isRunning,
  isAwaitingDecision = false,
  isPaused = false,
  logs,
  agentState,
  userPrompt,
}: AgentChatProps) {
  const [input, setInput] = useState("");
  const [showSaved, setShowSaved] = useState(false);
  const items = buildConversation(userPrompt, logs, agentState?.action_history);
  const groups = groupItems(items);
  const saved = agentState?.extractions ?? [];
  const todos = agentState?.todo_list ?? [];

  const send = () => {
    const message = input.trim();
    if (isAwaitingDecision) {
      if (!message) return;
      onSendDecision?.("modify", message);
      setInput("");
      return;
    }
    if (!message) return;
    if (isRunning) {
      onSendInput?.(message);
    } else {
      onFollowUp?.(message);
    }
    setInput("");
  };

  const placeholder = isAwaitingDecision
    ? "Tell Bro what to change"
    : isRunning
      ? "Add a note"
      : "Ask a follow-up";

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 py-2">
        {groups.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {isRunning ? "Working" : "Nothing here yet"}
          </p>
        )}
        {groups.map((group) => {
          if (group.kind === "user") {
            return (
              <div key={group.id} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl bg-secondary px-3 py-2 text-sm whitespace-pre-wrap break-words">
                  {group.texts[0]}
                </p>
              </div>
            );
          }
          if (group.kind === "steps") {
            return <Activity key={group.id} steps={group.texts} />;
          }
          if (group.kind === "error") {
            return (
              <p key={group.id} className="text-sm text-destructive whitespace-pre-wrap">
                {group.texts[0]}
              </p>
            );
          }
          return (
            <p key={group.id} className="text-sm leading-relaxed whitespace-pre-wrap">
              {group.texts[0]}
            </p>
          );
        })}
        {todos.length > 0 && (
          <ul className="space-y-1 text-sm">
            {todos.map((todo, index) => (
              <li
                key={`${todo.task}-${index}`}
                className={todo.completed ? "text-muted-foreground line-through" : ""}
              >
                {todo.task}
              </li>
            ))}
          </ul>
        )}
        {saved.length > 0 && (
          <div>
            <button
              type="button"
              className="text-sm text-muted-foreground hover:text-foreground"
              onClick={() => setShowSaved((open) => !open)}
            >
              {showSaved ? "Hide page text" : "From the page"}
            </button>
            {showSaved && (
              <div className="mt-2 space-y-2">
                {saved.map((extraction, index) => (
                  <p key={index} className="text-sm whitespace-pre-wrap text-muted-foreground">
                    {typeof extraction === "string" ? extraction : extraction.content}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="pt-3">
        {isRunning && !isAwaitingDecision && (
          <p className="mb-2 text-xs text-muted-foreground">
            {isPaused ? "Paused while you drive" : "Working"}
          </p>
        )}
        {isAwaitingDecision && (
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">Bro thinks this is done</p>
            <Button size="sm" variant="secondary" onClick={() => onSendDecision?.("done")}>
              Looks good
            </Button>
          </div>
        )}
        <div className="rounded-xl border p-2">
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={placeholder}
            rows={2}
            className="min-h-0 resize-none border-0 px-2 py-1 shadow-none focus-visible:ring-0"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
          />
          <div className="flex items-center justify-end gap-2">
            {isRunning && (
              <Button type="button" size="sm" variant="ghost" onClick={onStop}>
                Stop
              </Button>
            )}
            <Button
              type="button"
              size="icon"
              className="rounded-full"
              aria-label={isAwaitingDecision ? "Keep going" : "Send"}
              disabled={!input.trim()}
              onClick={send}
            >
              <ArrowUpIcon />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
