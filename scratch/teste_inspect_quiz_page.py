import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_edit = "https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi=254965&ou=155388"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1200})
    page = context.new_page()

    print("Acessando pagina de edicao da prova...")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    # Tirar screenshot inicial
    page.screenshot(path=str(BASE_DIR / "quiz_edit_page_top.png"))
    
    # Rolar para baixo
    page.evaluate("window.scrollTo(0, 1000)")
    time.sleep(2)
    page.screenshot(path=str(BASE_DIR / "quiz_edit_page_mid.png"))

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    page.screenshot(path=str(BASE_DIR / "quiz_edit_page_bottom.png"))

    # Inspecionar todos os textos, botões e links na seção de perguntas
    info = page.evaluate(r"""() => {
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
        
        const items = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('dissertativa') || txt.includes('dissertat') || txt.includes('QME') || txt.includes('pontos por pergunta') || txt.includes('Pontos por pergunta') || txt.includes('Grupo de Questões') || txt.includes('Conjunto de perguntas')) {
                // Registrar elementos relevantes com tag e atributos
                if (['button', 'a', 'd2l-button', 'd2l-link', 'div', 'span', 'tr', 'li'].includes(el.tagName.toLowerCase())) {
                    if (txt.length < 150) {
                        items.push({
                            tag: el.tagName,
                            id: el.id,
                            className: el.className,
                            txt: txt.replace(/\s+/g, ' '),
                            outer: el.outerHTML.slice(0, 200)
                        });
                    }
                }
            }
        }
        return items;
    }""")

    print(f"\nTotal elementos encontrados: {len(info)}")
    for it in info:
        print(f"[{it['tag']}] id={it['id']} text='{it['txt']}'")

    browser.close()
