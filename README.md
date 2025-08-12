# Bro

**Bro** is an AI agent that autonomously interacts with the web. It takes a user-defined task, splits it into multiple subtasks to be run in parallel, which are assigned to other AI agents to complete. Bro navigates web pages using Chromium via Playwright, processes HTML, and repeatedly queries a language model (like `gpt-4o`) to decide the next action—until the task is completed.

## Features

- **Autonomous Web Navigation**: Uses Playwright to interact with web pages
- **Multi-Agent Architecture**: Splits tasks among specialized AI agents (CEO, Manager, Worker)
- **Computer Vision**: Integrates YOLO models for visual understanding
- **Parallel Task Execution**: Runs multiple subtasks simultaneously for efficiency
- **Flexible AI Backends**: Supports multiple language models (GPT, Claude, Cerebras)





