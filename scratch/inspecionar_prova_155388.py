import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
url_prova = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5UUTVOalUuMTU1Mzg4?ou=155388&iteratorRange=all&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.goto(url_prova, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    # Clicar em Tentativa 1 se necessário
    page.evaluate(r"""() => {
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
        for (let el of getAll(document.body)) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt === 'Tentativa 1' || txt.startsWith('Tentativa 1')) {
                const target = el.closest ? (el.closest('a') || el.closest('button') || el) : el;
                if (typeof target.click === 'function') {
                    target.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    time.sleep(5)

    # Inspecionar perguntas rolando para baixo
    for scroll_idx in range(6):
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
            const headers = [];
            for (let el of all) {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt.startsWith('Pergunta') || txt.startsWith('Questão')) {
                    if (txt.length < 50) headers.push(txt);
                }
            }
            return { headers };
        }""")
        print(f"Scroll step {scroll_idx}: perguntas visíveis: {res['headers']}")
        page.evaluate("window.scrollBy(0, 800);")
        time.sleep(1)

    page.screenshot(path=str(BASE_DIR / "scratch" / "prova_155388_screen.png"))
    print("Screenshot salva em scratch/prova_155388_screen.png")
    browser.close()
