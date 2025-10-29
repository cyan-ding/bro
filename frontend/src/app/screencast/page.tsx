"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

export default function ScreencastPage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("runId") || "default";

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fps, setFps] = useState(0);
  const lastFrameTimeRef = useRef(Date.now());
  const frameCountRef = useRef(0);

  useEffect(() => {
    const wsUrl = `ws://localhost:8000/ws/screencast/${runId}`;
    console.log("Attempting to connect to:", wsUrl);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected successfully");
        setIsConnected(true);
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "frame" && data.data) {
            // Decode base64 JPEG and render to canvas
            const img = new Image();
            img.onload = () => {
              const canvas = canvasRef.current;
              if (canvas) {
                const ctx = canvas.getContext("2d");
                if (ctx) {
                  // Set canvas size to match image
                  canvas.width = img.width;
                  canvas.height = img.height;

                  // Draw image
                  ctx.drawImage(img, 0, 0);

                  // Calculate FPS
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

            // Set base64 data as image source
            img.src = `data:image/jpeg;base64,${data.data}`;
          }
        } catch (err) {
          console.error("Error processing frame:", err);
          setError("Error processing frame");
        }
      };

      ws.onerror = (event) => {
        console.error("WebSocket error:", event);
        setError(`WebSocket connection error. Make sure backend is running on port 8000 and Chrome CDP is active.`);
        setIsConnected(false);
      };

      ws.onclose = (event) => {
        console.log("WebSocket disconnected. Code:", event.code, "Reason:", event.reason);
        setError(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason || "Unknown"}`);
        setIsConnected(false);
      };

    } catch (err) {
      console.error("Failed to create WebSocket:", err);
      setError("Failed to connect to screencast stream");
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [runId]);

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-2">Agent Screencast</h1>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  isConnected ? "bg-green-500" : "bg-red-500"
                }`}
              />
              <span>{isConnected ? "Connected" : "Disconnected"}</span>
            </div>
            <div>Run ID: {runId}</div>
            <div>FPS: {fps}</div>
          </div>
        </div>

        {error && (
          <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        <div className="bg-gray-800 rounded-lg p-4 shadow-xl">
          <canvas
            ref={canvasRef}
            className="w-full h-auto bg-black rounded"
            style={{ maxWidth: "100%", maxHeight: "calc(100vh - 250px)" }}
          />
        </div>

        <div className="mt-4 text-sm text-gray-400">
          <p>
            This page shows a live view of the agent&apos;s browser at approximately 10
            FPS.
          </p>
          <p className="mt-2">
            The stream is powered by Chrome DevTools Protocol (CDP) screencast
            mode.
          </p>
        </div>
      </div>
    </div>
  );
}
