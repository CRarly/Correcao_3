import os
import sys
from pathlib import Path

# Ajustar sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

def test_imports():
    print("1. Testando importação dos módulos...")
    import config
    import engine_state
    from cognitive import extrair_texto_documento, detector_plagio, analisador_pedagogico, construtor_feedback
    from core import BrowserSession, inspector_disciplina, motor_foruns, motor_atividades, motor_provas, orquestrador
    import app
    print("   -> Todos os módulos importados com sucesso!")

def test_extrator_documentos():
    print("\n2. Testando extrator de documentos...")
    from cognitive.extrator_documentos import extrair_texto_documento
    # Testar com arquivo de texto temporário
    teste_txt = BASE_DIR / "teste_doc.txt"
    teste_txt.write_text("Este é um texto de teste para validação de extração acadêmica.", encoding="utf-8")
    res = extrair_texto_documento(teste_txt)
    assert res["sucesso"] is True, "Falha na extração de texto"
    assert res["palavras"] > 5, "Contagem de palavras incorreta"
    teste_txt.unlink()
    print(f"   -> Extrator OK ({res['palavras']} palavras extraídas).")

def test_detector_plagio():
    print("\n3. Testando detector de plágio cruzado...")
    from cognitive.detector_plagio import detector_plagio
    
    ou = "999999"
    disc = "DISCIPLINA TESTE"
    ativ = "Fórum de teste"
    
    texto_autor = (
        "A governança corporativa no contexto ágil requer a sincronização de papéis estratégicos, "
        "garantindo transparência nas entregas incrementais e conformidade contínua com os objetivos de negócio. "
        "Nesse sentido, a comunicação dialógica entre stakeholders minimiza o risco de retrabalho."
    )
    
    # Estudante 1 envia
    res1 = detector_plagio.registrar_e_comparar(ou, disc, ativ, "Carlos Silva", texto_autor)
    assert res1["tem_plagio"] is False, "Não deveria acusar plágio no primeiro envio"
    
    # Estudante 2 envia cópia idêntica
    res2 = detector_plagio.registrar_e_comparar(ou, disc, ativ, "Mariana Oliveira", texto_autor)
    assert res2["tem_plagio"] is True, "Deveria ter detectado cópia"
    assert res2["similaridade_pct"] >= 90.0, f"Similaridade esperada >= 90%, obteve {res2['similaridade_pct']}%"
    assert res2["aluno_autor"] == "Carlos Silva", "Autor original deveria ser Carlos Silva"
    assert res2["aluno_copiador"] == "Mariana Oliveira", "Copiador deveria ser Mariana Oliveira"
    print(f"   -> Detector de plágio OK (Identificado: {res2['aluno_copiador']} copiou de {res2['aluno_autor']} com {res2['similaridade_pct']}% de similaridade).")

def test_analisador_pedagogico():
    print("\n4. Testando analisador pedagógico multicritério...")
    from cognitive.analisador_pedagogico import analisador_pedagogico
    
    comando = "Desenvolva uma análise crítica sobre os pilares da governança de TI e explique sua relação com a entrega de valor contínuo."
    texto_bom = (
        "No que tange aos pilares da governança de TI, evidencia-se que o alinhamento estratégico e o gerenciamento "
        "de riscos constituem a base fundamental para sustentar a entrega de valor contínuo. "
        "Portanto, ao conectar os objetivos de tecnologia com a estratégia corporativa, a organização assegura "
        "maior previsibilidade e redução de desperdícios operacionais. Além disso, a mensuração sistemática de desempenho "
        "permite ajustes tempestivos diante de oscilações de mercado."
    )
    
    diag = analisador_pedagogico.avaliar_submissao(
        tipo_atividade="forum",
        texto_aluno=texto_bom,
        comando_oficial=comando,
        nota_maxima=1.0,
        metadados_envio={"posts_count": 1, "replies_count": 1}
    )
    
    assert diag["nota_sugerida"] >= 0.85, f"Nota esperada >= 0.85, obteve {diag['nota_sugerida']}"
    assert diag["qualidade_geral"] in ["Excelente", "Bom"], f"Conceito inesperado: {diag['qualidade_geral']}"
    print(f"   -> Analisador Pedagógico OK (Nota atribuída: {diag['nota_sugerida']}/1.0 - Conceito: {diag['qualidade_geral']}).")

