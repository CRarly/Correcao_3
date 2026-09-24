import re
from typing import Dict, Any, List

def extrair_primeiro_nome(nome_completo: str) -> str:
    """Extrai e capitaliza adequadamente o primeiro nome do estudante."""
    if not nome_completo:
        return "Estudante"
    partes = nome_completo.strip().split()
    if not partes:
        return "Estudante"
    primeiro = partes[0].capitalize()
    # Casos de nomes compostos curtos comuns
    if len(partes) > 1 and partes[0].lower() in ["ana", "maria", "joão", "joao", "luiz", "luis"]:
        segundo = partes[1].capitalize()
        return f"{primeiro} {segundo}"
    return primeiro

class ConstrutorFeedback:
    """
    Construtor de feedbacks pedagógicos humanizados, construtivos e individualizados.
    Garante o uso de {FirstName}, tom de professor especialista e foco nas evidências do envio.
    """

    def gerar_feedback(
        self,
        nome_estudante: str,
        tipo_atividade: str,  # "forum", "atividade_aberta", "prova_presencial"
        diagnostico_pedagogico: Dict[str, Any],
        nome_docente: str = "Prof. Arly Cristopher Nascimento Alves",
        info_plagio: Dict[str, Any] = None,
        usar_token_first_name: bool = True
    ) -> str:
        """
        Gera parecer avaliativo individualizado em formato HTML limpo compatível com o Brightspace TinyMCE.
        Utiliza por padrão a tag de substituição oficial do Brightspace {FirstName}.
        """
        first_name = extrair_primeiro_nome(nome_estudante)
        if info_plagio is None:
            info_plagio = {"tem_plagio": False}

        nota = diagnostico_pedagogico.get("nota_sugerida", 0.0)
        nota_max = diagnostico_pedagogico.get("nota_maxima", 1.0)
        qualidade = diagnostico_pedagogico.get("qualidade_geral", "Bom")
        pontos_fortes = diagnostico_pedagogico.get("pontos_fortes", [])
        pontos_melhoria = diagnostico_pedagogico.get("pontos_melhoria", [])

        paragrafos = []

        # 1. Saudação Nominal com tag oficial {FirstName} do Brightspace
        if usar_token_first_name:
            paragrafos.append("<p>Olá, {FirstName}!</p>")
        else:
            paragrafos.append(f"<p>Olá, <strong>{first_name}</strong>!</p>")

        # 2. Parecer sobre o Envio
        if info_plagio.get("tem_plagio", False):
            sim = info_plagio.get("similaridade_pct", 0.0)
            paragrafos.append(
                f"<p>Ao avaliar sua submissão, foi identificada uma expressiva sobreposição conceitual e textual "
                f"({sim}% de similaridade) com a produção de outro colega da turma. Ressalto que as atividades acadêmicas "
                f"têm como objetivo o desenvolvimento da sua autoria, reflexão crítica e argumentação pessoal. "
                f"Diante dessa constatação, a pontuação foi ajustada em conformidade com as diretrizes institucionais.</p>"
            )
        else:
            if tipo_atividade == "forum":
                if nota >= nota_max * 0.85:
                    paragrafos.append(
                        f"<p>Parabéns pela sua participação no Fórum de Discussão! Sua contribuição demonstrou sólida "
                        f"compreensão da temática proposta, articulando os conceitos com clareza e maturidade acadêmica.</p>"
                    )
                elif nota >= nota_max * 0.6:
                    paragrafos.append(
                        f"<p>Agradeço sua postagem no Fórum. Você trouxe pontos pertinentes sobre o tema central, "
                        f"embora haja espaço para aprofundar ainda mais as conexões teóricas e a interação dialógica com os colegas.</p>"
                    )
                else:
                    paragrafos.append(
                        f"<p>Sua participação no Fórum foi registrada, contudo o conteúdo apresentado foi sucinto ou "
                        f"não contemplou integralmente as instruções solicitadas no enunciado (como o aprofundamento do tema ou a réplica a colegas).</p>"
                    )

            elif tipo_atividade == "atividade_aberta":
                if nota >= nota_max * 0.85:
                    paragrafos.append(
                        f"<p>Excelente trabalho na Atividade Aberta! A entrega atendeu com rigor às diretrizes propostas, "
                        f"apresentando boa estruturação metodológica, fundamentação adequada e domínio do conteúdo.</p>"
                    )
                elif nota >= nota_max * 0.6:
                    paragrafos.append(
                        f"<p>Sua atividade foi avaliada e apresenta uma base interessante sobre o estudo proposto. "
                        f"Recomendo atentar-se aos pontos de detalhamento prático e fundamentação conceitual para enriquecer ainda mais suas análises.</p>"
                    )
                else:
                    paragrafos.append(
                        f"<p>A análise da sua submissão indicou que alguns dos requisitos essenciais do roteiro não foram plenamente "
                        f"desenvolvidos, resultando em uma entrega parcial frente ao que era esperado no enunciado.</p>"
                    )

            elif tipo_atividade == "prova_presencial":
                if nota >= nota_max * 0.85:
                    paragrafos.append(
                        f"<p>Excelente resposta na questão discursiva! Sua argumentação foi precisa, demonstrando domínio "
                        f"técnico e clareza na exposição dos fundamentos solicitados.</p>"
                    )
                elif nota >= nota_max * 0.5:
                    paragrafos.append(
                        f"<p>Sua resposta abordou aspectos centrais da questão, porém careceu de maior aprofundamento "
                        f"ou justificativa técnica em pontos específicos da formulação teórica.</p>"
                    )
                else:
                    paragrafos.append(
                        f"<p>A formulação apresentada ficou aquém do esperado para a questão discursiva, apresentando "
                        f"pouca correlação com o gabarito teórico exigido.</p>"
                    )

        # 3. Destaques Qualitativos e Oportunidades de Aprendizado
        if pontos_fortes and not info_plagio.get("tem_plagio", False):
            bullets_fortes = "".join([f"<li>{pf}</li>" for pf in pontos_fortes[:2]])
            paragrafos.append(f"<p><strong>Pontos de Destaque:</strong><ul>{bullets_fortes}</ul></p>")

        # 4. Justificativa Explícita do Não Atingimento da Totalidade da Nota (Descontos Aplicados)
        motivos_desconto = diagnostico_pedagogico.get("motivos_desconto", [])
        if nota < nota_max and (motivos_desconto or pontos_melhoria):
            motivos_exibir = motivos_desconto if motivos_desconto else pontos_melhoria[:2]
            bullets_desconto = "".join([f"<li>{m}</li>" for m in motivos_exibir])
            paragrafos.append(
                f"<p><strong>Motivos do não atingimento da totalidade da nota ({nota:.2f} de {nota_max:.2f}):</strong>"
                f"<ul>{bullets_desconto}</ul></p>"
            )
        elif pontos_melhoria:
            bullets_melhoria = "".join([f"<li>{pm}</li>" for pm in pontos_melhoria[:2]])
            paragrafos.append(f"<p><strong>Recomendações Construtivas:</strong><ul>{bullets_melhoria}</ul></p>")

        # 5. Encerramento
        paragrafos.append(
            f"<p>Continue se dedicando aos estudos e conte com o apoio docente na sua trajetória acadêmica!</p>"
        )
        primeiro_doc = extrair_primeiro_nome(nome_docente)
        paragrafos.append(f"<p>Atenciosamente, Prof. {primeiro_doc}</p>")

        return "".join(paragrafos)

construtor_feedback = ConstrutorFeedback()


