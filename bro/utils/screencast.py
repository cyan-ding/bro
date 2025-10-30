import asyncio
import json
from typing import Any, Callable, Dict, Optional

import aiohttp


class ScreencastClient:
    """
    Client for managing Chrome DevTools Protocol screencast streaming.

    Connects to Chrome via CDP and captures screencast frames at ~10 FPS.
    Each frame must be acknowledged before Chrome sends the next one.
    """

    def __init__(self, cdp_url: str = "http://localhost:9222"):
        """
        Initialize CDP screencast client.

        Args:
            cdp_url: Chrome DevTools Protocol endpoint URL
        """
        self.cdp_url = cdp_url
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.frame_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.message_id = 0

    async def connect(self) -> None:
        """
        Connect to Chrome via CDP WebSocket.

        Establishes WebSocket connection to the first available Chrome tab.
        """
        self.session = aiohttp.ClientSession()

        # Get list of targets (tabs)
        async with self.session.get(f"{self.cdp_url}/json") as resp:
            targets = await resp.json()
            if not targets:
                raise Exception("No Chrome tabs found")

            # Use first tab
            ws_url = targets[0]["webSocketDebuggerUrl"]

        # Connect to WebSocket
        self.ws = await self.session.ws_connect(ws_url)
        print(f"✅ Connected to CDP WebSocket: {ws_url}")

    async def _send_command(self, method: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Send a CDP command via WebSocket.

        Args:
            method: CDP method name (e.g., "Page.startScreencast")
            params: Optional parameters for the command

        Returns:
            Message ID for tracking responses
        """
        if not self.ws:
            raise Exception("WebSocket not connected")

        self.message_id += 1
        message = {
            "id": self.message_id,
            "method": method,
            "params": params or {}
        }

        await self.ws.send_json(message)
        return self.message_id

    async def start_screencast(
        self,
        frame_callback: Callable[[Dict[str, Any]], None],
        quality: int = 100,
        every_nth_frame: int = 1,
        max_width: int = 1280,
        max_height: int = 720
    ) -> None:
        """
        Start capturing screencast frames from Chrome.

        Args:
            frame_callback: Async callback function to receive frame data
            quality: JPEG quality (0-100)
            every_nth_frame: Capture every Nth frame (6 = ~10 FPS at 60Hz)
            max_width: Maximum frame width in pixels
            max_height: Maximum frame height in pixels
        """
        if not self.ws:
            raise Exception("Must connect() before starting screencast")

        self.frame_callback = frame_callback
        self.running = True

        # Start screencast
        await self._send_command("Page.startScreencast", {
            "format": "jpeg",
            "quality": quality,
            "everyNthFrame": every_nth_frame,
            "maxWidth": max_width,
            "maxHeight": max_height
        })

        print(f"✅ Screencast started (quality={quality}, every {every_nth_frame}th frame)")

        # Start listening for frames
        asyncio.create_task(self._listen_for_frames())

    async def _listen_for_frames(self) -> None:
        """
        Listen for screencast frames and acknowledgements.

        Receives frames from Chrome, calls the callback, and sends acknowledgements.
        """
        if not self.ws:
            return

        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)

                    # Handle screencast frame events
                    if data.get("method") == "Page.screencastFrame":
                        params = data.get("params", {})
                        session_id = params.get("sessionId")
                        frame_data = params.get("data")  # Base64-encoded JPEG

                        if frame_data and self.frame_callback:
                            # Call the callback with frame data
                            await self.frame_callback({
                                "data": frame_data,
                                "metadata": params.get("metadata", {})
                            })

                        # Acknowledge the frame so Chrome sends the next one
                        if session_id:
                            await self._send_command("Page.screencastFrameAck", {
                                "sessionId": session_id
                            })

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"❌ WebSocket error: {msg.data}")
                    break

        except Exception as e:
            print(f"❌ Error listening for frames: {e}")
        finally:
            self.running = False

    async def stop_screencast(self) -> None:
        """
        Stop capturing screencast frames.
        """
        if not self.ws or not self.running:
            return

        self.running = False
        await self._send_command("Page.stopScreencast")
        print("✅ Screencast stopped")

    async def dispatch_mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """
        Dispatch a mouse click at the specified coordinates.

        Args:
            x: X coordinate in viewport
            y: Y coordinate in viewport
            button: Mouse button ("left", "right", "middle")
        """
        if not self.ws:
            raise Exception("WebSocket not connected")

        # Send mousePressed event
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })

        # Send mouseReleased event
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })

        print(f"🖱️  Mouse click dispatched at ({x}, {y}) with {button} button")

    async def dispatch_key_event(self, key: str, text: str = "") -> None:
        """
        Dispatch a keyboard event.

        Args:
            key: Key identifier (e.g., "Enter", "a", "Backspace")
            text: Text to insert (for character keys)
        """
        if not self.ws:
            raise Exception("WebSocket not connected")

        # Send keyDown
        await self._send_command("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key,
            "text": text
        })

        # Send keyUp
        await self._send_command("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key,
            "text": text
        })

        print(f"⌨️  Key event dispatched: {key}")

    async def dispatch_scroll(self, x: int, y: int, delta_y: int) -> None:
        """
        Dispatch a scroll event using mouseWheel.

        Args:
            x: X coordinate to scroll from
            y: Y coordinate to scroll from
            delta_y: Vertical scroll distance (negative = scroll down)
        """
        if not self.ws:
            raise Exception("WebSocket not connected")

        # Use Input.dispatchMouseEvent with type "mouseWheel" for more responsive scrolling
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": x,
            "y": y,
            "deltaX": 0,
            "deltaY": delta_y
        })

        print(f"📜 Scroll dispatched at ({x}, {y}) with delta {delta_y}")

    async def close(self) -> None:
        """
        Close the WebSocket connection and session.
        """
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        print("✅ CDP screencast client closed")
