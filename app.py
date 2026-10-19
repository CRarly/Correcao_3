import os
import sys
import json
import threading
import webbrowser
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

# Suporte UTF-8 no Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import BASE_DIR, TEMPLATES_DIR, RELATORIOS_DIR
from engine_state import state
from core.discovery import descobrir_todas_abas_e_cursos
from core.browser_session import BrowserSession
from core.inspector_disciplina import inspector_disciplina
from core.orquestrador import orquestrador
from core.motor_discursivas import motor_discursivas
from core.motor_atividades_novo import motor_atividades_novo

app = FastAPI(title="Brightspace Grader 3.0")

class DiscoverRequest(BaseModel):
    username: str
    password: str
    headless: bool = True

class InspectRequest(BaseModel):
    username: str
    password: str
    ou: str
    nome: str
    headless: bool = True

class StartRequest(BaseModel):
    username: str
    password: str
    disciplinas: List[Dict[str, Any]]
    atividades: List[str]
    modo: str = "tradicional"
    headless: bool = True

class DiscursivaInspectRequest(BaseModel):
    username: str
    password: str
    ou: str
    nome: str = ""
    headless: bool = True
    tipo_prova: str = "presencial"

class DiscursivaStartRequest(BaseModel):
    username: str
    password: str
    ou: str
    nome: str = ""
    modo: str = "tradicional"
    docente: str = "Prof. Avaliador"
    headless: bool = True
    enunciado_override: str = ""
    valor_maximo_override: float = 2.0
    tipo_prova: str = "presencial"

class AtividadeInspectRequest(BaseModel):
    username: str
    password: str
    ou: str
    nome: str = ""
    headless: bool = True

class AtividadeStartRequest(BaseModel):
    username: str
    password: str
    ou: str
    nome: str = ""
    modo: str = "tradicional"
    docente: str = "Prof. Arly Cristopher Nascimento Alves"
    headless: bool = True

@app.get("/", response_class=HTMLResponse)
def get_index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html não encontrado")
    return index_file.read_text(encoding="utf-8")

@app.post("/api/discover")
def api_discover(req: DiscoverRequest):
    try:
        dados = descobrir_todas_abas_e_cursos(req.username, req.password, headless=req.headless)
        return dados
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inspect")
def api_inspect(req: InspectRequest):
    session = BrowserSession(username=req.username, password=req.password, headless=req.headless)
    temp_dir = BASE_DIR / f"temp_downloads_{req.ou}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        page = session.iniciar()
        plano = inspector_disciplina.inspecionar(page, req.ou, req.nome, temp_dir)
        return plano
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.fechar()
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/api/start")
def api_start(req: StartRequest):
    if state.is_running:
        raise HTTPException(status_code=400, detail="Uma execução já está em andamento.")

    def run_worker():
        orquestrador.executar(
            username=req.username,
            password=req.password,
            disciplinas=req.disciplinas,
            atividades_selecionadas=req.atividades,
            modo=req.modo,
            headless=req.headless
        )

    t = threading.Thread(target=run_worker, daemon=True)
    t.start()
    return {"status": "iniciado", "total_turmas": len(req.disciplinas)}

@app.post("/api/stop")
def api_stop():
    orquestrador.abortar()
    return {"status": "parada_executada"}

@app.get("/api/status")
def api_status():
    return state.to_dict()

