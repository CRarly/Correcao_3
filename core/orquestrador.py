import os
import shutil
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import RELATORIOS_DIR, BASE_DIR
from engine_state import state
from core.browser_session import BrowserSession
from core.inspector_disciplina import inspector_disciplina
from core.motor_foruns import motor_foruns
from core.motor_atividades import motor_atividades
from core.motor_provas import motor_provas
from core.motor_discursivas import motor_discursivas
from cognitive.detector_plagio import detector_plagio

class OrquestradorCorrecoes:
    """
    Orquestrador mestre do Brightspace Grader 2.0.
    Coordena as 4 fases do ciclo:
    1. Pré-inspeção e geração do plano de apoio
    2. Execução seletiva dos motores (Fórum, Atividade Aberta, Prova Presencial)
    3. Persistência de relatórios consolidados em relatorios/
    4. Limpeza e expurgo total de arquivos temporários
    """

    def __init__(self):
        self.active_session: Optional[BrowserSession] = None

    def abortar(self):
        """Interrompe a execução imediatamente e fecha o navegador de fato."""
        state.request_stop()
        state.current_stage = "Interrompendo Execução"
        state.log("Interrupção solicitada: finalizando sessões ativas...", "WARN")
        BrowserSession.abortar_sessao_ativa()
        if self.active_session:
            try:
                self.active_session.abortar()
            except Exception:
                pass
            self.active_session = None
        state.is_running = False
        state.current_stage = "Execução Parada"
        state.log("Execução encerrada de fato com sucesso.", "WARN")

    def executar(
        self,
        username: str,
        password: str,
        disciplinas: List[Dict[str, Any]],
        atividades_selecionadas: List[str],  # ["forum", "atividade_aberta", "prova_presencial"]
        modo: str = "tradicional",           # "tradicional", "auditoria", "recorrigir", "auditoria_geral"
        headless: bool = True
    ) -> Dict[str, Any]:
        state.reset()
        state.is_running = True
        state.current_mode = modo
        state.current_stage = "Inicializando Sessão"
        state.log(f"Iniciando Brightspace Grader 2.0 - {len(disciplinas)} disciplina(s) na fila...")
        state.log(f"Modo: {modo.upper()} | Atividades: {', '.join(atividades_selecionadas)}")

        session = BrowserSession(username=username, password=password, headless=headless)
        self.active_session = session
        todos_resultados = []
        relatorio_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            page = session.iniciar()
            docente = session.nome_docente

            for idx, disc in enumerate(disciplinas, start=1):
                if state.should_stop:
                    state.log("Execução interrompida a pedido do usuário.", "WARN")
                    break

                ou = str(disc.get("ou", ""))
                nome_disc = disc.get("name", f"Disciplina {ou}")
                state.current_discipline = nome_disc
                state.current_ou = ou
                state.current_stage = f"Processando [{idx}/{len(disciplinas)}]: {nome_disc}"
                state.log(f"\n=======================================================")
                state.log(f"[{idx}/{len(disciplinas)}] INICIANDO DISCIPLINA: {nome_disc} (OU: {ou})")
                state.log(f"=======================================================")

                # Criar pasta temporária isolada para a disciplina
                temp_dir = BASE_DIR / f"temp_downloads_{ou}"
                temp_dir.mkdir(parents=True, exist_ok=True)

                try:
                    # FASE 1: Pré-inspeção e geração de apoio
                    state.current_stage = f"Pré-Inspeção: {nome_disc}"
                    plano = inspector_disciplina.inspecionar(page, ou, nome_disc, temp_dir)

                    # FASE 2: Executar Fórum se solicitado e ativo
                    if "forum" in atividades_selecionadas and plano.get("forum", {}).get("ativo", False):
                        state.current_stage = f"Avaliando Fórum: {nome_disc}"
                        res_forum = motor_foruns.executar(page, ou, nome_disc, modo, plano, docente)
                        todos_resultados.extend(res_forum)

                    # FASE 3: Executar Atividade Aberta se solicitada e ativa
                    if "atividade_aberta" in atividades_selecionadas and plano.get("atividade_aberta", {}).get("ativa", False):
                        state.current_stage = f"Avaliando Atividade Aberta: {nome_disc}"
                        res_ativ = motor_atividades.executar(page, ou, nome_disc, modo, plano, docente, temp_dir)
                        todos_resultados.extend(res_ativ)

                    # FASE 4: Executar Prova Presencial (Discursivas) com o [NOVO MOTOR DE CORREÇÃO] se solicitada
                    if "prova_presencial" in atividades_selecionadas:
                        state.current_stage = f"Avaliando Prova Presencial [Novo Motor de Correção]: {nome_disc}"
                        state.log(f"\n=======================================================")
                        state.log(f"[NOVO MOTOR DE CORREÇÃO] Iniciando Prova Presencial (Discursivas): {nome_disc}")
                        state.log(f"=======================================================")
                        res_prova = motor_discursivas.executar_turma(page, ou, nome_disc, modo, docente)
                        todos_resultados.extend(res_prova)

                    state.increment_stat("disciplinas_processadas")

                finally:
                    # REQUISITO 11: Expurgo de arquivos temporários e limpeza de ambiente
                    state.log(f"Limpando arquivos temporários da disciplina {ou}...")
                    if temp_dir.exists():
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            state.log(f"Diretório temporário {temp_dir.name} removido com sucesso.")
                        except Exception as e:
                            state.log(f"Aviso ao remover temporários: {e}", "WARN")

            # Salvar Relatórios Consolidados em relatorios/
            arquivos_gerados = self._persistir_relatorio(relatorio_id, todos_resultados, modo, docente)
            state.current_stage = "Concluído"
            state.log(f"\nCiclo finalizado! Relatório salvo em: {arquivos_gerados.get('json', '')}")

        except Exception as e:
            if state.should_stop or "closed" in str(e).lower():
                state.log("Execução interrompida de fato por comando do usuário.", "WARN")
                state.current_stage = "Execução Parada"
            else:
                state.log(f"Erro crítico durante a execução do orquestrador: {e}", "ERROR")
                import traceback
                state.log(traceback.format_exc(), "ERROR")
        finally:
            try:
                session.fechar()
            except Exception:
                pass
            self.active_session = None
            state.is_running = False
            if state.should_stop:
                state.current_stage = "Execução Parada"

        return {
            "relatorio_id": relatorio_id,
            "total_avaliados": len(todos_resultados),
            "estatisticas": state.statistics
        }

    def _persistir_relatorio(
        self,
        relatorio_id: str,
        resultados: List[Dict[str, Any]],
        modo: str,
        docente: str
    ) -> Dict[str, str]:
        caminho_json = RELATORIOS_DIR / f"relatorio_correcoes_{relatorio_id}.json"
        caminho_csv = RELATORIOS_DIR / f"relatorio_correcoes_{relatorio_id}.csv"

        dados_completos = {
            "id": relatorio_id,
            "data_execucao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "modo": modo,
            "docente": docente,
            "total_registros": len(resultados),
            "plagios_detectados": detector_plagio.ocorrencias_plagio,
            "itens": resultados
        }

        # Salvar JSON
        with open(caminho_json, "w", encoding="utf-8") as f:
            json.dump(dados_completos, f, ensure_ascii=False, indent=2)

        # Salvar CSV
        campos = ["ou", "disciplina", "atividade", "aluno", "nota", "nota_max", "plagio", "similaridade_pct", "qualidade", "modo"]
        with open(caminho_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            for item in resultados:
                writer.writerow({k: item.get(k, "") for k in campos})

        # Atualizar índice mestre de relatórios
        self._atualizar_indice_relatorios(dados_completos)

        return {"json": str(caminho_json), "csv": str(caminho_csv)}

    def _atualizar_indice_relatorios(self, meta: Dict[str, Any]):
        caminho_idx = RELATORIOS_DIR / "index_relatorios.json"
        lista = []
        if caminho_idx.exists():
            try:
                with open(caminho_idx, "r", encoding="utf-8") as f:
                    lista = json.load(f)
            except Exception:
                lista = []

        resumo = {
            "id": meta["id"],
            "data": meta["data_execucao"],
            "modo": meta["modo"],
            "docente": meta["docente"],
            "total": meta["total_registros"],
            "plagios": len(meta["plagios_detectados"]),
            "arquivo_json": f"relatorio_correcoes_{meta['id']}.json",
            "arquivo_csv": f"relatorio_correcoes_{meta['id']}.csv"
        }
        # Inserir no topo (mais recente primeiro)
        lista.insert(0, resumo)

        with open(caminho_idx, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)

orquestrador = OrquestradorCorrecoes()

