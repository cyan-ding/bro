"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { ArrowLeft, RotateCw } from "lucide-react";

interface ScreencastViewerProps {
  isRunning?: boolean;
  onDrivingChange?: (driving: boolean) => void;
}

/**
 * Embedded screencast viewer component for displaying live browser view.
 *
 * Shows Chrome screencast at ~10 FPS with optional manual intervention controls.
 */
export default function ScreencastViewer({
  isRunning = false,
  onDrivingChange,
}: ScreencastViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewportDimensions, setViewportDimensions] = useState({
    width: 1280,
    height: 720,
  });
  const [manualInterventionEnabled, setManualInterventionEnabled] =
    useState(false);
  const chromeClosedRef = useRef(false);
  const [localUrl, setLocalUrl] = useState("");

  useEffect(() => {
    if (!isRunning) {
      return;
    }

    // Reset chromeClosed flag
    chromeClosedRef.current = false;

    const wsUrl = `ws://localhost:8000/ws/screencast`;

    const connect = () => {
      // Don't connect/reconnect if Chrome was intentionally closed
      if (chromeClosedRef.current) {
        return;
      }
      setError(null);
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setError(null);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // Check if Chrome was intentionally closed
            if (data.type === "chrome_closed") {
              chromeClosedRef.current = true;
              setError("The browser closed");
              return;
            }

            if (data.type === "url" && data.url) {
              setLocalUrl(data.url);
              return;
            }

            if (data.type === "frame" && data.data) {
              const img = new Image();
              img.onload = () => {
                const canvas = canvasRef.current;
                if (canvas) {
                  const ctx = canvas.getContext("2d");
                  if (ctx) {
                    canvas.width = img.width;
                    canvas.height = img.height;

                    setViewportDimensions({
                      width: data.metadata?.deviceWidth ?? img.width,
                      height: data.metadata?.deviceHeight ?? img.height,
                    });

                    ctx.drawImage(img, 0, 0);
                  }
                }
              };

              img.onerror = () => {
                console.error("Failed to load frame image");
              };

              img.src = `data:image/jpeg;base64,${data.data}`;
            }
          } catch (err) {
            console.error("Error processing frame:", err);
          }
        };

        ws.onerror = (err) => {
          console.error("[Screencast] WebSocket error:", err);
          setError("The page isn't available right now.");
        };

        ws.onclose = (event) => {
          if (event.code !== 1000 && !chromeClosedRef.current) {
            setError("The page disconnected.");
          } else if (chromeClosedRef.current) {
            setError("The browser closed");
          }
        };
      } catch (err) {
        console.error("Failed to create WebSocket:", err);
        setError("Failed to connect to screencast stream");
      }
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      setManualInterventionEnabled(false);
      onDrivingChange?.(false);
    };
  }, [isRunning, onDrivingChange]);

  const setDriving = (driving: boolean) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    ws.send(JSON.stringify({ type: "control", driving }));
    setManualInterventionEnabled(driving);
    onDrivingChange?.(driving);
  };

  const canvasToViewportCoords = (canvasX: number, canvasY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };

    const rect = canvas.getBoundingClientRect();
    const scaleX = viewportDimensions.width / rect.width;
    const scaleY = viewportDimensions.height / rect.height;

    return {
      x: Math.round(canvasX * scaleX),
      y: Math.round(canvasY * scaleY),
    };
  };

  const handleCanvasClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!manualInterventionEnabled) {
      return;
    }

    const canvas = canvasRef.current;
    const ws = wsRef.current;

    if (!canvas || !ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const canvasX = event.clientX - rect.left;
    const canvasY = event.clientY - rect.top;

    const { x: viewportX, y: viewportY } = canvasToViewportCoords(
      canvasX,
      canvasY
    );

    const button =
      event.button === 0 ? "left" : event.button === 2 ? "right" : "middle";

    ws.send(
      JSON.stringify({
        type: "input",
        action: "click",
        x: viewportX,
        y: viewportY,
        button: button,
      })
    );
  };

  const handleCanvasContextMenu = (
    event: React.MouseEvent<HTMLCanvasElement>
  ) => {
    event.preventDefault();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (!manualInterventionEnabled) {
      return;
    }

    const ws = wsRef.current;

    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }

    event.preventDefault();

    ws.send(
      JSON.stringify({
        type: "input",
        action: "keypress",
        key: event.key,
        text: event.key.length === 1 ? event.key : "",
      })
    );
  };

  const handleWheel = (event: React.WheelEvent<HTMLCanvasElement>) => {
    if (!manualInterventionEnabled) {
      return;
    }

    const ws = wsRef.current;
    const canvas = canvasRef.current;

    if (!ws || ws.readyState !== WebSocket.OPEN || !canvas) {
      return;
    }

    event.preventDefault();

    const rect = canvas.getBoundingClientRect();
    const canvasX = event.clientX - rect.left;
    const canvasY = event.clientY - rect.top;

    const { x: viewportX, y: viewportY } = canvasToViewportCoords(
      canvasX,
      canvasY
    );

    ws.send(
      JSON.stringify({
        type: "input",
        action: "scroll",
        x: viewportX,
        y: viewportY,
        deltaY: event.deltaY,
      })
    );
  };

  const updateUrl = (url: string) => {
    const ws = wsRef.current;
    ws?.send(
      JSON.stringify({
        type: "navigation",
        action: "url",
        url: url,
      })
    );
  };

  if (!isRunning) {
    return (
      <div className="flex h-full min-w-0 items-center justify-center rounded-xl border border-dashed px-6">
        <p className="text-center text-sm text-muted-foreground">The page shows up here while Bro works.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-2">
      <div className="flex items-center justify-end">
        <Button
          size="sm"
          variant={manualInterventionEnabled ? "default" : "secondary"}
          onClick={() => setDriving(!manualInterventionEnabled)}
        >
          {manualInterventionEnabled ? "Hand back" : "I'll drive"}
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {manualInterventionEnabled && (
        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="ghost"
            onClick={() => {
              const ws = wsRef.current;
              if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "navigation", action: "back" }));
              }
            }}
            aria-label="Go back"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => {
              const ws = wsRef.current;
              if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "navigation", action: "reload" }));
              }
            }}
            aria-label="Reload"
          >
            <RotateCw className="h-4 w-4" />
          </Button>
          <Input
            className="h-8"
            value={localUrl}
            onChange={(e) => setLocalUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                updateUrl(e.currentTarget.value);
              }
            }}
            aria-label="Page address"
          />
        </div>
      )}

      <div className="flex flex-1 items-center justify-center overflow-hidden rounded-xl bg-black">
        <canvas
          ref={canvasRef}
          className="max-h-full max-w-full object-contain"
          onClick={handleCanvasClick}
          onContextMenu={handleCanvasContextMenu}
          onKeyDown={handleKeyDown}
          onWheel={handleWheel}
          tabIndex={0}
        />
      </div>
    </div>
  );
}
