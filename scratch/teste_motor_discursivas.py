import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.motor_discursivas import motor_discursivas

def test_pipeline():
    print("=" * 70)
    print("TESTE DO NOVO MOTOR UNIVERSAL DE DISCURSIVAS: PIPELINE DE 4 PASSOS")
    print("=" * 70)

    # 1. Simular Enunciado Oficial (qualquer disciplina)
    enunciado_teste = (
        "Os Sistemas de Informação estão presentes em diferentes atividades e níveis de uma organização, "
        "desde o registro das operações do dia a dia até o apoio às decisões gerenciais e estratégicas.\n\n"
        "Explique, com suas palavras, como os Sistemas de Informação podem contribuir para o funcionamento "
        "e a gestão de uma organização. Em sua resposta, apresente pelo menos dois exemplos de sistemas "
        "ou de aplicações estudados na disciplina."
    )
    valor_maximo = 2.0

    print("\n[Passo 1] Enunciado Carregado:")
    print(enunciado_teste[:160] + "...")

    # 2. Criar Critérios Pedagógicos Dinâmicos
    print("\n[Passo 2] Gerando Critérios Pedagógicos Dinâmicos:")
    criterios = motor_discursivas.gerar_criterios_avaliacao(enunciado_teste, valor_maximo)
    soma_pesos = sum(c["peso"] for c in criterios)
    print(f"Total critérios gerados: {len(criterios)} | Soma dos pesos: {soma_pesos:.2f} pts")
    for c in criterios:
        print(f"  * {c['nome']} (Peso: {c['peso']:.2f} pts)")
        print(f"    -> {c['descricao']}")

    assert len(criterios) == 3, "Devem existir 3 critérios"
    assert round(soma_pesos, 2) == valor_maximo, "Soma dos pesos deve ser igual ao valor máximo"

    # 3. Ver Exemplo de Resposta / Gabarito Comentado
    print("\n[Passo 3] Gerando Exemplo de Resposta (Padrão Esperado):")
    gabarito = motor_discursivas.gerar_exemplo_resposta(enunciado_teste, criterios)
    print(gabarito[:250] + "...\n")
    assert len(gabarito) > 100, "Gabarito de resposta deve ser detalhado"

    # 4. Avaliar Respostas de Teste
    print("[Passo 4] Testando Avaliação de Respostas de Estudantes:")
    
    # Caso A: Aluno com resposta excelente (domínio + 2 exemplos claros)
    resp_excelente = (
        "Os Sistemas de Informação são vitais para as organizações modernas porque automatizam rotinas, integram "
        "diferentes setores e fornecem relatórios precisos para a tomada de decisão gerencial e estratégica. "
        "Como primeiro exemplo, temos o ERP (Enterprise Resource Planning), que integra finanças, recursos humanos "
        "e suprimentos em um banco de dados centralizado. Como segundo exemplo, destaco o CRM (Customer Relationship Management), "
        "que gerencia as interações com clientes, o histórico de vendas e auxilia no pós-venda e fidelização."
    )
    diag_a = motor_discursivas.avaliar_estudante(
        texto_aluno=resp_excelente,
        nome_aluno="Vinícius Soares",
        enunciado=enunciado_teste,
        criterios=criterios,
        valor_maximo=valor_maximo,
        docente="Prof. Arly Cristopher",
        ou="155399",
        disciplina="Sistemas de Informação"
    )
    print(f"  -> Caso A (Excelente): Nota = {diag_a['nota']:.2f} / {valor_maximo:.2f} (Conceito: {diag_a['qualidade']})")
    assert diag_a["nota"] >= 1.8, "Resposta excelente deve ter nota alta"

    # Caso B: Aluno com resposta parcial (sem exemplos claros)
    resp_parcial = (
        "Os sistemas ajudam as empresas a funcionarem melhor e organizarem seus dados para os gestores."
    )
    diag_b = motor_discursivas.avaliar_estudante(
        texto_aluno=resp_parcial,
        nome_aluno="Lucas Lima",
        enunciado=enunciado_teste,
        criterios=criterios,
        valor_maximo=valor_maximo,
        docente="Prof. Arly Cristopher",
        ou="155399",
        disciplina="Sistemas de Informação"
    )
    print(f"  -> Caso B (Parcial): Nota = {diag_b['nota']:.2f} / {valor_maximo:.2f} (Conceito: {diag_b['qualidade']})")
    print(f"     Descontos identificados: {diag_b['descontos']}")
    assert diag_b["nota"] < valor_maximo, "Resposta parcial deve ter desconto"
    assert len(diag_b["descontos"]) > 0, "Deve listar justificativas para o desconto"
    assert "Justificativa do Desconto de Nota" in diag_b["feedback_html"], "Feedback deve ter seção de Justificativa do Desconto de Nota"
    for d in diag_b["descontos"]:
        assert "(-" not in d and "pts)" not in d, f"Desconto não deve conter valor numérico: {d}"

    # Caso C: Aluno em branco
    diag_c = motor_discursivas.avaliar_estudante(
        texto_aluno="",
        nome_aluno="Aluno Ausente",
        enunciado=enunciado_teste,
        criterios=criterios,
        valor_maximo=valor_maximo,
        docente="Prof. Arly Cristopher",
        ou="155399",
        disciplina="Sistemas de Informação"
    )
    print(f"  -> Caso C (Em Branco): Nota = {diag_c['nota']:.2f} / {valor_maximo:.2f} (Conceito: {diag_c['qualidade']})")
    assert diag_c["nota"] == 0.0, "Envio em branco deve receber nota zero"

    # Teste de Auditoria de Coerência
    print("\n[Auditoria] Executando Auditoria Final de Coerência:")
    turma_teste = [
        {"aluno": "Vinícius", "nota": diag_a["nota"], "qualidade": diag_a["qualidade"], "descontos": diag_a["descontos"], "plagio": False},
        {"aluno": "Lucas", "nota": diag_b["nota"], "qualidade": diag_b["qualidade"], "descontos": diag_b["descontos"], "plagio": False},
        {"aluno": "Ausente", "nota": diag_c["nota"], "qualidade": diag_c["qualidade"], "descontos": diag_c["descontos"], "plagio": False},
    ]
    motor_discursivas.executar_auditoria_coerencia(turma_teste, "155399", "Sistemas de Informação", valor_maximo)

    print("\n" + "=" * 70)
    print(">>> SUCESSO: TESTE COMPLETO DO MOTOR UNIVERSAL DE DISCURSIVAS APROVADO! <<<")
    print("=" * 70)

if __name__ == "__main__":
    test_pipeline()
