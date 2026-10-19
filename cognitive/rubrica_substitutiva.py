import re
from typing import Dict, Any, List

class RubricaSubstitutiva:
    """
    Rubrica analítica padrão para avaliação da Questão Discursiva da Prova Substitutiva (Valor: até 2,00 pontos).
    Questão: EAD_EdS_2026_3_PROREC_QDIS (Cenário de desenvolvimento ágil com desvios de processo e qualidade).

    Critérios de Avaliação:
    1. Diagnóstico dos Problemas das Decisões da Equipe (0,70 pts):
       - Identificação e explicação fundamentada de pelo menos três problemas no cenário:
         * Requisitos de negócio transformados diretamente em tarefas sem análise;
         * Incorporação imediata de alterações sem avaliação de impactos;
         * Supressão indevida de documentação técnica sob pretexto de comunicação ágil;
         * Postergação dos testes para o final das grandes entregas (ausência de testes contínuos);
         * Confusão entre velocidade de entrega e qualidade efetiva do software.
    2. Proposição Técnica de Organização Ágil Integrada (0,80 pts):
       - Indicação de como requisitos, análise, desenvolvimento, testes e feedback devem ser
         articulados de forma equilibrada no ciclo ágil (refinamento de backlog, testes contínuos/TDD,
         gestão de mudanças com análise de impacto e documentação enxuta).
    3. Articulação Conceitual, Coesão e Norma Culta (0,50 pts):
       - Linha de raciocínio articulada, precisão técnica dos conceitos de Engenharia de Software
         e correção gramatical.
    """

    def avaliar(
        self,
        enunciado: str,
        resposta_aluno: str,
        nome_aluno: str = "Estudante",
        nota_maxima: float = 2.00
    ) -> Dict[str, Any]:
        texto = (resposta_aluno or "").strip()
        palavras = len(re.findall(r"\b\w+\b", texto))

        # Caso em branco ou texto insignificante
        if palavras < 5:
            return {
                "nota_total": 0.0,
                "nota_maxima": nota_maxima,
                "criterios": [
                    {"nome": "1. Diagnóstico dos Problemas nas Decisões da Equipe", "nota": 0.0, "max": 0.70, "parecer": "Sem resposta apresentada."},
                    {"nome": "2. Proposição Técnica de Organização Ágil Integrada", "nota": 0.0, "max": 0.80, "parecer": "Sem proposição de organização do trabalho."},
                    {"nome": "3. Articulação, Coesão e Norma Culta", "nota": 0.0, "max": 0.50, "parecer": "Ausência de conteúdo textual."}
                ],
                "descontos": ["Questão sem resposta ou envio em branco."],
                "pontos_fortes": [],
                "pontos_melhoria": ["Desenvolver resposta fundamentada para as questões discursivas da Prova Substitutiva."],
                "feedback_html": "<p>Sua resposta para a Questão Discursiva da Prova Substitutiva foi avaliada com a pontuação de <strong>0.00 de 2.00 pontos</strong>.</p><p>Não foi identificada resposta para a questão discursiva nesta tentativa. Lembre-se de apresentar seu desenvolvimento teórico para pontuação.</p>"
            }

        texto_lower = texto.lower()

        # =========================================================================
        # CRITÉRIO 1: Diagnóstico dos Problemas das Decisões da Equipe (0,70 pts)
        # =========================================================================
        # Identificar pelo menos três problemas apontados no cenário:
        # P1: Requisitos sem análise prévia
        p_requisitos = any(t in texto_lower for t in [
            "sem anlise", "sem análise", "análise de requisito", "analise de requisito", "transformada", "diretamente em tarefa", "sem refinar", "entendimento do negócio"
        ])
        # P2: Alterações sem análise de impacto
        p_impacto = any(t in texto_lower for t in [
            "impacto", "alteraç", "mudança", "incorporada imediatamente", "sem avaliar", "retrabalho"
        ])
        # P3: Supressão indevida de documentação
        p_documentacao = any(t in texto_lower for t in [
            "documenta", "dispensad", "sem documento", "ausência de documento", "comunicação informal", "registro"
        ])
        # P4: Testes postergados para o final / ausência de testes contínuos
        p_testes = any(t in texto_lower for t in [
            "teste", "final da entrega", "final de cada", "defeito", "tarde", "durante o ciclo", "posterga"
        ])
        # P5: Confusão entre velocidade/volume e qualidade
        p_velocidade = any(t in texto_lower for t in [
            "velocidade", "rapidamente", "quantidade de funcionalidade", "apenas entregar", "qualidade não é só velocidade", "métrica"
        ])

        problemas_identificados = sum([1 for p in [p_requisitos, p_impacto, p_documentacao, p_testes, p_velocidade] if p])

        if problemas_identificados >= 3:
            c1_nota = 0.70
            c1_parecer = "Identificou e explicou assertivamente pelo menos três problemas fundamentais nas decisões da equipe (análise de requisitos, gestão de mudanças/impactos, documentação técnica e estratégia de testes)."
        elif problemas_identificados == 2:
            c1_nota = 0.50
            c1_parecer = "Identificou dois problemas relevantes no processo adotado, porém o enunciado solicitava expressamente a abordagem de pelo menos três pontos críticos."
        elif problemas_identificados == 1:
            c1_nota = 0.30
            c1_parecer = "Apontou apenas um problema pontual do cenário, deixando de explorar a amplitude dos desvios de processo e controle de qualidade."
        else:
            c1_nota = 0.15
            c1_parecer = "Não diagnosticou de forma técnica os problemas nas decisões da equipe frente aos conceitos de desenvolvimento ágil e Engenharia de Software."

        # =========================================================================
        # CRITÉRIO 2: Proposição Técnica de Organização Ágil Integrada (0,80 pts)
        # =========================================================================
        # Como organizar o trabalho integrando requisitos, análise, desenvolvimento, testes e feedback
        mencionou_requisitos_analise = any(t in texto_lower for t in [
            "requisito", "análise", "analise", "refinamento", "backlog", "história", "critério de aceitação", "entendimento"
        ])
        mencionou_testes_continuos = any(t in texto_lower for t in [
            "teste contínuo", "testes contínuos", "durante o desenvolvimento", "durante as iterações", "tdd", "teste automatizado", "testes integrados", "antes de entregar"
        ])
        mencionou_feedback_iteracao = any(t in texto_lower for t in [
            "feedback", "iteração", "iterativo", "ciclo", "revisão", "demonstração", "sprint review", "adaptação", "melhoria contínua"
        ])
        mencionou_equilibrio_agil = any(t in texto_lower for t in [
            "equilíbrio", "não significa ausência", "disciplina", "controle de qualidade", "processo ágil", "organizar o trabalho", "documentação ágil", "documentação enxuta"
        ])

        elementos_proposta = sum([1 for e in [mencionou_requisitos_analise, mencionou_testes_continuos, mencionou_feedback_iteracao, mencionou_equilibrio_agil] if e])

        if elementos_proposta >= 3:
            c2_nota = 0.80
            c2_parecer = "Apresentou excelente proposição de organização do trabalho, integrando análise contínua de requisitos, testes ao longo das iterações e ciclos de feedback estruturados sob a perspectiva ágil."
        elif elementos_proposta == 2:
            c2_nota = 0.55
            c2_parecer = "Propôs melhorias pertinentes para o fluxo de trabalho, porém a articulação entre todas as dimensões solicitadas (requisitos, análise, testes e feedback) poderia ser mais completa."
        elif elementos_proposta == 1:
            c2_nota = 0.35
            c2_parecer = "Apresentou sugestões genéricas de organização, sem detalhar como articular requisitos, testes contínuos e feedback no modelo ágil."
        else:
            c2_nota = 0.15
            c2_parecer = "Não atendeu plenamente à solicitação de propor uma organização estruturada e integrada do trabalho em conformidade com as boas práticas ágeis."

        # =========================================================================
        # CRITÉRIO 3: Articulação, Coesão e Norma Culta (0,50 pts)
        # =========================================================================
        desvios_gramaticais = 0
        if "projeto do projeto" in texto_lower or "há a " in texto_lower:
            desvios_gramaticais += 1
        if texto.endswith(",") or ",," in texto:
            desvios_gramaticais += 1

        if palavras >= 60 and desvios_gramaticais == 0:
            c3_nota = 0.50
            c3_parecer = "Texto bem articulado, coeso, com vocabulário técnico apropriado e conformidade com a norma padrão da língua portuguesa."
        elif palavras >= 35:
            c3_nota = 0.35
            c3_parecer = "Estrutura textual compreensível e conectada ao problema, apresentando adequação básica à norma culta."
        else:
            c3_nota = 0.20
            c3_parecer = "Construção textual demasiadamente concisa ou fragmentada, necessitando de maior articulação expositiva e rigor formal."

        # Cálculo Total
        nota_final = round(c1_nota + c2_nota + c3_nota, 2)
        # Arredondamento para múltiplo de 0,05
        nota_final = round(nota_final * 20) / 20
        nota_final = min(nota_maxima, max(0.0, nota_final))

        # Identificar causas dos descontos e pontos fortes
        descontos = []
        pontos_fortes = []
        pontos_melhoria = []

        if c1_nota >= 0.65:
            pontos_fortes.append("Excelente diagnóstico dos problemas nas decisões da equipe, destacando as falhas em requisitos, análise e controle de qualidade.")
        else:
            if problemas_identificados < 3:
                descontos.append(
                    "Omissão parcial no diagnóstico dos problemas: o comando da questão solicitava explicitamente identificar e explicar pelo menos três falhas nas decisões da equipe (ex.: requisitos sem análise prévia, incorporação imediata de mudanças sem avaliação de impacto, postergação de testes para o final ou supressão indevida de documentação essencial)."
                )
            pontos_melhoria.append("Aprofundar a análise crítica de todas as decisões problemáticas descritas no estudo de caso.")

        if c2_nota >= 0.70:
            pontos_fortes.append("Proposição sólida e equilibrada de organização ágil, conectando requisitos, testes e feedback contínuos.")
        else:
            descontos.append(
                "Proposição técnica incompleta: faltou articular de modo detalhado como requisitos, análise, desenvolvimento, testes integrados e ciclos de feedback devem coexistir no modelo ágil sem comprometer a qualidade."
            )
            pontos_melhoria.append("Integrar práticas técnicas (como testes contínuos e refinamento de requisitos) na proposição de melhoria do processo de trabalho.")

        if c3_nota < 0.45:
            descontos.append("Articulação textual e norma padrão: recomenda-se maior desenvolvimento argumentativo, revisão de pontuação e polimento estilístico.")

        # Construção do Parecer Pedagógico Formatado em HTML para o TinyMCE
        feedback_html = self._gerar_feedback_html(
            nota=nota_final,
            nota_max=nota_maxima,
            c1_parecer=c1_parecer,
            c2_parecer=c2_parecer,
            c3_parecer=c3_parecer,
            pontos_fortes=pontos_fortes,
            descontos=descontos
        )

        return {
            "nota_total": nota_final,
            "nota_maxima": nota_maxima,
            "criterios": [
                {"nome": "1. Diagnóstico dos Problemas nas Decisões da Equipe", "nota": c1_nota, "max": 0.70, "parecer": c1_parecer},
                {"nome": "2. Proposição Técnica de Organização Ágil Integrada", "nota": c2_nota, "max": 0.80, "parecer": c2_parecer},
                {"nome": "3. Articulação, Coesão e Norma Culta", "nota": c3_nota, "max": 0.50, "parecer": c3_parecer}
            ],
            "descontos": descontos,
            "pontos_fortes": pontos_fortes,
            "pontos_melhoria": pontos_melhoria,
            "feedback_html": feedback_html
        }

    def _gerar_feedback_html(
        self,
        nota: float,
        nota_max: float,
        c1_parecer: str,
        c2_parecer: str,
        c3_parecer: str,
        pontos_fortes: List[str],
        descontos: List[str]
    ) -> str:
        partes = [
            f"<p>Sua resposta para a Questão Discursiva da Prova Substitutiva foi avaliada com a pontuação de <strong>{nota:.2f} de {nota_max:.2f} pontos</strong>.</p>",
            "<p><strong>Análise Detalhada dos Critérios:</strong></p>",
            "<ul>",
            f"<li><strong>Diagnóstico das Decisões da Equipe:</strong> {c1_parecer}</li>",
            f"<li><strong>Proposição de Organização Ágil:</strong> {c2_parecer}</li>",
            f"<li><strong>Articulação e Clareza Textual:</strong> {c3_parecer}</li>",
            "</ul>"
        ]

        if descontos:
            partes.append("<p><strong>Justificativa do Desconto de Nota:</strong></p>")
            partes.append("<ul>")
            for desc in descontos:
                partes.append(f"<li>{desc}</li>")
            partes.append("</ul>")

        partes.append(
            "<p>Continue empenhado(a) em articular os princípios ágeis à disciplina de Engenharia de Software e garantia da qualidade. Conte com o apoio docente na disciplina!</p>"
        )
        return "".join(partes)

rubrica_substitutiva = RubricaSubstitutiva()
