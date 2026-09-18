import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
sys.path.insert(0, str(BASE_DIR))
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155377"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(f"https://ava.catolica.edu.br/d2l/le/{ou}/quickeval/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # Clicar na aba Atividades
    page.evaluate("""() => {
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
            if ((el.innerText || '').trim() === 'Atividades') {
                const target = el.shadowRoot ? el.shadowRoot.querySelector('button') : el;
                if (target && typeof target.click === 'function') {
                    target.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    time.sleep(4)

    # Extrair todos os links evaluation/activity
    itens = page.evaluate("""() => {
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
            if (el.tagName.toLowerCase() === 'a' && el.href && el.href.includes('evaluation/activity')) {
                // Procurar texto da atividade no elemento pai ou irmãos
                let parent = el.parentElement;
                let textContext = '';
                for (let k = 0; k < 4 && parent; k++) {
                    const t = (parent.innerText || '').trim();
                    if (t.length > textContext.length) textContext = t;
                    parent = parent.parentElement;
                }
                links.push({
                    text: (el.innerText || el.textContent || '').trim(),
                    href: el.href,
                    context: textContext.replace(/\\s+/g, ' ').slice(0, 120)
                });
            }
        }
        return links;
    }""")

    print(f"Links evaluation/activity encontrados ({len(itens)}):")
    for it in itens:
        print(f"  - Contexto: {it['context']}\n    Link: {it['href']}\n")

    # Acessar Fórum em Avaliar Tudo
    forum_it = next((it for it in itens if 'postagens' in it['text'].lower() or 'fórum' in it['context'].lower()), None)
    if forum_it:
        url_all = forum_it['href'].replace('iteratorRange=new', 'iteratorRange=all')
        print(f"Acessando URL Avaliar Tudo do Fórum:\n{url_all}")
        page.goto(url_all, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        
        from core.navigation_iterator import extrair_posicao_mostrador_iterator, extrair_nome_estudante_atual
        pos = extrair_posicao_mostrador_iterator(page)
        nome = extrair_nome_estudante_atual(page)
        print(f"\nResultado no Consistent Evaluation:")
        print(f"  - Posição Mostrador: {pos}")
        print(f"  - Estudante: {nome}")

    browser.close()

