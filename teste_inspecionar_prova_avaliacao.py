import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
sys.path.insert(0, str(BASE_DIR))
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155377"
url_prova = f"https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5EazVOVEUuMTU1Mzc3?ou={ou}&iteratorRange=all"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.goto(url_prova, wait_until="domcontentloaded", timeout=30000)
    time.sleep(8)

    print("Clicando no link da 'Tentativa 1'...")
    res_click = page.evaluate(r"""() => {
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
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt === 'Tentativa 1' || txt.includes('Tentativa 1')) {
                const target = el.closest ? (el.closest('a') || el.closest('button') || el) : el;
                if (typeof target.click === 'function') {
                    target.click();
                    return { clicked: true, tag: target.tagName, txt };
                }
            }
        }
        return { clicked: false };
    }""")
    print("Resultado clique tentativa:", res_click)
    time.sleep(6)

    print(f"URL pós-clique tentativa: {page.url} | Título: {page.title()}")
    print(f"Total de frames pós-clique: {len(page.frames)}")

    # Inspecionar perguntas carregadas
    shadow_after = page.evaluate(r"""() => {
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
        const questions = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
            if (txt.includes('Pergunta') || txt.includes('Questão') || txt.includes('Pontos')) {
                if (txt.length > 15 && txt.length < 250) {
                    questions.push({ tag: el.tagName, txt: txt.slice(0, 120), cls: el.className });
                }
            }
        }
        return { total: all.length, questions: questions.slice(0, 20) };
    }""")

    print(f"Total elementos: {shadow_after['total']}")
    print(f"Perguntas localizadas pós-clique ({len(shadow_after['questions'])}):")
    for q in shadow_after['questions']:
        print("  -", q)

    browser.close()
