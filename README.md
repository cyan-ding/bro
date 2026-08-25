# Bro

Bro is a locally run browser-use agent inspired by [Browser-Use](https://github.com/browser-use/browser-use).

## Functions

Bro is model agnostic and you can use the dashboard to start and view runs.
- Onboarding sets up Chrome, API keys, storage, and which models to use (from providers your keys unlock).
- There is an optional Supabase integration to store data in the cloud. All data flows to your own account.
- The other option is local storage on disk.

## Tools Used

- Bro connects to your installed Chrome over CDP (via Patchright) and uses the DOM to find clickable elements.
- Frontend is Next.js in an Electron app; backend is a FastAPI agent loop.
