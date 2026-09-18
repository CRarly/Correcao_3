import time
from pathlib import Path
from playwright.sync_api import sync_playwright

auth_file = Path("auth_state_04083941.json")
ou = "155399"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(storage_state=str(auth_file), viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou={ou}", wait_until="domcontentloaded")
    time.sleep(3)

    href = page.evaluate(r"""() => {
        const rows = Array.from(document.querySelectorAll('tr'));
        for (let r of rows) {
            const txt = (r.innerText || '').toLowerCase();
            if ((txt.includes('prova presencial') || txt.includes('avaliação final')) && !txt.includes('substitutiva') && !txt.includes('recupera')) {
                const a = r.querySelector('a[href*="quiz_newedit_properties"]');
                if (a) return a.href;
            }
        }
        return null;
    }""")
    print("Href Prova:", href)

    if href:
        page.goto(href, wait_until="domcontentloaded")
        time.sleep(5)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        btns = page.evaluate(r"""() => {
            return Array.from(document.querySelectorAll('button')).map(b => (b.innerText || '').replace(/\s+/g, ' ').trim()).filter(t => t.length > 5 && (t.toLowerCase().includes('dissertat') || t.toLowerCase().includes('discursiv') || t.toLowerCase().includes('valendo') || t.toLowerCase().includes('grupo')));
        }""")
        print("Botões encontrados:", btns)

        # Clicar no botão da discursiva
        page.evaluate(r"""() => {
            const allB = Array.from(document.querySelectorAll('button'));
            for (let b of allB) {
                const t = (b.innerText || '').toLowerCase();
                if ((t.includes('dissertat') || t.includes('discursiv')) && t.includes('valendo')) {
                    b.scrollIntoView();
                    b.click();
                    return true;
                }
            }
            return false;
        }""")
        time.sleep(8)
        print(f"Total de frames pós-clique: {len(page.frames)}")
        for idx, fr in enumerate(page.frames):
            try:
                txt = fr.evaluate("() => document.body ? document.body.innerText.slice(0, 100).replace(/\\s+/g, ' ') : ''")
                print(f"  Frame {idx}: URL={fr.url[:40]} | Text={txt}")
            except Exception as e:
                print(f"  Frame {idx}: erro {e}")

    browser.close()
