import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_prova_eval = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5UUTVPRE0uMTU1Mzk5?ou=155399&iteratorRange=new&cfi=sort%7EeyJTb3J0cyI6W3siU29ydCI6eyJJZCI6IjE3YTFhOWE0LTcyOWYtNGJhMy05ZjdmLWRmZTJmOWQzZWVkMiJ9LCJEaXJlY3Rpb24iOjB9XX0&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    page.goto(url_prova_eval, wait_until="domcontentloaded", timeout=35000)
    time.sleep(10)

    # Inspecionar todos os elementos com 'feedback' em qualquer atributo ou tag
    res = page.evaluate(r"""() => {
        function getAll(root) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while(w.nextNode()) {
                const el = w.currentNode;
                res.push(el);
                if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
            }
            return res;
        }
        const all = getAll(document.body);
        const achados = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            const id = (el.id || '').toLowerCase();
            const cls = (el.className || '').toString().toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (tag.includes('feedback') || id.includes('feedback') || cls.includes('feedback') || aria.includes('feedback')) {
                achados.push({
                    tag: el.tagName,
                    id: el.id,
                    className: (el.className || '').toString(),
                    aria: el.getAttribute('aria-label'),
                    outer: el.outerHTML.slice(0, 150)
                });
            }
        }
        return achados;
    }""")

    print(f"Total elementos com 'feedback': {len(res)}")
    for a in res:
        print(" -", a)

    browser.close()
