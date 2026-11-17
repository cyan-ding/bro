"""Head-to-head with browser-use: shared screencast recorder, runners for both agents, scoring and side-by-side videos.

Bro's side runs in the project environment. browser-use runs in its own environment, pinned:

    uv venv .venv-browser-use --python 3.12
    VIRTUAL_ENV=.venv-browser-use uv pip install browser-use==1.0.3 pillow
"""
