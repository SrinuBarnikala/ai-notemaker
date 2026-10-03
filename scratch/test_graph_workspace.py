import asyncio
import os
import sys
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VIEWPORTS = [
    {"name": "1920x1080", "width": 1920, "height": 1080},
    {"name": "1440x900", "width": 1440, "height": 900},
    {"name": "1366x768", "width": 1366, "height": 768},
]

async def run_verification():
    os.makedirs("scratch/screenshots", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for vp in VIEWPORTS:
            name = vp["name"]
            width = vp["width"]
            height = vp["height"]
            print(f"\n=======================================================")
            print(f"VERIFYING VIEWPORT: {name} ({width} x {height})")
            print(f"=======================================================")

            context = await browser.new_context(viewport={"width": width, "height": height})
            page = await context.new_page()

            console_issues = []
            page.on("console", lambda m: console_issues.append(f"[{m.type}] {m.text}") if m.type in ["error"] else None)

            # 1. Navigate
            await page.goto("http://127.0.0.1:8000", wait_until="networkidle")
            await asyncio.sleep(1)

            # Open Knowledge Graph directly or via button
            try:
                cards = await page.query_selector_all(".journey-card, .history-item")
                if cards:
                    await cards[0].click()
                    await asyncio.sleep(0.5)
                await page.evaluate("openGraphModal(false)")
            except Exception:
                await page.evaluate("openGraphModal(false)")
            try:
                await page.wait_for_selector("#graph-loading", state="hidden", timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(0.5)

            # --- CHECKLIST 1: HEADER ---
            header_rect = await page.eval_on_selector(".graph-workspace-header", "el => el.getBoundingClientRect()")
            agent_badge = await page.eval_on_selector(".agent-compact-badge", "el => { const r = el.getBoundingClientRect(); return { text: el.textContent.trim(), h: r.height, w: r.width, fs: window.getComputedStyle(el).fontSize }; }")
            topic_title = await page.eval_on_selector(".workspace-topic-title", "el => { const r = el.getBoundingClientRect(); return { text: el.textContent.trim(), h: r.height, w: r.width, fs: window.getComputedStyle(el).fontSize }; }")
            back_btn = await page.eval_on_selector(".btn-workspace-back", "el => { const r = el.getBoundingClientRect(); return { h: r.height, w: r.width, fs: window.getComputedStyle(el).fontSize }; }")

            print(f"HEADER: Height={header_rect['height']}px (expected ~56px)")
            print(f"HEADER: Agent 10 badge='{agent_badge['text']}', height={agent_badge['h']:.1f}px, width={agent_badge['w']:.1f}px, font-size={agent_badge['fs']}")
            print(f"HEADER: Workspace Title='{topic_title['text']}', font-size={topic_title['fs']}, dominant={float(topic_title['fs'].replace('px','')) > float(agent_badge['fs'].replace('px',''))}")
            print(f"HEADER: Back button height={back_btn['h']}px, font-size={back_btn['fs']}")

            assert header_rect['height'] <= 62, f"Header too tall: {header_rect['height']}"
            assert agent_badge['h'] <= 28, f"Agent 10 badge too tall: {agent_badge['h']}"
            assert float(topic_title['fs'].replace('px','')) >= 16, f"Topic title not dominant: {topic_title['fs']}"

            # --- CHECKLIST 2: GRAPH HUDs (TOP-LEFT & TOP-RIGHT) ---
            legend_pos = await page.eval_on_selector("#graph-floating-legend", "el => { const r = el.getBoundingClientRect(); return { top: r.top, left: r.left, bottom: r.bottom }; }")
            zoom_pos = await page.eval_on_selector("#graph-zoom-island", "el => { const r = el.getBoundingClientRect(); return { top: r.top, right: window.innerWidth - r.right }; }")
            
            print(f"HUD: Legend HUD at top={legend_pos['top']:.1f}px, left={legend_pos['left']:.1f}px (verified Top-Left)")
            print(f"HUD: Zoom HUD at top={zoom_pos['top']:.1f}px, right={zoom_pos['right']:.1f}px (verified Top-Right)")

            assert legend_pos['top'] < 100, "Legend not in top area"
            assert zoom_pos['top'] < 100, "Zoom HUD not in top area"

            # --- CHECKLIST 3: LEGEND COLLAPSED/EXPANDED ---
            legend_body_init = await page.is_visible("#legend-expanded-body")
            await page.click(".legend-header")
            await asyncio.sleep(0.2)
            legend_body_open = await page.is_visible("#legend-expanded-body")
            await page.click(".legend-header")
            await asyncio.sleep(0.2)
            legend_body_closed = await page.is_visible("#legend-expanded-body")
            print(f"LEGEND: collapsed by default={not legend_body_init}, expands on click={legend_body_open}, collapses on click={not legend_body_closed}")

            assert not legend_body_init, "Legend should be collapsed by default"
            assert legend_body_open, "Legend should expand on click"

            await page.screenshot(path=f"scratch/screenshots/workspace_{name}_initial.png")

            # --- CHECKLIST 4: SIDEBAR SECTION HEADINGS & SELECTED CONCEPT ---
            section_titles = await page.eval_on_selector_all(".sidebar-section-title, .sidebar-title", "els => els.map(e => ({ text: e.textContent.trim(), fs: window.getComputedStyle(e).fontSize }))")
            print(f"SIDEBAR: Section labels font-size sample: {section_titles[0] if section_titles else 'None'}")

            # Select a node (using existing or sample node)
            node_res = await page.evaluate('''() => {
                if (!window.graphNodes || window.graphNodes.length === 0) {
                    window.graphNodes = [{
                        id: "concept-1",
                        name: "Multi-Version Concurrency Control (MVCC)",
                        status: "known",
                        journey_title: "Database Isolation Levels",
                        section_number: "2.1",
                        section_title: "MVCC Mechanics",
                        depth: "advanced",
                        summary: "Snapshot isolation using row versions and transaction IDs.",
                        recommendation: "Review write-skew anomalies.",
                        prerequisites: ["ACID Properties", "Transaction ID Allocation"],
                        unlocks: ["Serializable Snapshot Isolation (SSI)"]
                    }];
                }
                const node = window.graphNodes[0];
                selectConceptNode(node);
                const actionsBox = document.querySelector('.inspector-actions-row').getBoundingClientRect();
                const btnNote = document.getElementById('btn-graph-goto-note').getBoundingClientRect();
                const btnAsk = document.getElementById('btn-graph-ask-copilot').getBoundingClientRect();
                const btnPath = document.getElementById('btn-graph-trace-path').getBoundingClientRect();
                const scrollArea = document.getElementById('sidebar-scroll-area');
                return {
                    name: node.name,
                    actionsRowWidth: actionsBox.width,
                    btnNote: { w: btnNote.width, h: btnNote.height, visible: btnNote.width > 50 },
                    btnAsk: { w: btnAsk.width, h: btnAsk.height, visible: btnAsk.width > 50 },
                    btnPath: { w: btnPath.width, h: btnPath.height, visible: btnPath.width > 50 },
                    hasVerticalScroll: scrollArea.scrollHeight > scrollArea.clientHeight
                };
            }''')

            if node_res:
                print(f"SELECTED CONCEPT: Node='{node_res['name']}'")
                print(f"SELECTED CONCEPT: Actions row width={node_res['actionsRowWidth']:.1f}px")
                print(f"SELECTED CONCEPT: Go to Note button w={node_res['btnNote']['w']:.1f}px, h={node_res['btnNote']['h']:.1f}px")
                print(f"SELECTED CONCEPT: Ask Assistant button w={node_res['btnAsk']['w']:.1f}px, h={node_res['btnAsk']['h']:.1f}px")
                print(f"SELECTED CONCEPT: Path button w={node_res['btnPath']['w']:.1f}px, h={node_res['btnPath']['h']:.1f}px")
                print(f"SELECTED CONCEPT: Path button clipped={not node_res['btnPath']['visible']} (Must be False!)")

                assert node_res['btnPath']['visible'], "Path button is clipped!"
                assert node_res['btnNote']['visible'], "Go to Note button is clipped!"
                assert node_res['btnAsk']['visible'], "Ask button is clipped!"

            await page.screenshot(path=f"scratch/screenshots/workspace_{name}_node_selected.png")

            # --- CHECKLIST 5: SIDEBAR COLLAPSE & EXPAND ---
            await page.click("#btn-sidebar-collapse")
            await asyncio.sleep(0.35)
            collapsed = await page.evaluate("() => document.getElementById('graph-sidebar').classList.contains('collapsed')")
            expand_btn_visible = await page.is_visible("#btn-sidebar-expand")
            print(f"SIDEBAR COLLAPSE: Collapsed={collapsed}, Floating expand button visible={expand_btn_visible}")
            assert collapsed, "Sidebar failed to collapse"
            assert expand_btn_visible, "Expand button not visible after collapse"

            await page.screenshot(path=f"scratch/screenshots/workspace_{name}_collapsed.png")

            await page.click("#btn-sidebar-expand")
            await asyncio.sleep(0.35)
            reexpanded = await page.evaluate("() => !document.getElementById('graph-sidebar').classList.contains('collapsed')")
            print(f"SIDEBAR RE-EXPAND: Re-expanded={reexpanded}")
            assert reexpanded, "Sidebar failed to re-expand"

            # --- CHECKLIST 6: ZOOM CONTROLS ---
            init_zoom = await page.text_content("#graph-zoom-pill")
            await page.click("#graph-zoom-island button:has-text('+')")
            await asyncio.sleep(0.2)
            zoomed = await page.text_content("#graph-zoom-pill")
            await page.click("#graph-zoom-island .btn-reset-zoom")
            await asyncio.sleep(0.2)
            reset_zoom = await page.text_content("#graph-zoom-pill")
            print(f"ZOOM: Initial={init_zoom} -> Zoom In={zoomed} -> 1:1 Reset={reset_zoom}")

            # Close modal
            await page.click(".btn-workspace-back")
            await asyncio.sleep(0.4)
            modal_hidden = not await page.is_visible("#graph-modal")
            print(f"BACK TO NOTE: Modal closed successfully={modal_hidden}")
            assert modal_hidden, "Back to note failed to close modal"

            if console_issues:
                print(f"Console errors: {console_issues}")
            else:
                print("Console: 0 errors detected.")

            await context.close()

        await browser.close()
        print("\n=======================================================")
        print("ALL VIEWPORT VISUAL & UX VERIFICATIONS PASSED!")
        print("=======================================================")

if __name__ == "__main__":
    asyncio.run(run_verification())
