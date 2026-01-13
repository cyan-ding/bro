# Bro

Bro is a locally run browser use agent inspired by [Browser-Use](https://github.com/browser-use/browser-use). 

## Functions

Bro is model agnostic and you can use the dashboard to view runs.
- There is an optional Supabase integration to store data on the cloud. All data flows to your own account.
- The default is local storage (disk).
- Select and download open source models in the onboarding. 

## Tools Used

- Bro uses Playwright to interface with Chrome, and uses the Document Object Model (DOM) to find clickable elements
- Front end is built using Next.js, backend is a simple agent loop interfacing with Fast API
