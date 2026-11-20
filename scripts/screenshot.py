"""Screenshot a page with headless Chrome once a CSS selector appears (CDP over websockets).

Retake the hand-off proof with the demo window running (``uv run rescue-crew-demo``):

    uv run python scripts/screenshot.py \
        "http://127.0.0.1:8765/?ticket=LIS-TKT-0075&play=replay&refund=1&fast=1" \
        ".manual ~ .call" docs/demo/lis-tkt-0075-handoff.png .chrome-shot 1280 640

The page plays the recorded run, presses "Try the refund anyway", and the shot is taken only
once the blocked refund row is on screen. CHROME below is the default Windows install path.
"""

import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websockets

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
url, selector, out, profile = sys.argv[1:5]
width, height = int(sys.argv[5]), int(sys.argv[6])
PORT = 9333

proc = subprocess.Popen(
    [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--hide-scrollbars",
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={PORT}",
        "about:blank",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)


def debugger_url() -> str:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            return next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"]
        except OSError:
            time.sleep(0.2)
    raise SystemExit("Chrome did not start")


async def capture(ws_url: str) -> bytes:
    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        n = 0

        async def send(method, **params):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == n:
                    return msg.get("result", {})

        await send(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=2,
            mobile=False,
        )
        await send("Page.navigate", url=url)
        for _ in range(120):
            r = await send("Runtime.evaluate", expression=f"!!document.querySelector({selector!r})")
            if r.get("result", {}).get("value"):
                break
            await asyncio.sleep(0.5)
        else:
            raise SystemExit(f"selector {selector} never appeared")
        await asyncio.sleep(1.0)
        shot = await send("Page.captureScreenshot", format="png")
        return base64.b64decode(shot["data"])


try:
    png = asyncio.run(capture(debugger_url()))
    with open(out, "wb") as f:
        f.write(png)
    print("saved", out)
finally:
    proc.terminate()
