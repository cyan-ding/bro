import type { ActionContext, LogEvent } from "@/lib/models";

export type ConversationItem = {
  id: string;
  kind: "user" | "step" | "answer" | "error";
  text: string;
};

const CONTEXT_MARKER = "\n\nFor context, the previous task was ";

export function withPreviousContext(message: string, task: string, answer: string): string {
  return `${message}${CONTEXT_MARKER}"${task}" and the answer was "${answer}".`;
}

function withoutPreviousContext(prompt: string): string {
  return prompt.split(CONTEXT_MARKER)[0];
}

function commandText(action: Pick<ActionContext, "action_name" | "arguments" | "description">): string {
  const command = action.arguments.command;
  if (typeof command === "string" && command.trim()) {
    return command;
  }
  if (action.description && action.description.trim()) {
    return action.description;
  }
  return action.action_name;
}

function siteName(target: string): string {
  try {
    return new URL(target).hostname.replace(/^www\./, "");
  } catch {
    return target;
  }
}

function describe(command: string, result: string): ConversationItem | null {
  const verb = command.trim().split(/\s+/)[0] ?? "";
  const quoted = command.match(/"([\s\S]*)"\s*$/)?.[1];
  const rest = command.slice(verb.length).trim();
  if (!verb) {
    return null;
  }
  if (verb === "done") {
    const fromResult = result.replace(/^AWAIT_USER_DECISION:\s*/, "").trim();
    const answer = quoted || (fromResult && fromResult !== "finished" ? fromResult : "");
    return { id: "", kind: "answer", text: answer || "Done" };
  }
  if (verb === "click") return { id: "", kind: "step", text: "Clicked" };
  if (verb === "type") return { id: "", kind: "step", text: quoted ? `Typed “${quoted}”` : "Typed" };
  if (verb === "press") return { id: "", kind: "step", text: rest ? `Pressed ${rest.replace(/"/g, "")}` : "Pressed a key" };
  if (verb === "scroll") return { id: "", kind: "step", text: "Scrolled" };
  if (verb === "find") return { id: "", kind: "step", text: quoted ? `Looked for “${quoted}”` : "Looked through the page" };
  if (verb === "goto" || verb === "open" || verb === "navigate") {
    const target = quoted || rest;
    return { id: "", kind: "step", text: target ? `Opened ${siteName(target)}` : "Opened a page" };
  }
  if (verb === "note") return { id: "", kind: "step", text: quoted || "Noted" };
  if (verb === "extract") return { id: "", kind: "step", text: "Read the page" };
  return { id: "", kind: "step", text: verb.charAt(0).toUpperCase() + verb.slice(1) };
}

function describeAction(action: Pick<ActionContext, "action_name" | "arguments" | "description" | "result">): ConversationItem | null {
  const command = commandText(action);
  const described = describe(command, action.result ?? "");
  if (!described || !described.text.trim()) {
    return null;
  }
  const detailed = action.description?.trim();
  if (described.kind === "step" && detailed && detailed !== command.trim()) {
    return { ...described, text: detailed };
  }
  return described;
}

function pushAction(items: ConversationItem[], action: ActionContext, index: number): void {
  const described = describeAction(action);
  if (described) {
    items.push({ ...described, id: `action-${index}-${described.text}` });
  }
}

export function buildConversation(
  userPrompt: string | null,
  logs: LogEvent[],
  actions: ActionContext[] | undefined,
): ConversationItem[] {
  const items: ConversationItem[] = [];
  if (userPrompt && userPrompt.trim()) {
    items.push({ id: "task", kind: "user", text: withoutPreviousContext(userPrompt).trim() });
  }

  logs.forEach((log, index) => {
    if (log.event_type === "error") {
      items.push({
        id: `log-${index}`,
        kind: "error",
        text: log.error || log.message || "Something went wrong",
      });
      return;
    }
    if (log.event_type === "user_input" && log.message && log.message.trim() !== userPrompt?.trim()) {
      items.push({ id: `log-${index}`, kind: "user", text: log.message });
      return;
    }
    const instructions = log.decision?.additional_instructions;
    if (log.event_type === "user_decision" && instructions && instructions.trim()) {
      items.push({ id: `log-${index}`, kind: "user", text: instructions.trim() });
      return;
    }
    if (log.event_type === "control" && log.message) {
      items.push({ id: `log-${index}`, kind: "step", text: log.message });
      return;
    }
    if (log.event_type === "action" && log.action_context) {
      const described = describeAction(log.action_context);
      if (described) {
        items.push({ ...described, id: `log-${index}` });
      }
    }
  });

  const hasWork = items.some((item) => item.kind === "step" || item.kind === "answer");
  if (!hasWork) {
    (actions ?? []).forEach((action, index) => pushAction(items, action, index));
  }

  return items.filter((item, index) => {
    const previous = items[index - 1];
    return !(item.kind === "answer" && previous?.kind === "answer" && previous.text === item.text);
  });
}
