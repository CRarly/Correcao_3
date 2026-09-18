import re
from typing import Dict, Any, List

class AnalisadorPedagogico:
    """
    Motor pedagógico avançado de avaliação qualitativa e formativa.
    Analisa profundidade conceitual, aderência ao enunciado, coesão textual,
    atendimento às regras e originalidade.
    """

    def avaliar_submissao(
        self,
        tipo_atividade: str,  # "forum", "atividade_aberta", "prova_presencial"
        texto_aluno: str,
        comando_oficial: str,
        nota_maxima: float,
        metadados_envio: Dict[str, Any] = None,
        info_plagio: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Executa avaliação multicritério profunda e devolve pontuação calculada e diagnósticos.
        """
        if metadados_envio is None:
            metadados_envio = {}
        if info_plagio is None:
            info_plagio = {"tem_plagio": False, "similaridade_pct": 0.0}

        texto_limpo = (texto_aluno or "").strip()
        palavras = len(re.findall(r"\b\w+\b", texto_limpo))
        
        # Caso 1: Envio totalmente em branco ou vazio
        arquivos_count = metadados_envio.get("arquivos_count", 0)
        tem_anexos = metadados_envio.get("tem_anexos", False) or arquivos_count > 0

        # Só considera em branco se não houver texto E não houver arquivos anexados
        if palavras < 5 and not tem_anexos:
            return {
                "nota_sugerida": 0.0,
                "nota_maxima": nota_maxima,
                "qualidade_geral": "Insuficiente",
                "aderencia_tema": 0.0,
                "fundamentacao": 0.0,
                "redacao": 0.0,
                "cumprimento_regras": 0.0,
                "pontos_fortes": [],
                "pontos_melhoria": ["Ausência de conteúdo relevante ou envio em branco."],
                "diagnostico_resumido": "Submissão sem conteúdo textual identificável."
            }

        # 1. Análise de Aderência Temática e Palavras-Chave do Enunciado
        tokens_comando = set(re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{4,}\b", (comando_oficial or "").lower()))
        tokens_aluno = set(re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{4,}\b", texto_limpo.lower()))
        
        # Remover stopwords comuns em português para focar no vocabulário conceitual
        stopwords = {
            "para", "com", "como", "pelo", "pela", "onde", "quando", "sobre", "entre",
            "este", "esta", "esses", "essas", "aquele", "aquela", "sendo", "muito", "mais",
            "qual", "quais", "deve", "devem", "aluno", "estudante", "resposta", "atividade",
            "disciplina", "fórum", "discussão", "professor", "unidade", "conteúdo", "questão"
        }
        termos_chave_comando = tokens_comando - stopwords
        
        cobertura_conceitual = 0.7  # Valor base razoável
        if termos_chave_comando:
            intersecao = tokens_aluno & termos_chave_comando
            meta_termos = max(2, min(len(termos_chave_comando) * 0.4, 6))
            razao_cobertura = len(intersecao) / meta_termos
            cobertura_conceitual = min(1.0, max(0.3, razao_cobertura))

        # 2. Análise de Profundidade e Fundamentação
        # Avalia volume reflexivo e presença de conectivos argumentativos
        conectivos_argumentativos = [
            "portanto", "contudo", "todavia", "entretanto", "consequentemente",
            "por conseguinte", "além disso", "em contrapartida", "desta forma",
            "nesse sentido", "assim sendo", "ao passo que", "evidencia-se", "observa-se"
        ]
        num_conectivos = sum(1 for c in conectivos_argumentativos if c in texto_limpo.lower())
        
        if palavras >= 120 and num_conectivos >= 2:
            fundamentacao = 1.0
        elif palavras >= 50 and num_conectivos >= 1:
            fundamentacao = 0.95
        elif palavras >= 50:
            fundamentacao = 0.85
        elif palavras >= 25:
            fundamentacao = 0.75
        elif tem_anexos:
            fundamentacao = 0.85
        else:
            fundamentacao = 0.50

        # 3. Análise Gramatical e Coesão Básica
        erros_grosseiros = 0
        if len(re.findall(r"\b(vc|tb|pq|tbm|pra|oq|blz)\b", texto_limpo.lower())) > 0:
            erros_grosseiros += 1
        
        qualidade_redacao = 1.0 - (erros_grosseiros * 0.15)
        qualidade_redacao = max(0.6, min(1.0, qualidade_redacao))

        # 4. Cumprimento de Regras Operacionais Específicas
        cumprimento_regras = 1.0
        pontos_melhoria = []
        pontos_fortes = []

        if tipo_atividade == "forum":
            posts_count = metadados_envio.get("posts_count", 0)
            replies_count = metadados_envio.get("replies_count", 0)
            total_posts = metadados_envio.get("total_posts", posts_count + replies_count)
            if total_posts == 0 and posts_count == 0:
                total_posts = 1
                posts_count = 1

            # Regra: Se o estudante realizou 2 ou mais postagens no fórum -> participação completa
            if total_posts >= 2 or (posts_count >= 1 and replies_count >= 1):
                pontos_fortes.append("Atendimento completo aos critérios de postagem e interação colaborativa com os colegas.")
                cumprimento_regras = 1.0
            elif total_posts == 1:
                if palavras >= 80:
                    pontos_fortes.append("Contribuição substantiva e reflexiva no debate da turma.")
                    pontos_melhoria.append("Para pontuação máxima integral, recomenda-se complementar com réplica a um colega nos próximos fóruns.")
                    cumprimento_regras = 0.90
                else:
                    pontos_melhoria.append("Participação sucinta no fórum. Recomenda-se maior aprofundamento e interação com os colegas.")
                    cumprimento_regras = 0.80

        elif tipo_atividade == "atividade_aberta":
            arquivos_enviados = metadados_envio.get("arquivos_count", 0) or (1 if tem_anexos else 0)
            if arquivos_enviados > 0:
                pontos_fortes.append("Submissão realizada com envio de arquivo documental correspondente.")
                cumprimento_regras = 1.0
                if palavras < 30:
                    cobertura_conceitual = max(cobertura_conceitual, 0.85)
                    fundamentacao = max(fundamentacao, 0.85)
            else:
                pontos_melhoria.append("Ausência de anexos solicitados.")
                cumprimento_regras = 0.5

        elif tipo_atividade == "prova_presencial":
            if palavras >= 40:
                pontos_fortes.append("Desenvolvimento fundamentado e resposta discursiva estruturada.")
                cumprimento_regras = 1.0
            else:
                pontos_melhoria.append("Resposta excessivamente concisa para uma questão discursiva.")
                cumprimento_regras = 0.7

        # 5. Penalização por Plágio / Cópia (Estritamente >= 90% conforme especificação)
        fator_originalidade = 1.0
        motivos_desconto = []

        if info_plagio.get("tem_plagio", False):
            sim = info_plagio.get("similaridade_pct", 0.0)
            if sim >= 90.0:
                fator_originalidade = 0.0  # Cópia integral (>= 90%) -> nota zero
                motivo = f"Sobreposição textual e conceitual crítica ({sim}%) identificada com trabalho de colega da turma (plágio ≥ 90%)."
                pontos_melhoria.append(motivo)
                motivos_desconto.append(motivo)

        # 6. Cálculo da Nota Ponderada
        # Pesos: Aderência (35%), Fundamentação (35%), Regras (15%), Redação (15%)
        score_base = (
            cobertura_conceitual * 0.35 +
            fundamentacao * 0.35 +
            cumprimento_regras * 0.15 +
            qualidade_redacao * 0.15
        )

        score_ajustado = score_base * fator_originalidade
        nota_calculada = round(nota_maxima * score_ajustado, 2)
        
        # Arredondamento pedagógico inteligente (múltiplos de 0.05)
        nota_calculada = round(nota_calculada * 20) / 20
        nota_calculada = min(nota_maxima, max(0.0, nota_calculada))

        # 7. Mapeamento explícito das causas do não atingimento da nota máxima
        if nota_calculada < nota_maxima and not info_plagio.get("tem_plagio", False):
            if cobertura_conceitual < 0.75:
                motivos_desconto.append(
                    "Abordagem conceitual parcial: os termos teóricos e conceitos centrais solicitados no enunciado não foram plenamente explorados."
                )
            if fundamentacao < 0.80:
                motivos_desconto.append(
                    "Profundidade analítica aquém do esperado: argumentação concisa, com necessidade de maior fundamentação técnica e exemplos contextualizados."
                )
            if cumprimento_regras < 1.0:
                if tipo_atividade == "forum":
                    motivos_desconto.append(
                        "Participação incompleta nas regras do fórum: envio de apenas 1 postagem, sem realização de réplica dialógica a postagens de colegas."
                    )
                elif tipo_atividade == "atividade_aberta":
                    motivos_desconto.append(
                        "Não atendimento integral das etapas do roteiro de entrega ou desenvolvimento parcial da atividade prática."
                    )
                elif tipo_atividade == "prova_presencial":
                    motivos_desconto.append(
                        "Resposta discursiva excessivamente sucinta, deixando de detalhar os fundamentos solicitados na questão."
                    )
            if qualidade_redacao < 0.80:
                motivos_desconto.append(
                    "Aspectos formais de redação acadêmica: identificada necessidade de maior coesão textual e adequação à norma padrão."
                )
            # Garantia de justificativa pedagógica explícita quando houver desconto (mesmo sutil)
            if not motivos_desconto:
                if pontos_melhoria:
                    motivos_desconto.extend(pontos_melhoria[:2])
                elif cobertura_conceitual < 0.95:
                    motivos_desconto.append(
                        "Aprofundamento conceitual: para pontuação máxima integral (100%), explore com maior amplitude teórica e correlação prática todos os conceitos solicitados no tema."
                    )
                elif fundamentacao < 0.95:
                    motivos_desconto.append(
                        "Detalhamento analítico complementar: para pontuação máxima integral (100%), apresente justificativas técnicas e conexões conceituais ainda mais exaustivas."
                    )
                elif qualidade_redacao < 0.95:
                    motivos_desconto.append(
                        "Polimento de redação acadêmica: pequenos ajustes na estrutura argumentativa e formalidade textual para alcançar a totalidade da nota."
                    )
                else:
                    motivos_desconto.append(
                        "Ajuste qualitativo ponderado na distribuição dos critérios avaliativos para alcance pleno da pontuação máxima."
                    )

        # Adicionar pontos fortes adicionais
        if cobertura_conceitual >= 0.8:
            pontos_fortes.append("Demonstrou domínio terminológico e contextualização clara dos tópicos exigidos.")
        if fundamentacao >= 0.85:
            pontos_fortes.append("Argumentação consistente, com encadeamento lógico de ideias.")

        qualidade_geral = "Excelente" if score_base >= 0.85 else "Bom" if score_base >= 0.70 else "Regular" if score_base >= 0.50 else "Insuficiente"

        return {
            "nota_sugerida": nota_calculada,
            "nota_maxima": nota_maxima,
            "qualidade_geral": qualidade_geral,
            "aderencia_tema": round(cobertura_conceitual, 2),
            "fundamentacao": round(fundamentacao, 2),
            "redacao": round(qualidade_redacao, 2),
            "cumprimento_regras": round(cumprimento_regras, 2),
            "originalidade": round(fator_originalidade, 2),
            "pontos_fortes": pontos_fortes,
            "pontos_melhoria": pontos_melhoria,
            "motivos_desconto": motivos_desconto,
            "diagnostico_resumido": f"Conceito {qualidade_geral} - Nota: {nota_calculada}/{nota_maxima}"
        }

analisador_pedagogico = AnalisadorPedagogico()
