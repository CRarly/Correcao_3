import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_ativ = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHlNREF3WHpFMk9UZzVPQS4xNTUzODg?ou=155388&iteratorRange=all&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(url_ativ, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

    # Inspecionar frames
    print(f"Total de frames: {len(page.frames)}")
    for idx, fr in enumerate(page.frames):
        try:
            info = fr.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a')).map(a => ({
                    txt: (a.innerText || '').trim(),
                    href: a.href,
                    aria: a.getAttribute('aria-label') || ''
                })).filter(l => l.href && (l.href.includes('download') || l.href.includes('file') || l.href.includes('attachment') || l.txt.length > 2));
                return { url: window.location.href, name: window.name, linksCount: links.length, sampleLinks: links.slice(0, 10) };
            }""")
            print(f"Frame [{idx}] ({fr.name}): URL={info['url'][:60]}, Links relevantes={info['linksCount']}")
            for sl in info['sampleLinks']:
                print("   ->", sl)
        except Exception as e:
            print(f"Frame [{idx}] erro: {e}")

    # Inspecionar também links na página principal
    page_links = page.evaluate(r"""() => {
        function getAllElements(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) elements = elements.concat(getAllElements(el.shadowRoot));
            }
            return elements;
        }
        const all = getAllElements(document.body);
        const links = [];
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'a' || el.tagName.toLowerCase().includes('button')) {
                const href = el.href || el.getAttribute('href') || '';
                const txt = (el.innerText || el.textContent || '').trim();
                const aria = el.getAttribute('aria-label') || '';
                if (href.includes('download') || aria.toLowerCase().includes('baixar') || txt.toLowerCase().includes('baixar') || txt.toLowerCase().includes('download') || txt.toLowerCase().includes('anexo') || href.includes('attachment')) {
                    links.push({ tag: el.tagName, txt: txt.slice(0, 60), aria: aria.slice(0, 60), href: href.slice(0, 80) });
                }
            }
        }
        return links;
    }""")
    print("\nLinks de download na página principal e Shadow DOMs:")
    for pl in page_links:
        print("  *", pl)

    browser.close()
