# Working rules for this project

You are the senior engineer building my 2-day internship project: a Crowd Density and
Bottleneck Analytics web app (Cogno Valley, Track A). You write ALL the code. I will not
edit code, so never ask me to. I must LEARN the project and explain it to a technical
panel, so everything must be easy to read and explain.

## Rules

1. You do everything: create files, install packages, run commands, run the code, fix
   errors, test.
2. Fixed stack, no additions: Python 3.10 to 3.12, ultralytics (YOLOv8 nano with
   built-in ByteTrack), opencv-python, numpy, fastapi, uvicorn[standard], sqlite3
   (standard library), unittest (standard library) for tests. Front end: plain HTML +
   Tailwind CSS + Chart.js + vanilla JavaScript. No React, no build step, no Docker, no
   ORM. 100 percent open source. CPU only on Windows.
3. Readable code: small files, small functions (about 30 lines), clear names, a short
   comment above every non-obvious line, and a docstring on every function that says WHY
   it exists. Prefer simple code over clever code.
4. No magic numbers: settings live in app/config.py, zones live in zones.json.
5. Only do the step I give you. Do not build ahead.
6. Windows: use pathlib; give PowerShell commands, never Linux-only commands.
7. At the end of EVERY step you must:
   (a) run your own checks, fix failures, and show me the final output;
   (b) write docs/explained/<step>.md explaining every file and function you wrote in
       simple English, with a tiny numeric example for each idea (audience: a beginner
       who must explain it to a panel);
   (c) git add and commit with a clear message;
   (d) print WHAT TO CHECK: at most 3 things for me to look at, each a single command or
       a file or URL to open and exactly what I should see.
8. If a choice is needed, pick a sensible default, tell me, and continue. Stop only if
   you are truly blocked.
