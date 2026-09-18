import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
url_edit = "https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi=254965&ou=155388"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    print(f"Acessando: {url_edit}")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    # Localizar e clicar no botão do pool (Grupo de Questões)
    pool_click = page.evaluate("""() => {
        function findElements(root) {
            let list = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                list.push(el);
                if (el.shadowRoot) list = list.concat(findElements(el.shadowRoot));
            }
            return list;
        }
        const all = findElements(document.body);
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if ((txt.includes('Grupo de Questões') || txt.includes('Questão dissertativa') || txt.includes('editar conjunto de perguntas')) && (el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'SPAN')) {
                const target = el.closest('button') || el.closest('a') || el;
                if (typeof target.click === 'function') {
                    target.scrollIntoView();
                    target.click();
                    return { clicked: true, tag: target.tagName, txt: txt.slice(0, 50) };
                }
            }
        }
        return { clicked: false };
    }""")
    print("Resultado clique pool:", pool_click)
    time.sleep(6)

    # Verificar frames
    print(f"Total de frames pós-clique pool: {len(page.frames)}")
    target_frame = None
    for idx, fr in enumerate(page.frames):
        print(f"  Frame [{idx}]: name='{fr.name}', url='{fr.url[:80]}'")
        if "quiz-question-authoring" in fr.url or "authoring" in fr.url:
            target_frame = fr

    ctx = target_frame if target_frame else page
    print(f"\nInspecionando contexto de perguntas ({'frame' if target_frame else 'page'})...")

    # Inspecionar textos e links no contexto
    links_e_textos = ctx.evaluate(r"""() => {
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
        const links = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (['script', 'style', 'noscript'].includes(tag)) continue;
            const txt = (el.innerText || '').trim();
            if (['a', 'button'].includes(tag) && txt.length > 2 && txt.length < 60) {
                links.push({ tag, txt, href: el.href || '' });
            }
        }
        return { totalAll: all.length, sampleLinks: links.slice(0, 25) };
    }""")

    print(f"Total elementos: {links_e_textos['totalAll']}")
    print("Links e botões encontrados:")
    for l in links_e_textos['sampleLinks']:
        print("  *", l)

    browser.close()
