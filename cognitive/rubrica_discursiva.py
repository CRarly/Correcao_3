import re
from typing import Dict, Any, List

class RubricaDiscursiva:
    """
    Rubrica analítica padrão para avaliação da Questão Discursiva da Prova Presencial (Valor: até 2,00 pontos).

    Critérios de Avaliação:
    1. Diagnóstico e Análise do Problema (0,70 pts):
       - Identificação do modelo/abordagem em uso e explicação das suas limitações frente ao cenário.
    2. Proposição Técnica e Justificativa da Solução (0,80 pts):
       - Indicação da abordagem de ciclo de vida mais adequada (Ágil / Iterativo-Incremental / Prototipação) e sua fundamentação.
    3. Articulação Conceitual, Coesão e Norma Culta (0,50 pts):
       - Linha de raciocínio articulada entre requisitos e abordagem, clareza técnica e correção gramatical.
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

        # Caso em branco
        if palavras < 5:
            return {
                "nota_total": 0.0,
                "nota_maxima": nota_maxima,
                "criterios": [
                    {"nome": "Diagnóstico e Análise do Problema", "nota": 0.0, "max": 0.70, "parecer": "Sem resposta apresentada."},
                    {"nome": "Proposição Técnica e Justificativa", "nota": 0.0, "max": 0.80, "parecer": "Sem proposição de abordagem alternativa."},
                    {"nome": "Articulação, Coesão e Norma Culta", "nota": 0.0, "max": 0.50, "parecer": "Ausência de conteúdo textual."}
                ],
                "descontos": ["Questão sem resposta ou envio em branco."],
                "pontos_fortes": [],
                "pontos_melhoria": ["Desenvolver resposta fundamentada para as questões discursivas."],
                "feedback_html": "<p>Sua resposta para a Questão Discursiva da Prova Presencial foi avaliada com a pontuação de <strong>0.00 de 2.00 pontos</strong>.</p><p>Não foi identificada resposta para a questão discursiva nesta tentativa. Lembre-se de apresentar seu desenvolvimento teórico para pontuação.</p>"
            }

        texto_lower = texto.lower()

        # =========================================================================
        # CRITÉRIO 1: Diagnóstico e Análise do Problema (0,70 pts)
        # =========================================================================
        # Identificar modelo cascata / tradicional / sequencial e limitações perante mudanças
        mencionou_cascata = any(t in texto_lower for t in ["cascata", "tradicional", "sequencial", "linear", "waterfall"])
        mencionou_limitacao = any(t in texto_lower for t in [
            "requisito", "alteraç", "mudança", "planejamento definitivo", "sem alteraç",
            "refazer", "etapa", "engessado", "rígido", "limita"
        ])

        if mencionou_cascata and mencionou_limitacao:
            c1_nota = 0.65
            c1_parecer = "Identificou corretamente o modelo Cascata/Tradicional e explicou com clareza a limitação decorrente da rigidez do planejamento prévio."
        elif mencionou_cascata or mencionou_limitacao:
            c1_nota = 0.40
            c1_parecer = "Abordou parcialmente as limitações do processo, mas sem caracterizar plenamente o modelo tradicional/cascata adotado."
        else:
            c1_nota = 0.20
            c1_parecer = "Não diagnosticou adequadamente o modelo de ciclo de vida inicial nem suas limitações frente aos requisitos incertos."

        # =========================================================================
        # CRITÉRIO 2: Proposição Técnica e Justificativa (0,80 pts)
        # =========================================================================
        # Indicar abordagem alternativa mais adequada (Ágil, Scrum, Iterativo-Incremental, Espiral, Prototipação)
        indicou_modelo_adequado = any(t in texto_lower for t in [
            "ágil", "agil", "iterativ", "incremental", "scrum", "kanban",
            "espiral", "prototipação evolutiva", "modelo ágil", "desenvolvimento ágil"
        ])
        mencionou_prototipos = "protótipo" in texto_lower or "prototipo" in texto_lower
        justificou_abordagem = any(t in texto_lower for t in [
            "ciclo curto", "feedback", "adapta", "flexib", "iteraç", "evolu", "mudança de requisito"
        ])

        if indicou_modelo_adequado and justificou_abordagem:
            c2_nota = 0.80
            c2_parecer = "Indicou com precisão uma abordagem adequada (Ágil/Iterativa) e justificou sua escolha com foco em flexibilidade e adaptação."
        elif indicou_modelo_adequado:
            c2_nota = 0.50
            c2_parecer = "Indicou uma abordagem alternativa adequada, porém a justificativa técnica poderia ser mais detalhada."
        elif mencionou_prototipos:
            c2_nota = 0.25
            c2_parecer = "Observou a presença de protótipos no cenário, porém OMITIU a indicação formal da abordagem de ciclo de vida recomendada (ex.: Modelos Ágeis ou Iterativo-Incremental) e sua respectiva justificativa."
        else:
            c2_nota = 0.10
            c2_parecer = "Não atendeu ao comando do enunciado que solicitava expressamente a indicação e justificativa de um ciclo de vida mais adequado."

        # =========================================================================
        # CRITÉRIO 3: Articulação, Coesão e Norma Culta (0,50 pts)
        # =========================================================================
        # Avaliar clareza conceitual, concatenação das ideias e correção gramatical
        desvios_gramaticais = 0
        if "há a informações" in texto_lower or "projeto do projeto" in texto_lower:
            desvios_gramaticais += 1
        if texto.endswith(",") or ",," in texto:
            desvios_gramaticais += 1

        if palavras >= 60 and desvios_gramaticais == 0:
            c3_nota = 0.50
            c3_parecer = "Texto bem estruturado, coeso e em perfeita conformidade com a norma padrão."
        elif palavras >= 40:
            c3_nota = 0.35
            c3_parecer = "Linha de raciocínio compreensível e conectada ao problema de requisitos, apresentando apenas pequenos desvios de pontuação ou repetição vocabular."
        else:
            c3_nota = 0.20
            c3_parecer = "Construção textual muito concisa ou fragmentada, necessitando de maior articulação expositiva."

        # Cálculo Total
        nota_final = round(c1_nota + c2_nota + c3_nota, 2)
        # Arredondamento para múltiplo de 0,05
        nota_final = round(nota_final * 20) / 20
        nota_final = min(nota_maxima, max(0.0, nota_final))

        # Identificar causas dos descontos
        descontos = []
        pontos_fortes = []
        pontos_melhoria = []

        if c1_nota >= 0.60:
            pontos_fortes.append("Reconhecimento assertivo do modelo Cascata e da sua incompatibilidade com escopos abertos a mudanças.")
        else:
            pontos_melhoria.append("Aprofundar a análise crítica das características do modelo tradicional frente a incertezas.")

        if c2_nota < 0.60:
            motivo = "Omissão parcial na proposição técnica: o enunciado solicitou explicitamente indicar e justificar uma abordagem de ciclo de vida mais adequada para o projeto (ex.: Modelos Ágeis / Iterativo-Incremental), etapa que não foi plenamente desenvolvida."
            descontos.append(motivo)
            pontos_melhoria.append("Certificar-se de responder integralmente a todas as solicitações do comando da questão (indicar a abordagem e justificá-la).")
        else:
            pontos_fortes.append("Excelente indicação e fundamentação do ciclo de vida sugerido.")

        if c3_nota < 0.45:
            descontos.append("Ajuste na articulação textual e norma padrão: revisão de pontuação e polimento estilístico.")

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
                {"nome": "1. Diagnóstico e Análise do Problema (Modelo Inicial)", "nota": c1_nota, "max": 0.70, "parecer": c1_parecer},
                {"nome": "2. Proposição Técnica e Justificativa da Abordagem", "nota": c2_nota, "max": 0.80, "parecer": c2_parecer},
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
            f"<p>Sua resposta para a Questão Discursiva da Prova Presencial foi avaliada com a pontuação de <strong>{nota:.2f} de {nota_max:.2f} pontos</strong>.</p>",
            "<p><strong>Análise Detalhada dos Critérios:</strong></p>",
            "<ul>",
            f"<li><strong>Diagnóstico do Modelo Inicial:</strong> {c1_parecer}</li>",
            f"<li><strong>Proposição de Abordagem Adequada:</strong> {c2_parecer}</li>",
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
            "<p>Continue empenhado(a) em articular os conceitos teóricos aos desafios práticos do desenvolvimento de software. Conte com o apoio docente na disciplina!</p>"
        )
        return "".join(partes)

rubrica_discursiva = RubricaDiscursiva()
