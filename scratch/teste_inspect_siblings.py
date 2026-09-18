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

    # Inspecionar irmãos e descendentes a partir de inpScore
    siblings = page.evaluate(r"""() => {
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
        let inpScore = null;
        for (let el of all) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (aria.includes('pontuação da pergunta de 2') || aria.includes('pontuacao da pergunta de 2')) {
                inpScore = el;
                break;
            }
        }
        if (!inpScore) return [];

        // Subir até achar um container que tenha mais irmãos
        let p = inpScore;
        let achados = [];
        for (let step = 0; step < 8; step++) {
            if (!p) break;
            const parent = p.parentElement;
            if (parent) {
                const children = Array.from(parent.children);
                for (let ch of children) {
                    if (ch !== p) {
                        const inners = getAll(ch);
                        for (let inner of inners) {
                            achados.push({
                                tag: inner.tagName,
                                id: inner.id,
                                className: inner.className,
                                outer: inner.outerHTML.slice(0, 200)
                            });
                        }
                    }
                }
            }
            p = parent;
        }
        return achados;
    }""")

    print(f"Total irmãos/descendentes encontrados: {len(siblings)}")
    for s in siblings[:25]:
        print(" -", s)

    browser.close()
