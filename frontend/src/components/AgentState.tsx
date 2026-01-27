"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AgentStateResponse } from "@/lib/models";

interface AgentStateProps {
  state: AgentStateResponse | null;
  runStatus: string | null;
}

/**
 * Component for displaying the current agent state including tabs, todo list, and extractions.
 */
export default function AgentState({
  state,
  runStatus,
}: AgentStateProps) {
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
  const lastAction = state.action_history.length > 0 
    ? state.action_history[state.action_history.length - 1] 
    : null;
  return (
    <Card className="h-[calc(100vh-12rem)]">
      <CardHeader>
        <CardTitle>Agent State</CardTitle>
      </CardHeader>
      <CardContent className="h-[calc(100%-5rem)] overflow-auto space-y-4">
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
                  <Badge
                    variant={runStatus === "running" ? "default" : "secondary"}
                  >
                    {runStatus || "unknown"}
                  </Badge>
                </div>
              </div>
              <div>
                <span className="text-sm font-medium">Progress</span>
                <div className="mt-1 text-sm">
                  {lastAction?.iteration ?? 0} / {state.max_iterations || 0}
                </div>
              </div>
            </div>

            <div>
              <span className="text-sm font-medium">Last Action</span>
              <div className="mt-1">
                <code className="text-sm bg-muted px-2 py-1 rounded">
                  {lastAction?.action_name ?? "No actions yet"}
                </code>
              </div>
            </div>
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
                {state.tabs.map((tab, mapIndex) => (
                  <div
                    key={`tab-${mapIndex}`}
                    className={`p-3 rounded-lg border ${
                      tab.index === state.current_tab_index
                        ? "border-primary bg-muted"
                        : ""
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <Badge variant="outline" className="mt-0.5">
                        {tab.index}
                      </Badge>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">
                          {tab.title}
                        </div>
                        <div className="text-xs text-muted-foreground truncate">
                          {tab.url}
                        </div>
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
                  <div key={`todo-${index}`} className="flex items-start gap-2">
                    <div
                      className={`w-4 h-4 mt-0.5 rounded border ${
                        todo.completed
                          ? "bg-primary border-primary"
                          : "border-muted-foreground"
                      }`}
                    >
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
                    <span
                      className={`text-sm ${todo.completed ? "line-through text-muted-foreground" : ""}`}
                    >
                      {todo.task}
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
              <div className="text-sm text-muted-foreground">
                No extractions yet
              </div>
            ) : (
              <ScrollArea className="h-[300px] w-full">
                <div className="space-y-3">
                  {state.extractions.map((extraction, index) => {
                    const isString = typeof extraction === "string";
                    const extractionObj = !isString ? extraction : null;

                    return (
                      <div key={`extraction-${index}`}>
                        <div className="text-xs text-muted-foreground mb-1">
                          Extraction {index + 1}
                          {extractionObj?.source_title && (
                            <span className="ml-2 font-medium">
                              {extractionObj.source_title}
                            </span>
                          )}
                        </div>
                        <div className="text-sm bg-muted p-3 rounded-lg whitespace-pre-wrap">
                          {isString ? extraction : extractionObj?.content}
                        </div>
                        {index < state.extractions.length - 1 && (
                          <Separator className="mt-3" />
                        )}
                      </div>
                    );
                  })}
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
              <div className="text-sm text-muted-foreground">
                No actions yet
              </div>
            ) : (
              <ScrollArea className="h-[400px] w-full">
                <div className="space-y-3">
                  {state.action_history
                    .slice()
                    .reverse()
                    .map((action, index) => (
                      <div key={`action-${index}`}>
                        <div className="flex items-start gap-2">
                          <Badge variant="outline" className="mt-0.5">
                            #{action.iteration ?? 0}
                          </Badge>
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-2">
                              <code className="text-sm font-medium">
                                {action.action_name}
                              </code>
                              {action.timestamp && (
                                <span className="text-xs text-muted-foreground">
                                  {new Date(
                                    action.timestamp
                                  ).toLocaleTimeString()}
                                </span>
                              )}
                            </div>
                            {Object.keys(action.arguments).length > 0 && (
                              <div className="text-xs">
                                <span className="text-muted-foreground">
                                  Args:{" "}
                                </span>
                                <code className="bg-muted px-1 py-0.5 rounded">
                                  {JSON.stringify(action.arguments)}
                                </code>
                              </div>
                            )}
                            <div className="text-xs text-muted-foreground">
                              {action.result}
                            </div>
                          </div>
                        </div>
                        {index < state.action_history.length - 1 && (
                          <Separator className="mt-3" />
                        )}
                      </div>
                    ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </CardContent>
    </Card>
  );
}
