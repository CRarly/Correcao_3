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

    # Inspecionar hosts e irmãos saindo do shadow root
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
        let inpScore = null;
        for (let el of all) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (aria.includes('pontuação da pergunta de 2') || aria.includes('pontuacao da pergunta de 2')) {
                inpScore = el;
                break;
            }
        }
        if (!inpScore) return { found: false };

        // Subir até o host
        let host = inpScore;
        while (host && !host.tagName.toLowerCase().includes('d2l-')) {
            host = host.parentElement || (host.getRootNode ? host.getRootNode().host : null);
        }

        // Subir mais um pouco no DOM real
        let p = host;
        let chain = [];
        for (let i = 0; i < 6; i++) {
            if (!p) break;
            chain.push({ tag: p.tagName, className: p.className, id: p.id });
            p = p.parentElement || (p.getRootNode ? p.getRootNode().host : null);
        }

        // Listar todos os filhos e netos desse ancestral comum
        const ancestor = p || host;
        const inners = getAll(ancestor);
        const elements = inners.map(e => ({
            tag: e.tagName,
            id: e.id,
            className: e.className,
            aria: e.getAttribute('aria-label'),
            val: e.value,
            txt: (e.innerText || e.textContent || '').slice(0, 60),
            outer: e.outerHTML.slice(0, 120)
        })).filter(e => ['input', 'textarea', 'button', 'd2l-input-textarea', 'd2l-htmleditor', 'd2l-input-number'].includes(e.tag.toLowerCase()) || (e.aria && e.aria.toLowerCase().includes('feedback')));

        return { chain, elements };
    }""")

    print("Cadeia ancestral:", res.get('chain'))
    print(f"\nElementos interativos no container da pergunta ({len(res.get('elements', []))}):")
    for el in res.get('elements', []):
        print(" -", el)

    browser.close()
