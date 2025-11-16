"use client";

import { useEffect, useRef, useState } from "react";

interface ScreencastViewerProps {
  runId: string | null;
  currentUrl?: string;
  isRunning?: boolean;
}

/**
 * Embedded screencast viewer component for displaying live browser view.
 *
 * Shows Chrome screencast at ~10 FPS with optional manual intervention controls.
 */
export default function ScreencastViewer({ runId, currentUrl, isRunning = false }: ScreencastViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fps, setFps] = useState(0);
  const lastFrameTimeRef = useRef(Date.now());
  const frameCountRef = useRef(0);
  const [viewportDimensions, setViewportDimensions] = useState({ width: 1280, height: 720 });
  const [manualInterventionEnabled, setManualInterventionEnabled] = useState(false);
  const chromeClosedRef = useRef(false);
  const [localUrl, setLocalUrl] = useState(currentUrl ?? "")

  
  useEffect(() => {
    if (!runId || !isRunning) {
      return;
    }

    // Reset chromeClosed flag when runId changes (new run)
    chromeClosedRef.current = false;

    const wsUrl = `ws://localhost:8000/ws/screencast/${runId}`;

    let reconnectTimeout: NodeJS.Timeout;
    let hasConnectedOnce = false;

    const connect = () => {
      // Don't connect/reconnect if Chrome was intentionally closed
      if (chromeClosedRef.current) {
        return;
      }

      hasConnectedOnce = true;
      setError(null);
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          setError(null);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // Check if Chrome was intentionally closed
            if (data.type === "chrome_closed") {
            chromeClosedRef.current = true;
              setIsConnected(false);
              setError("Chrome browser has been closed");
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

                    setViewportDimensions({ width: img.width, height: img.height });

                    ctx.drawImage(img, 0, 0);

                    frameCountRef.current++;
                    const now = Date.now();
                    const elapsed = now - lastFrameTimeRef.current;

                    if (elapsed >= 1000) {
                      setFps(Math.round((frameCountRef.current / elapsed) * 1000));
                      frameCountRef.current = 0;
                      lastFrameTimeRef.current = now;
                    }
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
          setError("WebSocket connection error. Chrome may not be running or the run may have ended.");
          setIsConnected(false);
        };

        ws.onclose = (event) => {
          setIsConnected(false);
          // Only reconnect if it wasn't a clean close and Chrome wasn't intentionally closed
          if (event.code !== 1000 && !chromeClosedRef.current) {
            setError(`Connection lost. Retrying in 2s...`);
            reconnectTimeout = setTimeout(() => {
              connect();
            }, 2000);
          } else if (chromeClosedRef.current) {
            setError("Chrome browser has been closed");
          } 
        };
      } catch (err) {
        console.error("Failed to create WebSocket:", err);
        setError("Failed to connect to screencast stream");
      }
    };

    connect();

    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [runId, isRunning]);

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

    const { x: viewportX, y: viewportY } = canvasToViewportCoords(canvasX, canvasY);

    const button = event.button === 0 ? "left" : event.button === 2 ? "right" : "middle";

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

  const handleCanvasContextMenu = (event: React.MouseEvent<HTMLCanvasElement>) => {
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

    const { x: viewportX, y: viewportY } = canvasToViewportCoords(canvasX, canvasY);

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
    const ws = wsRef.current
    ws?.send(
      JSON.stringify({
        type: "navigation",
        action: "url",
        url: url,
      })
    )
  }

  return (
    <div className="bg-card rounded-lg border shadow-sm p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Browser View</h2>
          {/* Connection status*/}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div
              className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"
                }`}
            />
            <span>{fps} FPS</span>
          </div>
        </div>
        { /* Manual button */}
        <button
          onClick={() => setManualInterventionEnabled(!manualInterventionEnabled)}
          className={`px-3 py-1 text-sm rounded-md font-medium transition-colors ${manualInterventionEnabled
            ? "bg-green-600 hover:bg-green-700 text-white"
            : "bg-secondary hover:bg-secondary/80"
            }`}
        >
          {manualInterventionEnabled ? "Manual: ON" : "Manual: OFF"}
        </button>
      </div>

      {error && (
        <div className={`mb-3 p-3 rounded text-sm flex-shrink-0 ${error.includes("Waiting")
          ? "bg-blue-500/10 border border-blue-500 text-blue-700 dark:text-blue-300"
          : "bg-destructive/10 border border-destructive text-destructive"
          }`}>
          {error}
        </div>
      )}

      {/* URL Bar */}
      <div className="mb-2 px-3 py-2 bg-secondary rounded flex items-center gap-2 text-sm flex-shrink-0">
        {/* Back Button */}
        <button
          onClick={() => {
            const ws = wsRef.current;
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "navigation", action: "back" }));
            }
          }}
          className="p-1.5 hover:bg-accent rounded transition-colors"
          title="Go back"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z"
              clipRule="evenodd"
            />
          </svg>
        </button>

        {/* Reload Button */}
        <button
          onClick={() => {
            const ws = wsRef.current;
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "navigation", action: "reload" }));
            }
          }}
          className="p-1.5 hover:bg-accent rounded transition-colors"
          title="Reload"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
              clipRule="evenodd"
            />
          </svg>
        </button>

        {/* Lock Icon + URL */}
        <div className="flex items-center gap-2 flex-1 min-w-0 px-2 py-1 bg-background rounded">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4 text-muted-foreground flex-shrink-0"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z"
              clipRule="evenodd"
            />
          </svg>
          <input className="text-muted-foreground truncate outline-none border-none"
            value={localUrl || "Connecting..."}
            onChange={e => setLocalUrl(e.target.value)}
            onKeyDown={
              e => {
                if (e.key === "Enter") {
                  updateUrl(localUrl)
                }
              }
            }
          />
        </div>
      </div>

      { /* Screencast */}
      <div className="bg-black rounded overflow-hidden flex-1 flex items-center justify-center">
        <canvas
          ref={canvasRef}
          className="max-w-full max-h-full cursor-pointer object-contain"
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
