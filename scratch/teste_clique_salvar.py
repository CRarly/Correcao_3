import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
url_ativ = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHlNREF3WHpFMk9UZzVPQS4xNTUzODg?ou=155388&iteratorRange=all&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    network_logs = []
    def log_request(request):
        if any(k in request.url.lower() for k in ["save", "evaluation", "grade", "feedback", "draft", "rpc"]):
            network_logs.append(f"REQ: {request.method} {request.url}")

    def log_response(response):
        if any(k in response.url.lower() for k in ["save", "evaluation", "grade", "feedback", "draft", "rpc"]):
            network_logs.append(f"RES: {response.status} {response.url}")

    page.on("request", log_request)
    page.on("response", log_response)

    print(f"Navegando para: {url_ativ}")
    page.goto(url_ativ, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

    # Inspecionar o estado atual da nota e do feedback
    estado_inicial = page.evaluate(r"""() => {
        const inpNum = document.querySelector('d2l-input-number');
        const inpVal = inpNum ? inpNum.value : null;
        
        let fbVal = '';
        const ed = document.querySelector('d2l-htmleditor');
        if (ed) fbVal = ed.html || ed.innerText || '';

        return { inpVal, fbVal: fbVal.slice(0, 100) };
    }""")
    print("Estado inicial:", estado_inicial)

    # Testar como d2l-button responde a clique
    print("\nTestando clique no botão Salvar Rascunho...")
    network_logs.clear()

    # Vamos ver como o d2l-button#consistent-evaluation-footer-save-draft é clicado
    click_res = page.evaluate(r"""() => {
        const btn = document.querySelector('d2l-button#consistent-evaluation-footer-save-draft');
        if (!btn) return { found: false };
        
        // Verificar se tem shadowRoot e botão interno
        const innerBtn = btn.shadowRoot ? btn.shadowRoot.querySelector('button') : null;
        
        // Simular clique no innerBtn ou no btn
        if (innerBtn) {
            innerBtn.click();
            return { found: true, innerClicked: true, disabled: innerBtn.disabled };
        } else {
            btn.click();
            return { found: true, btnClicked: true, disabled: btn.disabled };
        }
    }""")
    print("Resultado clique JS:", click_res)
    time.sleep(3)

    print(f"\nRequisições disparadas pelo clique ({len(network_logs)}):")
    for r in network_logs[:10]:
        print(" ", r)

    browser.close()
