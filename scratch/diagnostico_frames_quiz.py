import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155377"
url_prova = f"https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5EazVOVEUuMTU1Mzc3?ou={ou}&iteratorRange=all"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()
    page.goto(url_prova, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    # Clicar em Tentativa 1
    page.evaluate(r"""() => {
        const sel = document.querySelector("select");
        if (sel) {
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].text.includes('Tentativa 1')) {
                    sel.selectedIndex = i;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
        }
        return false;
    }""")
    time.sleep(6)

    print(f"Total de frames: {len(page.frames)}")
    for i, fr in enumerate(page.frames):
        try:
            txt_sample = fr.evaluate("() => document.body.innerText.slice(0, 300)")
            print(f"\n--- Frame [{i}] (name: '{fr.name}', url: '{fr.url[:80]}') ---")
            print(txt_sample)
            
            # Buscar perguntas dentro deste frame
            perguntas = fr.evaluate(r"""() => {
                const els = Array.from(document.querySelectorAll('*')).filter(el => {
                    const t = (el.innerText || '').trim();
                    return t.startsWith('Pergunta') || t.startsWith('Questão') || (el.className && el.className.includes('quiz-question'));
                });
                return els.slice(0, 5).map(e => ({ tag: e.tagName, cls: e.className, txt: (e.innerText||'').slice(0, 100) }));
            }""")
            print(f"Perguntas achadas no frame [{i}]: {len(perguntas)}")
            for q in perguntas:
                print("   ->", q)
        except Exception as e:
            print(f"Frame [{i}] erro: {e}")

    browser.close()
