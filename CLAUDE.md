## Contributing to Bro

**Bro** is an AI agent that autonomously interacts with the web. It takes a user-defined task, splits it into multiple subtasks to be run on parallel, which are assigned to other ai agents to complete. Bro navigates web pages using Chromium via Playwright, processes HTML, and repeatedly queries a language model (like `gpt-4o`) to decide the next action—until the task is completed.

### Development Rules

- Always use `uv` instead of `pip`
  For deterministic and fast dependency installs.

- Always reference the [pyproject.toml](mdc:pyproject.toml) instead of creating a new `requirements.txt` file.

- Always add type annotations and return types and ensure all lint errors are resolved

- Do not do any more than asked. Keep code minimal, simple, and readible.

- Never add `console.log` logs in any `js` files

- Never create extra testing or summary .MD files in any circumstances

- Before making any edits, outline what changes you will be making

- If you get stuck on a problem or believe it is a dead end, suggest alternatives

- When handling json response parsing in Python, do not chain hasattr() or get(), use Pydantic models instead

- Always use Shadcn components in .jsx files instead of native HTML is possible. 

---