@app.get("/api/relatorios")
def api_listar_relatorios():
    caminho_idx = RELATORIOS_DIR / "index_relatorios.json"
    if not caminho_idx.exists():
        return []
    try:
        with open(caminho_idx, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

@app.get("/api/relatorios/{report_id}")
def api_obter_relatorio(report_id: str):
    caminho = RELATORIOS_DIR / f"relatorio_correcoes_{report_id}.json"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/relatorios/{report_id}/csv")
def api_baixar_csv(report_id: str):
    caminho = RELATORIOS_DIR / f"relatorio_correcoes_{report_id}.csv"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo CSV não encontrado")
    return FileResponse(caminho, media_type="text/csv", filename=f"relatorio_{report_id}.csv")

# =============================================================================
# ENDPOINTS DO MOTOR UNIVERSAL DE PROVAS DISCURSIVAS
# =============================================================================
@app.post("/api/discursivas/inspecionar")
def api_discursivas_inspecionar(req: DiscursivaInspectRequest):
    session = BrowserSession(username=req.username, password=req.password, headless=req.headless)
    try:
        page = session.iniciar()
        info = motor_discursivas.inspecionar_questao_discursiva(page, req.ou, req.nome, tipo_prova=req.tipo_prova)
        criterios = motor_discursivas.gerar_criterios_avaliacao(info.get("enunciado", ""), info.get("valor_maximo", 2.0))
        exemplo = motor_discursivas.gerar_exemplo_resposta(info.get("enunciado", ""), criterios)
        return {
            "status": "sucesso",
            "info": info,
            "criterios": criterios,
            "exemplo": exemplo
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.fechar()

@app.post("/api/discursivas/iniciar")
def api_discursivas_iniciar(req: DiscursivaStartRequest):
    if state.is_running:
        raise HTTPException(status_code=400, detail="Uma execução já está em andamento.")

    def run_discursivas_worker():
        session = BrowserSession(username=req.username, password=req.password, headless=req.headless)
        try:
            state.is_running = True
            state.should_stop = False
            state.reset_stats()
            tipo_label = "Substitutiva" if str(req.tipo_prova).lower() == "substitutiva" else "Presencial"
            state.current_stage = f"Iniciando Provas Discursivas ({tipo_label}): {req.nome or req.ou}"
            page = session.iniciar()
            motor_discursivas.executar_turma(
                page=page,
                ou=req.ou,
                disciplina=req.nome or f"Turma {req.ou}",
                modo=req.modo,
                docente=req.docente,
                enunciado_override=req.enunciado_override,
                valor_maximo_override=req.valor_maximo_override,
                tipo_prova=req.tipo_prova
            )
        except Exception as e:
            state.log(f"Erro na execução de discursivas: {e}", "ERROR")
            import traceback
            state.log(traceback.format_exc(), "ERROR")
        finally:
            session.fechar()
            state.is_running = False
            state.current_stage = "Concluído"

    t = threading.Thread(target=run_discursivas_worker, daemon=True)
    t.start()
    return {"status": "iniciado", "ou": req.ou}

@app.get("/api/discursivas/auditoria/{ou}")
def api_discursivas_auditoria(ou: str):
    arquivos = list(RELATORIOS_DIR.glob(f"auditoria_coerencia_discursivas_{ou}_*.json"))
    arquivos += list(RELATORIOS_DIR.glob(f"auditoria_coerencia_substitutiva_{ou}_*.json"))
    if not arquivos:
        raise HTTPException(status_code=404, detail="Nenhuma auditoria encontrada para esta turma.")
    arquivos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    try:
        with open(arquivos[0], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ENDPOINTS DO MOTOR DE ATIVIDADES ABERTAS
# =============================================================================
@app.post("/api/atividades/inspecionar")
def api_atividades_inspecionar(req: AtividadeInspectRequest):
    nome_limpo = "" if str(req.nome).lower() in ["undefined", "null", "none", ""] else req.nome.strip()
    session = BrowserSession(username=req.username, password=req.password, headless=req.headless)
    try:
        page = session.iniciar()
        info = motor_atividades_novo.inspecionar_atividade_aberta(page, req.ou, nome_limpo)
        rubrica = motor_atividades_novo.gerar_matriz_rubrica(info["enunciado"], info["valor_maximo"], info["tipologia"])
        return {
            "status": "sucesso",
            "info": info,
            "rubrica": rubrica
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.fechar()

@app.post("/api/atividades/iniciar")
def api_atividades_iniciar(req: AtividadeStartRequest):
    if state.is_running:
        raise HTTPException(status_code=400, detail="Uma execução já está em andamento.")

    nome_limpo = "" if str(req.nome).lower() in ["undefined", "null", "none", ""] else req.nome.strip()

    def run_atividades_worker():
        session = BrowserSession(username=req.username, password=req.password, headless=req.headless)
        try:
            state.is_running = True
            state.should_stop = False
            state.reset_stats()
            state.current_stage = f"Iniciando Atividades Abertas: {nome_limpo or req.ou}"
            page = session.iniciar()
            motor_atividades_novo.executar_turma(
                page=page,
                ou=req.ou,
                nome_disciplina=nome_limpo or f"Turma {req.ou}",
                modo=req.modo,
                docente=req.docente
            )
        except Exception as e:
            state.log(f"Erro na execução de atividades abertas: {e}", "ERROR")
            import traceback
            state.log(traceback.format_exc(), "ERROR")
        finally:
            session.fechar()
            state.is_running = False
            state.current_stage = "Concluído"

    t = threading.Thread(target=run_atividades_worker, daemon=True)
    t.start()
    return {"status": "iniciado", "ou": req.ou}

@app.get("/api/atividades/auditoria/{ou}")
def api_atividades_auditoria(ou: str):
    arquivos = list(RELATORIOS_DIR.glob(f"auditoria_atividades_abertas_{ou}_*.json"))
    if not arquivos:
        raise HTTPException(status_code=404, detail="Nenhuma auditoria encontrada para esta turma.")
    arquivos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    try:
        with open(arquivos[0], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    from config import DEFAULT_PORT, find_available_port
    port = find_available_port(DEFAULT_PORT)
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
