import os
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
RELATORIOS_DIR = BASE_DIR / "relatorios"
TEMPLATES_DIR = BASE_DIR / "templates"
RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# URLs do AVA Católica / Brightspace
BASE_AVA_URL = "https://ava.catolica.edu.br"
LOGIN_URL = f"{BASE_AVA_URL}/d2l/login"

def get_home_url(ou: str | int) -> str:
    return f"{BASE_AVA_URL}/d2l/home/{ou}"

def get_quickeval_url(ou: str | int) -> str:
    return f"{BASE_AVA_URL}/d2l/le/{ou}/quickeval/"

def get_forums_url(ou: str | int) -> str:
    return f"{BASE_AVA_URL}/d2l/le/{ou}/discussions/List"

def get_dropbox_url(ou: str | int) -> str:
    return f"{BASE_AVA_URL}/d2l/lms/dropbox/admin/folders_manage.d2l?ou={ou}"

def get_quizzes_url(ou: str | int) -> str:
    return f"{BASE_AVA_URL}/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou={ou}"

def get_grades_url(ou: str | int) -> str:
    return f"{BASE_AVA_URL}/d2l/lms/grades/admin/manage/gradeslist.d2l?ou={ou}"

# Nomes de atividades padrão no AVA Católica
FORUM_KEYWORDS = ["Avaliação: Fórum de discussão", "Fórum de discussão", "Fórum Avaliativo"]
ATIVIDADE_KEYWORDS = ["Avaliação: Atividade aberta", "Atividade aberta", "Atividade 3", "Atividade Aberta"]
PROVA_KEYWORDS = ["Avaliação: Prova presencial", "Prova presencial", "Avaliação Presencial"]

# Matriz Curricular Padrão de Pontuações
SCORE_RULES = {
    "2_UNIDADES": {
        "forum": 2.5,
        "atividade_aberta": None,
        "descricao": "Turma com 2 unidades: Fórum vale 2,5 e não há Atividade Aberta."
    },
    "4_UNIDADES": {
        "forum": 1.0,
        "atividade_aberta": 1.5,
        "descricao": "Turma com 4 unidades: Fórum vale 1,0 e Atividade Aberta vale 1,5."
    },
    "PROVA_PRESENCIAL": {
        "discursiva_max": 2.0,
        "descricao": "Prova presencial: Questão discursiva avaliada com nota até 2,0."
    }
}

# Modos de execução suportados
EXECUTION_MODES = {
    "tradicional": "Execução Normal (Novos envios + Auditoria comum)",
    "auditoria": "Auditoria (Verificação de itens já corrigidos)",
    "recorrigir": "Recorrigir + Auditoria Geral (Avaliar e auditar 100% da turma)",
    "auditoria_geral": "Auditoria Geral (Auditar 100% dos alunos da turma)"
}

# Timeout padrão em milissegundos
NAV_TIMEOUT = 45000
DYNAMIC_LOAD_WAIT_MS = 3000

# Porta do servidor Dashboard Web (padrão alterado para 8080 para evitar conflitos)
import socket
DEFAULT_PORT = int(os.getenv("PORT", "8080"))

def find_available_port(start_port: int = DEFAULT_PORT) -> int:
    """Encontra a primeira porta TCP livre a partir de start_port."""
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port


