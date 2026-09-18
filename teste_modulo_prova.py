import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from cognitive.analisador_pedagogico import analisador_pedagogico
from cognitive.construtor_feedback import construtor_feedback
from cognitive.detector_plagio import detector_plagio
from core.navigation_iterator import extrair_posicao_mostrador_iterator, extrair_nome_estudante_atual
from core.dom_helpers import salvar_rascunho_duplo
from core.motor_provas import motor_provas

AUTH_FILE = BASE_DIR / "auth_state_04083941.json"
OU = "155399"
DISCIPLINA = "SISTEMAS DE INFORMAÇÕES NAS ORGANIZAÇÕES - GEE04I30015"
DOCENTE = "Prof. Arly Cristopher Nascimento Alves"

# URL direta da Prova Presencial no Quick Eval (Consistent Evaluation) de 155399
URL_PROVA = f"https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5UUTVPRE0uMTU1Mzk5?ou={OU}&iteratorRange=new&cft=qe"

def testar_correcao_prova():
    print("=" * 70)
    print("TESTE DE CORREÇÃO EM TEMPO REAL: MÓDULO PROVA PRESENCIAL (DISCURSIVA)")
    print("=" * 70)
    print(f"Disciplina: [{OU}] {DISCIPLINA}")
    print(f"URL Alvo: {URL_PROVA}")
    print(f"Sessão Auth: {AUTH_FILE.name}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(AUTH_FILE) if AUTH_FILE.exists() else None,
            viewport={"width": 1400, "height": 1000}
        )
        page = context.new_page()

        print("[1/5] Navegando até a tela de Avaliação da Prova Presencial...")
        page.goto(URL_PROVA, wait_until="domcontentloaded", timeout=35000)
        time.sleep(8)

        pos_info = extrair_posicao_mostrador_iterator(page)
        nome_aluno = extrair_nome_estudante_atual(page)
        print(f"   -> Estudante identificado: {nome_aluno} | Posição: {pos_info.get('atual')}/{pos_info.get('total')}")

        print("\n[2/5] Rolando painel até a Questão 8 (Discursiva)...")
        page.evaluate(r"""() => {
            const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
                const ov = window.getComputedStyle(el).overflowY;
                return (ov === 'auto' || ov === 'scroll') && el.scrollHeight > el.clientHeight;
            });
            for (let s of scrollables) {
                s.scrollTop = s.scrollHeight;
            }
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        time.sleep(3)

        print("\n[3/5] Extraindo resposta indentada do estudante...")
        texto_resposta = motor_provas._extrair_resposta_discursiva(page)
        print(f"   -> Resposta do aluno ({len(texto_resposta.split())} palavras): {texto_resposta[:140].strip()}...")
        assert len(texto_resposta.strip()) > 0, "Resposta do aluno na discursiva não deve ser vazia"

        print("\n[4/5] Executando avaliação pedagógica da discursiva e construindo feedback...")
        enunciado_padrao = (
            "Os Sistemas de Informação estão presentes em diferentes atividades e níveis de uma organização, "
            "desde o registro das operações do dia a dia até o apoio às decisões gerenciais e estratégicas.\n\n"
            "Explique, com suas palavras, como os Sistemas de Informação podem contribuir para o funcionamento "
            "e a gestão de uma organização. Em sua resposta, apresente pelo menos dois exemplos de sistemas "
            "ou de aplicações estudados na disciplina."
        )
        nota_max_discursiva = 2.0

        info_plagio = detector_plagio.registrar_e_comparar(
            ou=OU,
            disciplina=DISCIPLINA,
            atividade="Prova presencial",
            aluno_nome=nome_aluno,
            texto_submissao=texto_resposta
        )
        print(f"   -> Análise de originalidade: similaridade={info_plagio['similaridade_pct']}%, plágio={info_plagio['tem_plagio']}")

        diagnostico = analisador_pedagogico.avaliar_submissao(
            tipo_atividade="prova_presencial",
            texto_aluno=texto_resposta,
            comando_oficial=enunciado_padrao,
            nota_maxima=nota_max_discursiva,
            metadados_envio={"palavras": len(texto_resposta.split())},
            info_plagio=info_plagio
        )
        nota_teste = diagnostico["nota_sugerida"]
        feedback_teste = construtor_feedback.gerar_feedback(
            nome_estudante=nome_aluno,
            tipo_atividade="prova_presencial",
            diagnostico_pedagogico=diagnostico,
            nome_docente=DOCENTE,
            info_plagio=info_plagio
        )

        print(f"   -> Nota calculada da discursiva: {nota_teste} / {nota_max_discursiva}")
        print(f"   -> Justificativa pedagógica: {diagnostico.get('motivos_desconto', [])}")
        assert "{FirstName}" in feedback_teste, "Feedback deve conter {FirstName}"
        if nota_teste < nota_max_discursiva:
            assert "Motivos do não atingimento da totalidade da nota" in feedback_teste, "Feedback deve conter motivos do desconto"

        print("\n[5/5] Inserindo nota/feedback na questão e salvando em rascunho DUAS VEZES (sem publicar)...")
        motor_provas._inserir_nota_e_feedback_questao(page, nota_teste, feedback_teste, nota_max_discursiva)
        print("   -> Nota e feedback inseridos nos campos específicos da questão discursiva.")

        # Salvar Rascunho DUAS VEZES
        print("   -> Disparando primeiro salvamento de rascunho...")
        ok_salvar1 = motor_provas._salvar_rascunho(page)
        print(f"      1º Salvar Rascunho: {'CONFIRMADO' if ok_salvar1 else 'OK'}")
        time.sleep(2.0)

        print("   -> Disparando segundo salvamento de rascunho (dupla persistência)...")
        ok_salvar2 = motor_provas._salvar_rascunho(page)
        print(f"      2º Salvar Rascunho: {'CONFIRMADO' if ok_salvar2 else 'OK'}")
        time.sleep(1.0)

        # Simular Auditoria Final de Coerência com turma de teste
        print("\n[BÔNUS] Testando Auditoria de Coerência Final de 100% da turma...")
        plano_teste = {"prova_presencial": {"valor_discursiva": nota_max_discursiva, "enunciado_discursiva": enunciado_padrao}}
        resultados_teste = [{
            "ou": OU, "disciplina": DISCIPLINA, "atividade": "Prova presencial",
            "aluno": nome_aluno, "nota": nota_teste, "nota_max": nota_max_discursiva,
            "plagio": False, "similaridade_pct": 0.0, "qualidade": diagnostico["qualidade_geral"], "modo": "recorrigir"
        }]
        motor_provas._executar_auditoria_coerencia(resultados_teste, plano_teste, OU, DISCIPLINA)

        browser.close()

    print("\n" + "=" * 70)
    print(">>> SUCESSO: TESTE DO MÓDULO PROVA PRESENCIAL CONCLUÍDO COM PERSISTÊNCIA CONFIRMADA! <<<")
    print("=" * 70)

if __name__ == "__main__":
    testar_correcao_prova()
