"""
Script to capture high-resolution screenshots of the living note reader UI
using the local Windows Edge browser via Playwright.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def capture_ui(url: str, output_path: str, toolbar_only_path: str = None):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page = context.new_page()
        print(f"Navigating to {url}...")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2500)
        
        # Ensure note panel is visible
        page.wait_for_selector("#reader-toolbar", state="visible", timeout=10000)
        
        # Capture full viewport
        page.screenshot(path=output_path)
        print(f"Saved full page screenshot to: {output_path}")
        
        # Capture toolbar element only if requested
        if toolbar_only_path:
            toolbar = page.locator("#reader-toolbar")
            toolbar.screenshot(path=toolbar_only_path)
            print(f"Saved toolbar screenshot to: {toolbar_only_path}")
            
        browser.close()

if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/?journey_id=692297a5-ad6b-4914-9c6e-d16a402be65f"
    out_dir = Path("C:/Users/srinu barnikala/.gemini/antigravity-ide/brain/b56e19e0-e00e-403f-bb2c-c3c78f330d67")
    out_dir.mkdir(parents=True, exist_ok=True)
    full_png = str(out_dir / "note_viewer_page.png")
    toolbar_png = str(out_dir / "toolbar_render.png")
    capture_ui(target_url, full_png, toolbar_png)
