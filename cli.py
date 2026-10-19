import sys
import os
import getpass
from pathlib import Path

# Suporte UTF-8 no Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import BASE_DIR
from core.discovery import descobrir_todas_abas_e_cursos
from core.orquestrador import orquestrador
from core.inspector_disciplina import inspector_disciplina
from core.browser_session import BrowserSession

def banner():
    print("=" * 65)
    print("   BRIGHTSPACE GRADER 3.0 | Motor Pedagógico Especialista")
    print("=" * 65)

def menu_principal():
    banner()
    username = input("Matrícula/Usuário (ex: 04083941): ").strip() or "04083941"
    password = getpass.getpass("Senha [Enter para usar mesma do usuário]: ").strip() or username

    print("\nMapeando turmas disponíveis no AVA...")
    dados = descobrir_todas_abas_e_cursos(username, password, headless=True)
    abas = dados.get("abas", ["Fixado"])
    print("\nAbas disponíveis:")
    for idx, a in enumerate(abas, 1):
        print(f"  [{idx}] {a}")

    escolha_aba = input(f"\nEscolha a aba [1-{len(abas)}] (Padrão 1): ").strip()
    idx_aba = int(escolha_aba) - 1 if escolha_aba.isdigit() and 1 <= int(escolha_aba) <= len(abas) else 0
    aba_selecionada = abas[idx_aba]

    turmas = dados.get("disciplinas_por_aba", {}).get(aba_selecionada, [])
    if not turmas:
        print("Nenhuma turma localizada nesta aba.")
        return

    print(f"\nTurmas em '{aba_selecionada}':")
    for idx, t in enumerate(turmas, 1):
        print(f"  [{idx}] [{t['ou']}] {t['name']}")

    sel_turmas_str = input("\nSelecione as turmas (ex: 1, 2 ou 'todas'): ").strip()
    if sel_turmas_str.lower() == 'todas':
        turmas_escolhidas = turmas
    else:
        indices = [int(x.strip()) - 1 for x in sel_turmas_str.split(",") if x.strip().isdigit()]
        turmas_escolhidas = [turmas[i] for i in indices if 0 <= i < len(turmas)]

    if not turmas_escolhidas:
        print("Nenhuma turma válida selecionada.")
        return

    print("\nSelecione as Atividades para Avaliação:")
    print("  [1] Todas (Fórum + Atividade Aberta + Provas)")
    print("  [2] Apenas Fórum de Discussão")
    print("  [3] Apenas Atividade Aberta")
    print("  [4] Apenas Prova Presencial (Questão Discursiva)")
    print("  [5] Apenas Prova Substitutiva (Questão Discursiva)")
    print("  [6] Ambas as Provas (Presencial + Substitutiva)")
    op_ativ = input("Opção [1-6] (Padrão 1): ").strip() or "1"

    mapa_ativ = {
        "1": ["forum", "atividade_aberta", "prova_presencial", "prova_substitutiva"],
        "2": ["forum"],
        "3": ["atividade_aberta"],
        "4": ["prova_presencial"],
        "5": ["prova_substitutiva"],
        "6": ["prova_presencial", "prova_substitutiva"]
    }
    atividades_escolhidas = mapa_ativ.get(op_ativ, ["forum", "atividade_aberta", "prova_presencial", "prova_substitutiva"])

    print("\nSelecione o Modo Operacional:")
    print("  [1] Execução Normal (Novos envios + Auditoria comum)")
    print("  [2] Recorrigir + Auditoria Geral (Avaliar e auditar 100% da turma)")
    print("  [3] Auditoria (Verificar já corrigidos, {FirstName}, notas)")
    print("  [4] Auditoria Geral (Auditar 100% dos estudantes)")
    op_modo = input("Opção [1-4] (Padrão 1): ").strip() or "1"

    mapa_modo = {
        "1": "tradicional",
        "2": "recorrigir",
        "3": "auditoria",
        "4": "auditoria_geral"
    }
    modo_escolhido = mapa_modo.get(op_modo, "tradicional")

    op_visivel = input("\nExecutar com navegador visível? (s/N): ").strip().lower()
    headless = op_visivel != "s"

    print("\n" + "=" * 65)
    print("INICIANDO EXECUÇÃO")
    print("=" * 65)

    orquestrador.executar(
        username=username,
        password=password,
        disciplinas=turmas_escolhidas,
        atividades_selecionadas=atividades_escolhidas,
        modo=modo_escolhido,
        headless=headless
    )

if __name__ == "__main__":
    menu_principal()
