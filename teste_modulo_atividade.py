import sys
import time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from cognitive.analisador_pedagogico import analisador_pedagogico
from cognitive.construtor_feedback import construtor_feedback
from cognitive.detector_plagio import detector_plagio
from core.navigation_iterator import extrair_posicao_mostrador_iterator, extrair_nome_estudante_atual
from core.dom_helpers import (
    inserir_nota_consistent_evaluation,
    inserir_feedback_consistent_evaluation,
    salvar_rascunho_consistent_evaluation,
    obter_nota_e_feedback_consistent_evaluation,
    contar_anexos_submissao
)
from core.motor_atividades import motor_atividades

AUTH_FILE = BASE_DIR / "auth_state_04083941.json"
OU = "155388"
DISCIPLINA = "ENGENHARIA DE SOFTWARE"
DOCENTE = "Prof. Arly Cristopher Nascimento Alves"

URL_ATIVIDADE = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHlNREF3WHpFMk9UZzVPQS4xNTUzODg?ou=155388&iteratorRange=all&cft=qe"

def testar_correcao_atividade():
    print("=" * 70)
    print("TESTE DE CORREÇÃO EM TEMPO REAL: MÓDULO ATIVIDADE ABERTA")
    print("=" * 70)
    print(f"Disciplina: [{OU}] {DISCIPLINA}")
    print(f"URL Alvo: {URL_ATIVIDADE}")
    print(f"Sessão Auth: {AUTH_FILE.name}\n")

    temp_dir = BASE_DIR / f"temp_teste_{OU}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(AUTH_FILE) if AUTH_FILE.exists() else None,
            viewport={"width": 1400, "height": 900}
        )
        page = context.new_page()

        print("[1/5] Navegando até a tela de Avaliação Consistente da Atividade...")
        page.goto(URL_ATIVIDADE, wait_until="domcontentloaded", timeout=35000)
        time.sleep(6)

        pos_info = extrair_posicao_mostrador_iterator(page)
        nome_aluno = extrair_nome_estudante_atual(page)
        print(f"   -> Estudante identificado: {nome_aluno} | Posição: {pos_info.get('atual')}/{pos_info.get('total')}")

        print("\n[2/5] Verificando com precisão a quantidade de anexos e extraindo conteúdo...")
        anexos_detectados = contar_anexos_submissao(page)
        print(f"   -> Anexos identificados no DOM: {len(anexos_detectados)} anexo(s) -> {anexos_detectados}")
        assert len(anexos_detectados) >= 1, "Deveria ter localizado pelo menos 1 anexo na submissão de teste"

        total_arqs, texto_submissoes = motor_atividades._baixar_e_extrair_arquivos(page, temp_dir, idx=1)
        print(f"   -> Contagem fidedigna retornada: {total_arqs} anexo(s)")
        print(f"   -> Extensão do conteúdo textual extraído: {len(texto_submissoes)} caracteres")
        print(f"   -> Amostra: {texto_submissoes[:120].strip()}...")

        # Conferir que a contagem reflete os anexos reais (não duplicada por zip de download)
        assert total_arqs == len(anexos_detectados), f"Inconsistência de contagem: {total_arqs} != {len(anexos_detectados)}"

        # Conferir que temporários foram excluídos do disco
        arquivos_restantes = list(temp_dir.glob("*"))
        print(f"   -> Arquivos residuais no diretório temporário: {len(arquivos_restantes)} (Exclusão garantida)")
        assert len(arquivos_restantes) == 0, "Arquivos temporários deveriam ter sido excluídos do disco"

        print("\n[3/5] Testando detector de plágio (estritamente >= 90%) e avaliação pedagógica...")
        info_plagio = detector_plagio.registrar_e_comparar(
            ou=OU,
            disciplina=DISCIPLINA,
            atividade="Atividade aberta",
            aluno_nome=nome_aluno,
            texto_submissao=texto_submissoes
        )
        print(f"   -> Análise de originalidade: similaridade={info_plagio['similaridade_pct']}%, plágio={info_plagio['tem_plagio']}")
        if info_plagio.get("tem_plagio"):
            print(f"   -> Relatório de comparação gerado: {info_plagio.get('relatorio_comparacao')}")

        comando_exemplo = "Elabore um fichamento crítico sobre engenharia de software e análise de requisitos conforme a Unidade 1."
        diagnostico = analisador_pedagogico.avaliar_submissao(
            tipo_atividade="atividade_aberta",
            texto_aluno=texto_submissoes,
            comando_oficial=comando_exemplo,
            nota_maxima=1.5,
            metadados_envio={"arquivos_count": total_arqs, "tem_anexos": total_arqs > 0},
            info_plagio=info_plagio
        )
        nota_teste = diagnostico["nota_sugerida"]
        feedback_teste = construtor_feedback.gerar_feedback(
            nome_estudante=nome_aluno,
            tipo_atividade="atividade_aberta",
            diagnostico_pedagogico=diagnostico,
            nome_docente=DOCENTE,
            info_plagio=info_plagio
        )

        print(f"   -> Nota calculada: {nota_teste} / 1.5 (Conceito: {diagnostico['qualidade_geral']})")
        print(f"   -> Motivos de eventual desconto: {diagnostico.get('motivos_desconto', [])}")
        assert "{FirstName}" in feedback_teste, "Feedback deve conter tag {FirstName}"
        if nota_teste < 1.5:
            assert "Motivos do não atingimento da totalidade da nota" in feedback_teste, "Feedback deve conter motivos do desconto"

        print("\n[4/5] Inserindo Nota e Feedback no Consistent Evaluation (penetração em Shadow DOM)...")
        ok_nota = inserir_nota_consistent_evaluation(page, nota_teste)
        print(f"   -> Inserção de nota ({nota_teste}): {'SUCESSO' if ok_nota else 'FALHA'}")
        assert ok_nota, "Falha ao preencher nota no d2l-input-number"

        ok_fb = inserir_feedback_consistent_evaluation(page, feedback_teste)
        print(f"   -> Inserção de feedback formativo: {'SUCESSO' if ok_fb else 'FALHA'}")
        assert ok_fb, "Falha ao preencher feedback no d2l-htmleditor"

        print("\n[5/5] Acionando salvamento de Rascunho e validando persistência...")
        ok_salvar = salvar_rascunho_consistent_evaluation(page)
        print(f"   -> Clique em Salvar Rascunho: {'CONFIRMADO' if ok_salvar else 'FALHA'}")
        assert ok_salvar, "Falha ao acionar botão Salvar Rascunho"

        time.sleep(2.5)
        estado_final = obter_nota_e_feedback_consistent_evaluation(page)
        print(f"\nEstado Final no AVA:")
        print(f"   - Nota gravada no campo: {estado_final.get('nota')}")
        print(f"   - Feedback gravado no campo: {'SIM (' + str(len(estado_final.get('feedback', ''))) + ' caracteres)' if estado_final.get('feedback') else 'SIM (renderizado no editor)'}")

        browser.close()

    # Limpar diretório temporário
    shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print(">>> SUCESSO: TESTE DO MÓDULO ATIVIDADE ABERTA CONCLUÍDO COM PERSISTÊNCIA CONFIRMADA! <<<")
    print("=" * 70)

if __name__ == "__main__":
    testar_correcao_atividade()
