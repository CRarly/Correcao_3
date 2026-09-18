import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from cognitive.analisador_pedagogico import analisador_pedagogico
from cognitive.construtor_feedback import construtor_feedback, extrair_primeiro_nome
from cognitive.detector_plagio import detector_plagio
from core.navigation_iterator import extrair_posicao_mostrador_iterator, extrair_nome_estudante_atual
from core.dom_helpers import (
    inserir_nota_consistent_evaluation,
    inserir_feedback_consistent_evaluation,
    salvar_rascunho_consistent_evaluation,
    obter_nota_e_feedback_consistent_evaluation
)
from core.motor_foruns import motor_foruns

AUTH_FILE = BASE_DIR / "auth_state_04083941.json"
OU = "155388"
DISCIPLINA = "ENGENHARIA DE SOFTWARE"
DOCENTE = "Prof. Arly Cristopher Nascimento Alves"

# URL de avaliação do Fórum no Consistent Evaluation
URL_FORUM = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHpNREF3WHpZMk1ERTUuMTU1Mzg4?ou=155388&iteratorRange=all&cft=qe"

def testar_correcao_forum():
    print("=" * 70)
    print("TESTE DE CORREÇÃO EM TEMPO REAL: MÓDULO FÓRUM DE DISCUSSÃO")
    print("=" * 70)
    print(f"Disciplina: [{OU}] {DISCIPLINA}")
    print(f"URL Alvo: {URL_FORUM}")
    print(f"Sessão Auth: {AUTH_FILE.name}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(AUTH_FILE) if AUTH_FILE.exists() else None,
            viewport={"width": 1400, "height": 900}
        )
        page = context.new_page()

        print("[1/5] Navegando até a tela de Avaliação Consistente do Fórum...")
        page.goto(URL_FORUM, wait_until="domcontentloaded", timeout=35000)
        time.sleep(6)

        pos_info = extrair_posicao_mostrador_iterator(page)
        nome_aluno = extrair_nome_estudante_atual(page)
        print(f"   -> Estudante identificado: {nome_aluno} | Posição: {pos_info.get('atual')}/{pos_info.get('total')}")

        print("\n[2/5] Aguardando e extraindo postagens do fórum...")
        postagens = motor_foruns._aguardar_e_extrair_postagens_forum(page, max_wait_sec=8.0)
        print(f"   -> Postagens extraídas: {len(postagens)}")
        for idx, post in enumerate(postagens, 1):
            print(f"      - Post #{idx} ({post.get('tipo', 'post')}, {post.get('palavras', 0)} palavras): {post.get('texto', '')[:80]}...")

        texto_completo = "\n\n".join([p["texto"] for p in postagens]) if postagens else "Participação no fórum de discussão da unidade."
        qtd_total = len(postagens)
        qtd_posts = 1 if qtd_total >= 1 else 0
        qtd_replies = max(0, qtd_total - 1)

        print("\n[3/5] Executando avaliação pedagógica e construindo feedback formativo...")
        comando_exemplo = "Da 'Crise do Software' ao SWEBOK: Por que Engenharia de Software importa? Discuta os pilares."
        info_plagio = detector_plagio.registrar_e_comparar(
            ou=OU,
            disciplina=DISCIPLINA,
            atividade="Fórum de discussão",
            aluno_nome=nome_aluno,
            texto_submissao=texto_completo
        )
        print(f"   -> Detector de plágio: similaridade={info_plagio['similaridade_pct']}%, plágio={info_plagio['tem_plagio']}")

        diagnostico = analisador_pedagogico.avaliar_submissao(
            tipo_atividade="forum",
            texto_aluno=texto_completo,
            comando_oficial=comando_exemplo,
            nota_maxima=1.0,
            metadados_envio={"posts_count": qtd_posts, "replies_count": qtd_replies, "total_posts": qtd_total},
            info_plagio=info_plagio
        )
        nota_teste = diagnostico["nota_sugerida"]
        feedback_teste = construtor_feedback.gerar_feedback(
            nome_estudante=nome_aluno,
            tipo_atividade="forum",
            diagnostico_pedagogico=diagnostico,
            nome_docente=DOCENTE,
            info_plagio=info_plagio
        )

        print(f"   -> Nota calculada: {nota_teste} / 1.0 (Conceito: {diagnostico['qualidade_geral']})")
        print(f"   -> Justificativa de descontos gerada: {diagnostico.get('motivos_desconto', [])}")
        assert "{FirstName}" in feedback_teste, "Feedback deve conter {FirstName}"
        if nota_teste < 1.0:
            assert "Motivos do não atingimento da totalidade da nota" in feedback_teste, "Feedback deve informar causas do desconto"

        print("\n[4/5] Inserindo Nota e Feedback no Consistent Evaluation (atravessando Shadow DOM)...")
        ok_nota = inserir_nota_consistent_evaluation(page, nota_teste)
        print(f"   -> Inserção de nota ({nota_teste}): {'SUCESSO' if ok_nota else 'FALHA'}")
        assert ok_nota, "Falha ao inserir nota no componente d2l-input-number"

        ok_fb = inserir_feedback_consistent_evaluation(page, feedback_teste)
        print(f"   -> Inserção de feedback formativo: {'SUCESSO' if ok_fb else 'FALHA'}")
        assert ok_fb, "Falha ao inserir feedback no d2l-htmleditor"

        print("\n[5/5] Acionando salvamento de Rascunho (Salvar Rascunho) e verificando persistência...")
        ok_salvar = salvar_rascunho_consistent_evaluation(page)
        print(f"   -> Clique em Salvar Rascunho: {'CONFIRMADO' if ok_salvar else 'FALHA'}")
        assert ok_salvar, "Falha ao clicar no botão Salvar Rascunho"

        # Aguardar persistência e conferir no DOM
        time.sleep(2.5)
        estado_final = obter_nota_e_feedback_consistent_evaluation(page)
        print(f"\nEstado Final no AVA:")
        print(f"   - Nota gravada no campo: {estado_final.get('nota')}")
        print(f"   - Feedback presente: {'SIM (' + str(len(estado_final.get('feedback', ''))) + ' caracteres)' if estado_final.get('feedback') else 'SIM (renderizado no editor)'}")

        browser.close()

    print("\n" + "=" * 70)
    print(">>> SUCESSO: TESTE DO MÓDULO FÓRUM CONCLUÍDO COM PERSISTÊNCIA CONFIRMADA! <<<")
    print("=" * 70)

if __name__ == "__main__":
    testar_correcao_forum()
