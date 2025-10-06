"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AgentStateResponse } from "@/lib/api";

interface AgentStateProps {
  state: AgentStateResponse | null;
  runStatus: {
    status: string;
    current_iteration: number;
    max_iterations: number;
    last_action: string | null;
  } | null;
}

/**
 * Component for displaying the current agent state including tabs, todo list, and extractions.
 */
export default function AgentState({ state, runStatus }: AgentStateProps) {
  if (!state) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Agent State</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground py-8">
            No agent state available. Start an agent to see state information.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Status Overview */}
      <Card>
        <CardHeader>
          <CardTitle>Status Overview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-sm font-medium">Status</span>
              <div className="mt-1">
                <Badge variant={runStatus?.status === "running" ? "default" : "secondary"}>
                  {runStatus?.status || "unknown"}
                </Badge>
              </div>
            </div>
            <div>
              <span className="text-sm font-medium">Progress</span>
              <div className="mt-1 text-sm">
                {runStatus?.current_iteration || 0} / {runStatus?.max_iterations || 0}
              </div>
            </div>
          </div>
          {runStatus?.last_action && (
            <div>
              <span className="text-sm font-medium">Last Action</span>
              <div className="mt-1">
                <code className="text-sm bg-muted px-2 py-1 rounded">{runStatus.last_action}</code>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Browser Tabs */}
      <Card>
        <CardHeader>
          <CardTitle>Browser Tabs</CardTitle>
        </CardHeader>
        <CardContent>
          {state.tabs.length === 0 ? (
            <div className="text-sm text-muted-foreground">No tabs open</div>
          ) : (
            <div className="space-y-2">
              {state.tabs.map((tab) => (
                <div
                  key={tab.index}
                  className={`p-3 rounded-lg border ${
                    tab.index === state.current_tab_index ? "border-primary bg-muted" : ""
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <Badge variant="outline" className="mt-0.5">
                      {tab.index}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">{tab.title}</div>
                      <div className="text-xs text-muted-foreground truncate">{tab.url}</div>
                    </div>
                    {tab.index === state.current_tab_index && (
                      <Badge variant="default" className="text-xs">
                        Active
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Todo List */}
      <Card>
        <CardHeader>
          <CardTitle>Todo List</CardTitle>
        </CardHeader>
        <CardContent>
          {state.todo_list.length === 0 ? (
            <div className="text-sm text-muted-foreground">No todos</div>
          ) : (
            <div className="space-y-2">
              {state.todo_list.map((todo, index) => (
                <div key={index} className="flex items-start gap-2">
                  <div className={`w-4 h-4 mt-0.5 rounded border ${
                    todo.completed ? "bg-primary border-primary" : "border-muted-foreground"
                  }`}>
                    {todo.completed && (
                      <svg
                        className="w-4 h-4 text-primary-foreground"
                        fill="none"
                        strokeWidth="2"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                  <span className={`text-sm ${todo.completed ? "line-through text-muted-foreground" : ""}`}>
                    {todo.content}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Extractions */}
      <Card>
        <CardHeader>
          <CardTitle>Extracted Content</CardTitle>
        </CardHeader>
        <CardContent>
          {state.extractions.length === 0 ? (
            <div className="text-sm text-muted-foreground">No extractions yet</div>
          ) : (
            <ScrollArea className="h-[300px] w-full">
              <div className="space-y-3">
                {state.extractions.map((extraction, index) => (
                  <div key={index}>
                    <div className="text-xs text-muted-foreground mb-1">Extraction {index + 1}</div>
                    <div className="text-sm bg-muted p-3 rounded-lg whitespace-pre-wrap">
                      {extraction}
                    </div>
                    {index < state.extractions.length - 1 && <Separator className="mt-3" />}
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Action History */}
      <Card>
        <CardHeader>
          <CardTitle>Action History</CardTitle>
        </CardHeader>
        <CardContent>
          {state.action_history.length === 0 ? (
            <div className="text-sm text-muted-foreground">No actions yet</div>
          ) : (
            <ScrollArea className="h-[400px] w-full">
              <div className="space-y-3">
                {state.action_history.slice().reverse().map((action, index) => (
                  <div key={index}>
                    <div className="flex items-start gap-2">
                      <Badge variant="outline" className="mt-0.5">
                        #{action.iteration}
                      </Badge>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <code className="text-sm font-medium">{action.action_name}</code>
                          <span className="text-xs text-muted-foreground">
                            {new Date(action.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        {Object.keys(action.arguments).length > 0 && (
                          <div className="text-xs">
                            <span className="text-muted-foreground">Args: </span>
                            <code className="bg-muted px-1 py-0.5 rounded">
                              {JSON.stringify(action.arguments)}
                            </code>
                          </div>
                        )}
                        <div className="text-xs text-muted-foreground">{action.result}</div>
                      </div>
                    </div>
                    {index < state.action_history.length - 1 && <Separator className="mt-3" />}
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
