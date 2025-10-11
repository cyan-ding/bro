"use client";

import { useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { LogEvent } from "@/lib/api";

interface LogStreamProps {
  logs: LogEvent[];
}

/**
 * Component for displaying a stream of log events from the agent.
 */
export default function LogStream({ logs }: LogStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const getEventBadgeVariant = (eventType: string) => {
    switch (eventType) {
      case "action":
        return "default";
      case "thinking":
        return "secondary";
      case "error":
        return "destructive";
      case "status":
        return "outline";
      default:
        return "outline";
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  const renderLogData = (event: LogEvent) => {
    const data = event.data;
    switch (event.event_type) {
      case "thinking":
        return (
          <div className="space-y-2 text-sm">
            {data.action_data.structured_output?.thinking && (
              <div>
                <span className="font-medium">Thinking: </span>
                <span className="text-muted-foreground">{data.action_data.structured_output?.thinking}</span>
              </div>
            )}
            {data.action_data.structured_output?.evaluation_previous_actions && (
              <div>
                <span className="font-medium">Evaluation: </span>
                <span className="text-muted-foreground">{data.action_data.structured_output?.evaluation_previous_actions}</span>
              </div>
            )}
            {data.action_data.structured_output?.memory && (
              <div>
                <span className="font-medium">Memory: </span>
                <span className="text-muted-foreground">{data.action_data.structured_output?.memory}</span>
              </div>
            )}
            {data.action_data.structured_output?.next_goal && (
              <div>
                <span className="font-medium">Next Goal: </span>
                <span className="text-muted-foreground">{data.action_data.structured_output?.next_goal}</span>
              </div>
            )}
          </div>
        );

      case "action":
        return (
          <div className="space-y-1 text-sm">
            <div>
              <span className="font-medium">Action: </span>
              <code className="bg-muted px-1 py-0.5 rounded">{data.action_data.action_name}</code>
            </div>
            {data.action_data.arguments && Object.keys(data.action_data.arguments).length > 0 && (
              <div>
                <span className="font-medium">Arguments: </span>
                <code className="bg-muted px-1 py-0.5 rounded text-xs">
                  {JSON.stringify(data.action_data.arguments)}
                </code>
              </div>
            )}
            {data.action_data.result && (
              <div>
                <span className="font-medium">Result: </span>
                <span className="text-muted-foreground">{data.action_data.result}</span>
              </div>
            )}
          </div>
        );

      case "status":
        return (
          <div className="text-sm">
            <span className="text-muted-foreground">{data.message}</span>
          </div>
        );

      case "error":
        return (
          <div className="text-sm text-destructive">
            <span className="font-medium">Error: </span>
            <span>{data.error || data.message}</span>
          </div>
        );

      case "user_input":
        return (
          <div className="text-sm">
            <span className="font-medium">User Input: </span>
            <span className="text-muted-foreground">{data.message}</span>
          </div>
        );

      case "user_decision":
        return (
          <div className="text-sm">
            <span className="font-medium">Decision: </span>
            <span className="text-muted-foreground">{data.decision}</span>
            {data.additional_instructions && (
              <div className="mt-1">
                <span className="font-medium">Instructions: </span>
                <span className="text-muted-foreground">{data.additional_instructions}</span>
              </div>
            )}
          </div>
        );

      case "iteration_start":
        return (
          <div className="text-sm font-medium">
            Iteration {data.action_data.iteration}
          </div>
        );

      default:
        return (
          <div className="text-sm text-muted-foreground">
            {JSON.stringify(data)}
          </div>
        );
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent Logs</CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-full w-full pr-4" ref={scrollRef}>
          {logs.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              No logs yet. Start an agent to see activity.
            </div>
          ) : (
            <div className="space-y-3">
              {logs.map((log, index) => (
                <div key={index}>
                  <div className="flex items-start gap-2">
                    <Badge variant={getEventBadgeVariant(log.event_type)} className="mt-0.5">
                      {log.event_type}
                    </Badge>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>{formatTimestamp(log.timestamp || "")}</span>
                        <span>•</span>
                        <span>Iteration {log.iteration}</span>
                      </div>
                      {renderLogData(log)}
                    </div>
                  </div>
                  {index < logs.length - 1 && <Separator className="mt-3" />}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
