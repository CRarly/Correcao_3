import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
sys.path.insert(0, str(BASE_DIR))
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155377"
qi = "249951"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(auth_file) if auth_file.exists() else None,
        viewport={"width": 1400, "height": 900}
    )
    page = context.new_page()

    # Acessar a edição do quiz
    url_edit = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi={qi}&ou={ou}"
    print(f"Acessando: {url_edit}")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    # Localizar o elemento clicável do Question Pool (Grupo de Questões)
    print("Clicando no botão do question pool...")
    # No componente d2l-activity-question-pool, há um botão dentro do shadowRoot ou direto
    clicked = page.evaluate(r"""() => {
        const pool = document.querySelector('d2l-activity-question-pool');
        if (pool) {
            const btn = pool.shadowRoot ? pool.shadowRoot.querySelector('button, [role="button"]') : pool.querySelector('button');
            if (btn) {
                btn.click();
                return { ok: true, source: 'pool_shadow_btn' };
            }
            if (typeof pool.click === 'function') {
                pool.click();
                return { ok: true, source: 'pool_direct' };
            }
        }
        // Fallback para qualquer botão com texto 'Grupo de Questões'
        const buttons = Array.from(document.querySelectorAll('button, a'));
        const b = buttons.find(el => (el.innerText || '').includes('Grupo de Questões'));
        if (b) {
            b.click();
            return { ok: true, source: 'text_button' };
        }
        return { ok: false };
    }""")
    print("Resultado clique pool:", clicked)
    time.sleep(5)

    print(f"URL pós clique: {page.url} | Título: {page.title()}")

    # Inspecionar perguntas listadas dentro do pool ou na tela aberta
    info_tela = page.evaluate(r"""() => {
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

        // Extrair todos os links/textos de perguntas exibidas
        const perguntas = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
            const tag = el.tagName.toLowerCase();
            const cls = (el.className ? el.className.toString() : '').toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();

            // Procurar perguntas (código da pergunta ou tipo)
            if (txt.toLowerCase().includes('dissertat') || txt.toLowerCase().includes('discursiv') ||
                txt.toLowerCase().includes('escrita') || txt.toLowerCase().includes('resposta longa') ||
                aria.includes('pergunta') || cls.includes('question-title') || cls.includes('question-text')) {
                perguntas.push({
                    tag,
                    cls,
                    txt: txt.slice(0, 150),
                    aria,
                    href: el.href || el.getAttribute('href') || ''
                });
            }
        }

        // Buscar campos de 'pontos por pergunta'
        const pontos = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (txt.toLowerCase().includes('pontos por pergunta') || aria.includes('pontos por pergunta') || txt.toLowerCase().includes('pontos cada')) {
                pontos.push({
                    tag: el.tagName,
                    txt: txt.slice(0, 100),
                    val: el.value || (el.querySelector ? (el.querySelector('input') ? el.querySelector('input').value : '') : '')
                });
            }
        }

        return {
            perguntas: perguntas.slice(0, 20),
            pontos: pontos.slice(0, 10)
        };
    }""")

    print(f"\nPerguntas localizadas ({len(info_tela['perguntas'])}):")
    for p_item in info_tela['perguntas']:
        print("  *", p_item)

    print(f"\nCampos de pontos por pergunta ({len(info_tela['pontos'])}):")
    for pt in info_tela['pontos']:
        print("  *", pt)

    browser.close()
