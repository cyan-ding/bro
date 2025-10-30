"use client";

import { useEffect, useRef, useState } from "react";

interface ScreencastViewerProps {
  runId: string;
}

/**
 * Embedded screencast viewer component for displaying live browser view.
 *
 * Shows Chrome screencast at ~10 FPS with optional manual intervention controls.
 */
export default function ScreencastViewer({ runId }: ScreencastViewerProps) {
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

  useEffect(() => {
    if (!runId) {
      return;
    }

    // Reset chromeClosed flag when runId changes (new run)
    chromeClosedRef.current = false;
    setError(null);

    const wsUrl = `ws://localhost:8000/ws/screencast/${runId}`;

    let reconnectTimeout: NodeJS.Timeout;

    const connect = () => {
      // Don't reconnect if Chrome was intentionally closed
      if (chromeClosedRef.current) {
        return;
      }
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

        ws.onerror = () => {
          setError("WebSocket connection error. Is Chrome running with CDP?");
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
  }, [runId]);

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

  return (
    <div className="bg-card rounded-lg border shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Browser View</h2>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span>{fps} FPS</span>
          </div>
        </div>
        <button
          onClick={() => setManualInterventionEnabled(!manualInterventionEnabled)}
          className={`px-3 py-1 text-sm rounded-md font-medium transition-colors ${
            manualInterventionEnabled
              ? "bg-green-600 hover:bg-green-700 text-white"
              : "bg-secondary hover:bg-secondary/80"
          }`}
        >
          {manualInterventionEnabled ? "Manual: ON" : "Manual: OFF"}
        </button>
      </div>

      {error && (
        <div className="mb-3 p-3 bg-destructive/10 border border-destructive rounded text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="bg-black rounded overflow-hidden">
        <canvas
          ref={canvasRef}
          className="w-full h-auto cursor-pointer"
          style={{ maxHeight: "500px" }}
          onClick={handleCanvasClick}
          onContextMenu={handleCanvasContextMenu}
          onKeyDown={handleKeyDown}
          onWheel={handleWheel}
          tabIndex={0}
        />
      </div>

      {manualInterventionEnabled && (
        <p className="mt-2 text-xs text-muted-foreground">
          Manual control enabled. Click canvas to focus, then click, type, or scroll to interact.
        </p>
      )}
    </div>
  );
}
