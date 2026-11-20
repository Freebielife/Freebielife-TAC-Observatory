"""Offline Chromium acceptance test for TAC flags, services, staking and layouts."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "build/tac-qa"
STAKING = "https://staking.tac.build/"
EXPECTED = {"ton", "ston", "dedust", "telegram", "x", "usdt"}
FORBIDDEN = {"ludoman", "kito", "gram", "usda", "rton"}


def main():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for width in (360, 390, 768, 1280):
            page = browser.new_page(viewport={"width": width, "height": 850}, device_scale_factor=1)
            faults = []
            page.on("pageerror", lambda e: faults.append(str(e)))
            page.route("https://raw.githubusercontent.com/**", lambda route: route.abort())
            page.route("https://api.github.com/**", lambda route: route.abort())
            page.goto((ROOT / "index.html").as_uri())
            page.wait_for_selector("#market #plot svg", timeout=15000)
            assert not faults, faults
            assert set(page.evaluate("Object.keys(window.OBSERVATORY_BRAND_ATLAS?.positions || {})")) >= EXPECTED
            assert not (set(page.evaluate("Object.keys(window.OBSERVATORY_BRAND_ATLAS?.positions || {})")) & FORBIDDEN)
            for query in (".heroChain [data-brand=ton] .brandTile",
                          ".marketChain [data-brand=ston] .brandTile",
                          ".marketChain [data-brand=ton] .brandTile",
                          ".resourceList a[href='https://t.me/TACbuild'] .brandTile",
                          "#pools .knownPools .poolCard .dexMarks .brandTile",
                          "#pools .knownPools .poolCard h3 .brandTile",
                          "#links a[href='https://tac.build/'] .brand-project",
                          "#links a[href='https://staking.tac.build/'] .brand-project"):
                assert page.locator(query).count() >= 1, (width, query)
            assert "image/webp" in page.locator("#links a[href='https://tac.build/'] .brand-project").evaluate("el => getComputedStyle(el).backgroundImage")
            assert page.locator("a[href='" + STAKING + "']").count() == 2
            assert "GeckoTerminal ·" not in page.locator("#pools").inner_text()
            assert "Проверено по GeckoTerminal" not in page.locator("#pools").inner_text()
            assert "LUDOMAN" not in page.locator("body").inner_text()
            assert page.locator(".resourceList a[href^='https://']").count() >= 5
            for action in page.locator("#pools .knownPools .poolActions a").all():
                assert action.get_attribute("href", timeout=1000).startswith("https://")
            widths = page.evaluate("() => [document.documentElement.scrollWidth, document.body.scrollWidth, innerWidth]")
            assert max(widths[:2]) <= widths[-1] + 2, (width, widths)
            page.locator("#en").click()
            assert page.evaluate("document.documentElement.lang") == "en"
            assert "Официальная страница стейкинга" not in page.locator("#supply").inner_text()
            page.locator("#ru").click()
            assert page.evaluate("document.documentElement.lang") == "ru"
            assert not faults, (width, faults)
            page.screenshot(path=str(SCREENSHOTS / f"TAC-{width}.png"), full_page=True)
            page.close()
        browser.close()
    print("PASS TAC vetted flags, links, staking CTA and overflow at 360/390/768/1280")


if __name__ == "__main__":
    main()
