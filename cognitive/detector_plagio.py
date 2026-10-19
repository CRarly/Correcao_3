import re
import difflib
import unicodedata
from typing import List, Dict, Any, Optional

def normalizar_texto(texto: str) -> str:
    """Remove acentos, pontuações excessivas e converte para minúsculas."""
    if not texto:
        return ""
    # Normalizar unicode (NFD -> remover diacríticos)
    nfkd = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    # Substituir quebras de linha e múltiplos espaços
    limpo = re.sub(r"[^\w\s]", " ", sem_acento)
    return re.sub(r"\s+", " ", limpo).strip()

def extrair_ngrams(tokens: List[str], n: int = 4) -> set:
    """Extrai n-gramas de uma lista de tokens."""
    if len(tokens) < n:
        return set([" ".join(tokens)])
    return set(" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1))

from pathlib import Path
from config import RELATORIOS_DIR

class DetectorPlagio:
    """
    Detector de similaridade e plágio cruzado entre submissões de estudantes.
    Mapeia turmas e atividades, detectando cópias diretas e paráfrases.
    Regra estrita: Considera plágio apenas similaridades a partir de 90.0%.
    Ignora nomes de arquivo e compara exclusivamente o conteúdo textual extraído.
    Gera relatório detalhado de comparação lado a lado para submissões suspeitas.
    """
    def __init__(self, limiar_alerta: float = 0.90, limiar_critico: float = 0.90):
        self.limiar_alerta = limiar_alerta
        self.limiar_critico = limiar_critico
        # Estrutura: { f"{ou}_{atividade}": [ { "aluno": str, "texto_original": str, "texto_norm": str, "tokens": list, "timestamp": str, "ordem": int }, ... ] }
        self.banco_submissoes: Dict[str, List[Dict[str, Any]]] = {}
        # Histórico de plágios detectados
        self.ocorrencias_plagio: List[Dict[str, Any]] = []

    def limpar_turma(self, ou: str | int, atividade: str):
        chave = f"{ou}_{atividade}"
        if chave in self.banco_submissoes:
            del self.banco_submissoes[chave]

    def registrar_e_comparar(
        self,
        ou: str | int,
        disciplina: str,
        atividade: str,
        aluno_nome: str,
        texto_submissao: str,
        timestamp: str = ""
    ) -> Dict[str, Any]:
        """
        Registra a submissão e compara com todas as anteriores da mesma turma e atividade.
        Regra: Apenas >= 90% é considerado plágio. Nome de arquivo é ignorado (só conteúdo).
        Gera comparação direta lado a lado para casos suspeitos/plagiados.
        """
        chave = f"{ou}_{atividade}"
        if chave not in self.banco_submissoes:
            self.banco_submissoes[chave] = []

        submissoes_turma = self.banco_submissoes[chave]
        texto_norm = normalizar_texto(texto_submissao)
        tokens = texto_norm.split()

        # Ignorar submissões vazias ou minúsculas (menos de 15 palavras)
        if len(tokens) < 15:
            self.banco_submissoes[chave].append({
                "aluno": aluno_nome,
                "texto_original": texto_submissao,
                "texto_norm": texto_norm,
                "tokens": tokens,
                "timestamp": timestamp,
                "ordem": len(submissoes_turma) + 1
            })
            return {
                "tem_plagio": False,
                "similaridade_pct": 0.0,
                "aluno_autor": None,
                "aluno_copiador": aluno_nome,
                "trechos_copiados": [],
                "relatorio_comparacao": None,
                "diagnostico": "Texto insuficiente para análise comparativa."
            }

        ngrams_atual = extrair_ngrams(tokens, n=4)

        maior_similaridade = 0.0
        aluno_similar = None
        texto_similar = ""
        trechos_copiados = []

        for sub in submissoes_turma:
            if sub["aluno"].strip().lower() == aluno_nome.strip().lower():
                continue # Não comparar com ele mesmo

            ngrams_outro = extrair_ngrams(sub["tokens"], n=4)
            uniao = len(ngrams_atual | ngrams_outro)
            if uniao == 0:
                continue

            # Similaridade de Jaccard dos 4-gramas
            jaccard = len(ngrams_atual & ngrams_outro) / uniao

            # Verificação com difflib se Jaccard indicar relevância
            if jaccard > 0.35:
                matcher = difflib.SequenceMatcher(None, texto_norm, sub["texto_norm"])
                ratio = matcher.ratio()
                sim_final = max(jaccard, ratio)
            else:
                sim_final = jaccard

            if sim_final > maior_similaridade:
                maior_similaridade = sim_final
                aluno_similar = sub["aluno"]
                texto_similar = sub["texto_original"]

        # Estritamente >= 90% conforme especificação do usuário
        tem_plagio = round(maior_similaridade * 100, 1) >= 90.0
        similaridade_pct = round(maior_similaridade * 100, 1)
        relatorio_comp_path = None

        if tem_plagio and aluno_similar:
            # Extrair blocos idênticos contínuos relevantes
            matcher = difflib.SequenceMatcher(None, texto_submissao, texto_similar)
            blocos = matcher.get_matching_blocks()
            for b in blocos:
                if b.size >= 40:  # Trecho contínuo com 40+ caracteres
                    trecho = texto_submissao[b.a:b.a + b.size].strip()
                    if trecho and len(trecho) > 20:
                        trechos_copiados.append(trecho[:250])

            # Gerar comparação direta entre os dois conteúdos/arquivos
            relatorio_comp_path = self.gerar_comparacao_arquivos(
                ou=ou,
                disciplina=disciplina,
                atividade=atividade,
                aluno_copiador=aluno_nome,
                aluno_autor=aluno_similar,
                texto_copiador=texto_submissao,
                texto_autor=texto_similar,
                similaridade_pct=similaridade_pct
            )

            ocorrencia = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": atividade,
                "aluno_copiador": aluno_nome,
                "aluno_autor": aluno_similar,
                "similaridade_pct": similaridade_pct,
                "trechos_copiados": trechos_copiados[:5],
                "relatorio_comparacao": str(relatorio_comp_path) if relatorio_comp_path else None,
                "nivel": "CRÍTICO (>= 90%)"
            }
            self.ocorrencias_plagio.append(ocorrencia)

        # Adicionar esta submissão ao banco
        self.banco_submissoes[chave].append({
            "aluno": aluno_nome,
            "texto_original": texto_submissao,
            "texto_norm": texto_norm,
            "tokens": tokens,
            "timestamp": timestamp,
            "ordem": len(submissoes_turma) + 1
        })

        return {
            "tem_plagio": tem_plagio,
            "similaridade_pct": similaridade_pct,
            "aluno_autor": aluno_similar if tem_plagio else None,
            "aluno_copiador": aluno_nome,
            "trechos_copiados": trechos_copiados[:3],
            "relatorio_comparacao": str(relatorio_comp_path) if relatorio_comp_path else None,
            "diagnostico": f"Similaridade de {similaridade_pct}% (>= 90%) com submissão de {aluno_similar}. Relatório comparativo gerado." if tem_plagio else "Originalidade verificada sem indícios de cópia (inferior a 90%)."
        }

    def gerar_comparacao_arquivos(
        self,
        ou: str | int,
        disciplina: str,
        atividade: str,
        aluno_copiador: str,
        aluno_autor: str,
        texto_copiador: str,
        texto_autor: str,
        similaridade_pct: float
    ) -> Optional[Path]:
        """
        Compara o conteúdo textual de um arquivo/envio suspeito diretamente com o suposto plagiado.
        Gera relatório HTML visual lado a lado (Side-by-Side Diff) e texto resumido.
        """
        try:
            plagios_dir = RELATORIOS_DIR / "plagios"
            plagios_dir.mkdir(parents=True, exist_ok=True)

            nome_cop_slug = re.sub(r'[^a-zA-Z0-9]', '_', aluno_copiador.strip().lower())
            nome_aut_slug = re.sub(r'[^a-zA-Z0-9]', '_', aluno_autor.strip().lower())
            arquivo_html = plagios_dir / f"comparacao_plagio_{ou}_{nome_cop_slug}_vs_{nome_aut_slug}.html"

            # Quebrar em linhas para o diff
            linhas_autor = texto_autor.splitlines(keepends=True)
            linhas_copiador = texto_copiador.splitlines(keepends=True)

            differ = difflib.HtmlDiff(wrapcolumn=65)
            tabela_diff = differ.make_table(
                linhas_autor,
                linhas_copiador,
                fromdesc=f"Original: {aluno_autor}",
                todesc=f"Suspeito: {aluno_copiador} ({similaridade_pct}% de similaridade)",
                context=True,
                numlines=3
            )

            html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Comparação de Plágio: {aluno_copiador} vs {aluno_autor}</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 24px; background: #f8f9fa; color: #333; }}
  .header {{ background: #fff; padding: 20px; border-radius: 8px; border-left: 6px solid #d32f2f; box-shadow: 0 2px 6px rgba(0,0,0,0.08); margin-bottom: 20px; }}
  h2 {{ margin: 0 0 10px 0; color: #b71c1c; }}
  .meta {{ font-size: 14px; color: #555; line-height: 1.6; }}
  .badge {{ background: #d32f2f; color: white; padding: 4px 10px; border-radius: 12px; font-weight: bold; }}
  table.diff {{ border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.08); font-size: 13px; font-family: Consolas, monospace; }}
  table.diff td, table.diff th {{ padding: 6px 10px; border: 1px solid #e0e0e0; vertical-align: top; }}
  .diff_header {{ background: #eceff1; font-weight: bold; text-align: center; }}
  .diff_add {{ background: #c8e6c9; }}
  .diff_chg {{ background: #fff9c4; }}
  .diff_sub {{ background: #ffcdd2; }}
</style>
</head>
<body>
  <div class="header">
    <h2>Relatório Comparativo de Suspeita de Plágio (≥ 90%)</h2>
    <div class="meta">
      <strong>Disciplina:</strong> [{ou}] {disciplina}<br>
      <strong>Atividade:</strong> {atividade}<br>
      <strong>Aluno Suspeito (Copiador):</strong> {aluno_copiador} <span class="badge">{similaridade_pct}% SIMILAR</span><br>
      <strong>Aluno Referência (Autor Anterior):</strong> {aluno_autor}<br>
      <em>Nota: A comparação avalia exclusivamente o conteúdo textual interno extraído, desconsiderando completamente nomes de arquivos.</em>
    </div>
  </div>
  <h3>Comparação Detalhada Lado a Lado:</h3>
  {tabela_diff}
</body>
</html>"""

            arquivo_html.write_text(html_content, encoding="utf-8")
            return arquivo_html
        except Exception as e:
            return None

    def listar_plagios_disciplina(self, ou: str | int) -> List[Dict[str, Any]]:
        return [p for p in self.ocorrencias_plagio if p["ou"] == str(ou)]

detector_plagio = DetectorPlagio()
