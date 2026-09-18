import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.motor_discursivas import motor_discursivas

AUTH_FILE = BASE_DIR / "auth_state_04083941.json"
OU = "155399"
DISCIPLINA = "SISTEMAS DE INFORMAÇÕES NAS ORGANIZAÇÕES - GEE04I30015"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(AUTH_FILE) if AUTH_FILE.exists() else None,
        viewport={"width": 1400, "height": 900}
    )
    page = context.new_page()

    print(f"Testando extração universal da discursiva na turma [{OU}] {DISCIPLINA}...")
    info = motor_discursivas.inspecionar_questao_discursiva(page, OU, DISCIPLINA)
    print("\nDados da Questão Discursiva Extraídos:")
    print(f"  * Código: {info.get('codigo_questao')}")
    print(f"  * Valor Máximo: {info.get('valor_maximo')} pts")
    print(f"  * Método de Extração: {info.get('metodo_extracao')}")
    print(f"  * Tamanho do Enunciado: {len(info.get('enunciado', ''))} caracteres")
    print(f"  * Trecho inicial do Enunciado: {info.get('enunciado', '')[:140]}...")

    if info.get("enunciado"):
        criterios = motor_discursivas.gerar_criterios_avaliacao(info["enunciado"], info.get("valor_maximo", 2.0))
        exemplo = motor_discursivas.gerar_exemplo_resposta(info["enunciado"], criterios)
        print(f"\nCritérios Gerados ({len(criterios)}):")
        for c in criterios:
            print(f"  - {c['nome']}: {c['peso']} pts")
        print(f"\nExemplo de Resposta Gerado:\n{exemplo[:250]}...")

    browser.close()
