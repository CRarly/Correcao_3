import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
url_quizzes = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None)
    page = context.new_page()

    page.goto(url_quizzes, wait_until="domcontentloaded", timeout=35000)
    time.sleep(4)

    quizzes = page.evaluate(r"""() => {
        const rows = Array.from(document.querySelectorAll('tr'));
        return rows.map(r => {
            const a = r.querySelector('a[href*="quiz"]');
            return {
                text: (r.innerText || '').replace(/\s+/g, ' ').trim(),
                link: a ? a.innerText.trim() : null,
                href: a ? a.href : null
            };
        }).filter(r => r.link);
    }""")

    print(f"Total quizzes encontrados em {ou}: {len(quizzes)}")
    for q in quizzes:
        print(f" - [{q['link']}] -> {q['href']}")

    browser.close()