def test_construtor_feedback():
    print("\n5. Testando construtor de feedbacks humanizados com {FirstName}...")
    from cognitive.construtor_feedback import construtor_feedback
    
    diag = {
        "nota_sugerida": 1.0,
        "nota_maxima": 1.0,
        "qualidade_geral": "Excelente",
        "pontos_fortes": ["Demonstrou domínio terminológico e contextualização clara."],
        "pontos_melhoria": []
    }
    
    fb = construtor_feedback.gerar_feedback(
        nome_estudante="Maria Eduarda Santos",
        tipo_atividade="forum",
        diagnostico_pedagogico=diag,
        nome_docente="Prof. Arly Cristopher Nascimento Alves"
    )
    
    assert "{FirstName}" in fb, "Tag oficial {FirstName} não encontrada no feedback"
    assert "Prof. Arly Cristopher Nascimento Alves" in fb, "Assinatura do docente ausente"
    print(f"   -> Construtor de feedback OK (Uso estrito da tag Brightspace: 'Olá, {{FirstName}}!').")

def test_rotas_app():
    print("\n6. Testando rotas FastAPI do novo sistema...")
    from app import app
    rotas = [r.path for r in app.routes]
    esperadas = ["/", "/api/discover", "/api/inspect", "/api/start", "/api/stop", "/api/status", "/api/relatorios", "/api/relatorios/{report_id}"]
    for exp in esperadas:
        assert exp in rotas, f"Rota {exp} ausente no app"
    print(f"   -> Todas as rotas da API registradas ({len(rotas)} rotas ativas).")

def test_relatorio_persist():
    print("\n7. Testando persistência e índice histórico de relatórios...")
    from core.orquestrador import orquestrador
    from config import RELATORIOS_DIR
    import json

    dados_simulados = [
        {
            "ou": "155377",
            "disciplina": "PROGRAMAÇÃO ORIENTADA A OBJETOS",
            "atividade": "Fórum de discussão",
            "aluno": "João Victor Ribeiro",
            "nota": 1.0,
            "nota_max": 1.0,
            "plagio": False,
            "similaridade_pct": 0.0,
            "qualidade": "Excelente",
            "modo": "tradicional"
        }
    ]

    arquivos = orquestrador._persistir_relatorio(
        relatorio_id="teste_unitario",
        resultados=dados_simulados,
        modo="tradicional",
        docente="Prof. Arly Cristopher Nascimento Alves"
    )

    assert Path(arquivos["json"]).exists(), "Arquivo JSON do relatório não foi gerado"
    assert Path(arquivos["csv"]).exists(), "Arquivo CSV do relatório não foi gerado"
    
    # Conferir se index_relatorios.json foi atualizado
    idx_path = RELATORIOS_DIR / "index_relatorios.json"
    assert idx_path.exists(), "index_relatorios.json não encontrado"
    with open(idx_path, "r", encoding="utf-8") as f:
        idx_data = json.load(f)
    assert any(r["id"] == "teste_unitario" for r in idx_data), "ID de teste não encontrado no índice"

    print("   -> Persistência de relatórios e indexador OK!")

def test_analise_atividade_com_anexos():
    print("\n8. Testando análise de Atividade Aberta com anexos (não dar zero nem falso branco)...")
    from cognitive.analisador_pedagogico import analisador_pedagogico
    
    # Estudante enviou arquivo documental
    diag = analisador_pedagogico.avaliar_submissao(
        tipo_atividade="atividade_aberta",
        texto_aluno="Resolução da atividade em arquivo anexo com diagramas e código.",
        comando_oficial="Implemente o diagrama de classes e código Java correspondente.",
        nota_maxima=1.5,
        metadados_envio={"arquivos_count": 1, "tem_anexos": True}
    )
    assert diag["nota_sugerida"] > 0.0, "Não deve atribuir zero quando há anexo"
    assert "Ausência de conteúdo relevante ou envio em branco." not in diag["pontos_melhoria"], "Falso positivo de envio em branco detectado"
    assert diag["cumprimento_regras"] == 1.0, "Cumprimento de regras deve ser 1.0 quando há arquivo documental"
    print(f"   -> Análise de anexos OK (Nota: {diag['nota_sugerida']}/1.5 - Cumprimento: {diag['cumprimento_regras']}).")

