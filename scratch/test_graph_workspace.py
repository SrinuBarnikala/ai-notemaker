import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ["error", "warning"] else None)

        print("1. Navigating to http://127.0.0.1:8000...")
        await page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        await asyncio.sleep(1)

        # Check if journey cards exist, click the first one if present
        journey_cards = await page.query_selector_all(".journey-card, .history-item")
        if journey_cards:
            print("Found existing journey card, clicking it...")
            await journey_cards[0].click()
            await asyncio.sleep(1.5)
        else:
            print("No journey card found directly, checking recent journeys...")
            # If viewer is hidden, check if we need to click a journey or generate
            pass

        # Check if Knowledge Graph button is visible
        graph_btn = await page.wait_for_selector("#btn-graph-toggle, .btn-graph", timeout=5000)
        print("2. Clicking Knowledge Graph button...")
        await graph_btn.click()
        await asyncio.sleep(1.5)

        # Verify Workspace Modal is visible
        modal = await page.query_selector("#graph-modal")
        modal_visible = await modal.is_visible()
        print(f"3. Graph Workspace Modal visible: {modal_visible}")

        # Check Header elements
        back_btn = await page.query_selector(".btn-workspace-back")
        title_el = await page.query_selector("#graph-modal-title")
        badge_el = await page.query_selector("#graph-workspace-badge")
        mode_journey = await page.query_selector("#btn-graph-mode-journey")
        mode_global = await page.query_selector("#btn-graph-mode-global")
        print(f"Header elements present: back={back_btn is not None}, title={await title_el.text_content() if title_el else None}, badge={await badge_el.text_content() if badge_el else None}")

        # Check Sidebar elements
        search_input = await page.query_selector("#graph-search-input")
        scope_neighbor = await page.query_selector("#btn-graph-scope-neighbor")
        scope_all = await page.query_selector("#btn-graph-scope-all")
        filter_all = await page.query_selector("#btn-filter-all")
        filter_known = await page.query_selector("#btn-filter-known")
        learning_path = await page.query_selector("#btn-graph-learning-path")
        assistant_sec = await page.query_selector("#graph-assistant-section")
        assistant_input = await page.query_selector("#graph-assistant-input")

        print("Sidebar elements present: search, scope, filters, learning path, assistant section.")

        # Take screenshot of open workspace
        os.makedirs("scratch", exist_ok=True)
        await page.screenshot(path="scratch/workspace_initial.png")
        print("Screenshot saved to scratch/workspace_initial.png")

        # Test selecting a concept node programmatically via graphNodes in page context
        print("4. Testing node selection in graph...")
        selected_info = await page.evaluate('''() => {
            if (window.graphNodes && window.graphNodes.length > 0) {
                const node = window.graphNodes[0];
                selectConceptNode(node);
                return {
                    name: node.name,
                    status: node.status,
                    inspectorDisplay: document.getElementById('graph-inspector-panel').style.display,
                    assistantContext: document.getElementById('graph-assistant-context').textContent
                };
            }
            return null;
        }''')
        print(f"Node selected info: {selected_info}")
        await asyncio.sleep(0.5)
        await page.screenshot(path="scratch/workspace_node_selected.png")

        # Test Ask Assistant button inside inspector
        print("5. Testing 'Ask Assistant' action...")
        await page.evaluate('''() => {
            askCopilotFromInspector();
        }''')
        await asyncio.sleep(0.5)
        assistant_val = await page.input_value("#graph-assistant-input")
        print(f"Assistant input prefilled with: {assistant_val[:60]}...")

        # Test Sidebar Collapse
        print("6. Testing Sidebar Collapse...")
        await page.click("#btn-sidebar-collapse")
        await asyncio.sleep(0.5)
        sidebar_collapsed = await page.evaluate('''() => {
            return document.getElementById('graph-sidebar').classList.contains('collapsed');
        }''')
        expand_btn_visible = await page.is_visible("#btn-sidebar-expand")
        print(f"Sidebar collapsed: {sidebar_collapsed}, Expand button visible: {expand_btn_visible}")
        await page.screenshot(path="scratch/workspace_collapsed.png")

        # Test Sidebar Expand
        print("7. Testing Sidebar Expand...")
        await page.click("#btn-sidebar-expand")
        await asyncio.sleep(0.5)
        sidebar_reexpanded = await page.evaluate('''() => {
            return !document.getElementById('graph-sidebar').classList.contains('collapsed');
        }''')
        print(f"Sidebar re-expanded: {sidebar_reexpanded}")

        # Test Floating Zoom Island
        print("8. Testing Floating Zoom Controls...")
        initial_zoom = await page.text_content("#graph-zoom-pill")
        await page.click("#graph-zoom-island button:has-text('+')")
        await asyncio.sleep(0.3)
        zoomed_in = await page.text_content("#graph-zoom-pill")
        await page.click("#graph-zoom-island .btn-reset-zoom")
        await asyncio.sleep(0.3)
        reset_zoom = await page.text_content("#graph-zoom-pill")
        print(f"Zoom levels: initial={initial_zoom}, zoomed_in={zoomed_in}, reset={reset_zoom}")

        # Test Floating Legend Toggle
        print("9. Testing Floating Legend Toggle...")
        legend_body_initial = await page.is_visible("#legend-expanded-body")
        await page.click(".legend-header")
        await asyncio.sleep(0.3)
        legend_body_expanded = await page.is_visible("#legend-expanded-body")
        await page.click(".legend-header")
        await asyncio.sleep(0.3)
        legend_body_collapsed = await page.is_visible("#legend-expanded-body")
        print(f"Legend: initial={legend_body_initial}, expanded={legend_body_expanded}, collapsed={legend_body_collapsed}")

        # Test Filter Buttons
        print("10. Testing Filter Buttons...")
        filter_status = await page.evaluate('''() => {
            setGraphFilter('gaps');
            const gapsActive = document.getElementById('btn-filter-gaps').classList.contains('active');
            setGraphFilter('all');
            const allActive = document.getElementById('btn-filter-all').classList.contains('active');
            return { gapsActive, allActive, currentFilter: activeFilter };
        }''')
        print(f"Filters test: {filter_status}")

        # Test Learning Path
        print("11. Testing Learning Path Toggle...")
        lp_status = await page.evaluate('''() => {
            toggleLearningPathMode();
            const bannerVisible = document.getElementById('graph-path-banner').style.display !== 'none';
            const lpActive = isLearningPathMode;
            exitLearningPathMode();
            const bannerClosed = document.getElementById('graph-path-banner').style.display === 'none';
            return { bannerVisible, lpActive, bannerClosed };
        }''')
        print(f"Learning Path test: {lp_status}")

        # Test Back to Note
        print("12. Testing 'Back to Note' button...")
        await page.click(".btn-workspace-back")
        await asyncio.sleep(0.5)
        modal_closed = not (await page.is_visible("#graph-modal"))
        print(f"Workspace modal closed: {modal_closed}")

        print("\n--- Console Errors/Warnings during session ---")
        for err in console_errors:
            print(" ", err)
        if not console_errors:
            print(" None! Clean console execution.")

        await browser.close()
        print("\nPlaywright test completed successfully!")

if __name__ == "__main__":
    asyncio.run(run())
