import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
url_quizzes = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    print(f"Acessando Questionários: {url_quizzes}")
    page.goto(url_quizzes, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    # 1. Localizar questionários disponíveis
    quizzes = page.evaluate(r"""() => {
        const rows = Array.from(document.querySelectorAll('tr'));
        const list = [];
        for (let r of rows) {
            const txt = (r.innerText || '').trim();
            const link = r.querySelector('a');
            if (txt && link && (txt.includes('Prova') || txt.includes('Avaliação'))) {
                list.push({ text: txt.replace(/\s+/g, ' ').slice(0, 80), href: link.href });
            }
        }
        return list;
    }""")
    print("Questionários encontrados:")
    for q in quizzes:
        print("  *", q)

    # 2. Localizar a Prova Presencial (ou substitutiva/final)
    quiz_alvo = next((q for q in quizzes if 'prova presencial' in q['text'].lower()), None)
    if not quiz_alvo:
        quiz_alvo = next((q for q in quizzes if 'prova' in q['text'].lower()), None)

    if quiz_alvo:
        print(f"\nQuestionário alvo: {quiz_alvo['text']}")
        # Abrir edição do questionário
        print(f"Acessando edição do questionário: {quiz_alvo['href']}")
        page.goto(quiz_alvo['href'], wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)
        print(f"URL de edição: {page.url} | Título: {page.title()}")

        # Rolar até a seção de Perguntas
        page.evaluate("window.scrollTo(0, 1000);")
        time.sleep(2)

        # Inspecionar perguntas/pools e iframes
        print(f"Total de frames na edição: {len(page.frames)}")
        for idx, fr in enumerate(page.frames):
            print(f"  Frame [{idx}]: name='{fr.name}', url='{fr.url[:70]}'")

        # Localizar Questão Dissertativa ou pool de questões
        info_perguntas = page.evaluate(r"""() => {
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
            const items = [];
            for (let el of all) {
                const txt = (el.innerText || el.textContent || '').trim();
                const tag = el.tagName.toLowerCase();
                if (['script', 'style', 'noscript'].includes(tag)) continue;
                if (txt.toLowerCase().includes('dissertat') || txt.toLowerCase().includes('discursiv') || 
                    txt.includes('Pontos por pergunta') || txt.includes('Grupo de questões') || 
                    txt.includes('Conjunto de perguntas') || txt.includes('Pool')) {
                    if (txt.length < 150 && !items.some(i => i.txt === txt)) {
                        items.push({ tag, txt, id: el.id, cls: el.className });
                    }
                }
            }
            return items;
        }""")
        print("\nElementos de perguntas encontrados na página principal:")
        for it in info_perguntas:
            print("  -", it)

    browser.close()