def test_navigation_iterator_helpers():
    print("\n9. Testando helpers de navegação e iterator seguro...")
    from core.navigation_iterator import (
        extrair_posicao_mostrador_iterator,
        extrair_nome_estudante_atual,
        disparar_clique_proximo,
        verificar_botao_proximo_desabilitado,
        avancar_proximo_estudante_seguro
    )
    assert callable(extrair_posicao_mostrador_iterator)
    assert callable(extrair_nome_estudante_atual)
    assert callable(disparar_clique_proximo)
    assert callable(verificar_botao_proximo_desabilitado)
    assert callable(avancar_proximo_estudante_seguro)
    print("   -> Helpers do iterator importados e operacionais!")

def test_prova_presencial_discursiva_e_coerencia():
    print("\n10. Testando lógica da Prova Presencial (Discursiva), Rascunho Duplo e Auditoria de Coerência...")
    from core.motor_provas import motor_provas
    from core.inspector_disciplina import inspector_disciplina
    from config import RELATORIOS_DIR
    import json

    assert hasattr(motor_provas, "_salvar_rascunho_duplo"), "Método _salvar_rascunho_duplo ausente"
    assert hasattr(motor_provas, "_executar_auditoria_coerencia"), "Método _executar_auditoria_coerencia ausente"
    assert hasattr(motor_provas, "_assegurar_tentativa_carregada"), "Método _assegurar_tentativa_carregada ausente"
    assert hasattr(inspector_disciplina, "_inspecionar_prova_presencial"), "Método _inspecionar_prova_presencial ausente"

    # Simular auditoria de coerência com turma completa (ex.: 97 avaliações)
    plano_simulado = {
        "prova_presencial": {
            "valor_discursiva": 2.0,
            "enunciado_discursiva": "Explique o conceito de herança e polimorfismo em POO."
        }
    }
    resultados_simulados = []
    for i in range(1, 98):
        nota = 2.0 if i % 2 == 0 else 1.8
        qualidade = "Excelente" if i % 2 == 0 else "Muito Bom"
        resultados_simulados.append({
            "ou": "155377",
            "disciplina": "PROGRAMAÇÃO ORIENTADA A OBJETOS",
            "atividade": "Prova presencial",
            "aluno": f"Estudante {i} Silva",
            "nota": nota,
            "nota_max": 2.0,
            "plagio": False,
            "similaridade_pct": 0.0,
            "qualidade": qualidade,
            "modo": "recorrigir"
        })

    motor_provas._executar_auditoria_coerencia(
        resultados=resultados_simulados,
        plano=plano_simulado,
        ou="155377",
        disciplina="PROGRAMAÇÃO ORIENTADA A OBJETOS"
    )

    # Verificar se o arquivo de auditoria foi gravado
    arquivos_auditoria = list(RELATORIOS_DIR.glob("auditoria_coerencia_prova_155377_*.json"))
    assert len(arquivos_auditoria) > 0, "Arquivo de auditoria de coerência não foi gerado"
    
    with open(arquivos_auditoria[-1], "r", encoding="utf-8") as f:
        dados_aud = json.load(f)
    assert dados_aud["total_avaliados"] == 97, f"Esperado 97 avaliados, obteve {dados_aud['total_avaliados']}"
    assert dados_aud["incoerencias_encontradas"] == 0, f"Incoerências inesperadas: {dados_aud['incoerencias_encontradas']}"
    assert dados_aud["media_geral"] > 1.8, "Média calculada incorreta"

    print(f"   -> Prova Presencial & Auditoria de Coerência OK ({dados_aud['total_avaliados']}/{dados_aud['total_avaliados']} auditados com sucesso)!")

if __name__ == "__main__":
    print("=" * 60)
    print("TESTE DE INTEGRIDADE: BRIGHTSPACE GRADER 2.0")
    print("=" * 60)
    try:
        test_imports()
        test_extrator_documentos()
        test_detector_plagio()
        test_analisador_pedagogico()
        test_construtor_feedback()
        test_rotas_app()
        test_relatorio_persist()
        test_analise_atividade_com_anexos()
        test_navigation_iterator_helpers()
        test_prova_presencial_discursiva_e_coerencia()
        print("\n" + "=" * 60)
        print(">>> SUCESSO: TODOS OS 10 TESTES DE VERIFICAÇÃO FORAM APROVADOS! <<<")
        print("=" * 60)
    except AssertionError as ae:
        print(f"\n[FALHA DE ASSERT]: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERRO]: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
