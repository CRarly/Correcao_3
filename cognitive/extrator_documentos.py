import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List

def extrair_texto_docx(caminho_arquivo: str | Path) -> str:
    """Extrai parágrafos de um arquivo .docx sem depender de bibliotecas externas."""
    try:
        with zipfile.ZipFile(caminho_arquivo) as z:
            xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Namespace padrão do Word
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragrafos = []
            for p in tree.iterfind(".//w:p", ns):
                textos = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                if textos:
                    paragrafos.append("".join(textos))
            return "\n".join(paragrafos).strip()
    except Exception as e:
        return f"[Erro ao extrair DOCX: {e}]"

def extrair_texto_pdf(caminho_arquivo: str | Path) -> str:
    """Extrai texto de um arquivo PDF usando pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(caminho_arquivo))
        textos = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                textos.append(txt.strip())
        return "\n\n".join(textos).strip()
    except Exception as e:
        return f"[Erro ao extrair PDF: {e}]"

def extrair_texto_puro(caminho_arquivo: str | Path) -> str:
    """Lê arquivos de texto puro e código-fonte com fallbacks de codificação."""
    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
    for enc in encodings:
        try:
            with open(caminho_arquivo, "r", encoding=enc, errors="replace") as f:
                return f.read().strip()
        except Exception:
            continue
    return ""

def extrair_texto_zip(caminho_arquivo: str | Path, max_files: int = 10) -> str:
    """Extrai texto de arquivos contidos dentro de um .zip."""
    textos = []
    try:
        with zipfile.ZipFile(caminho_arquivo) as z:
            namelist = z.namelist()[:max_files]
            for name in namelist:
                ext = Path(name).suffix.lower()
                if ext in [".txt", ".py", ".c", ".cpp", ".java", ".sql", ".html", ".css", ".js", ".md"]:
                    try:
                        raw = z.read(name).decode("utf-8", errors="replace")
                        textos.append(f"--- Arquivo no ZIP: {name} ---\n{raw}")
                    except Exception:
                        pass
        return "\n\n".join(textos)
    except Exception as e:
        return f"[Erro ao ler ZIP: {e}]"

def extrair_texto_documento(caminho_arquivo: str | Path) -> Dict[str, Any]:
    """
    Função unificada de extração de conteúdo textual e metadados de submissões.
    Retorna dicionário estruturado com texto, tamanho, contagem de palavras e status.
    """
    path = Path(caminho_arquivo)
    if not path.exists():
        return {
            "sucesso": False,
            "arquivo": path.name,
            "extensao": "",
            "texto": "",
            "palavras": 0,
            "tamanho_bytes": 0,
            "erro": "Arquivo não encontrado."
        }

    ext = path.suffix.lower()
    tamanho = path.stat().st_size
    texto = ""

    if ext == ".docx":
        texto = extrair_texto_docx(path)
    elif ext == ".pdf":
        texto = extrair_texto_pdf(path)
    elif ext == ".zip":
        texto = extrair_texto_zip(path)
    elif ext in [".txt", ".py", ".java", ".c", ".cpp", ".sql", ".html", ".js", ".ts", ".md", ".json", ".csv"]:
        texto = extrair_texto_puro(path)
    else:
        # Tenta ler como texto caso seja arquivo sem extensão ou desconhecido
        texto = extrair_texto_puro(path)

    # Limpeza básica e contagem
    texto_limpo = re.sub(r"\r\n", "\n", texto)
    palavras = len(re.findall(r"\b\w+\b", texto_limpo))

    return {
        "sucesso": bool(texto_limpo and not texto_limpo.startswith("[Erro")),
        "arquivo": path.name,
        "extensao": ext,
        "texto": texto_limpo,
        "palavras": palavras,
        "tamanho_bytes": tamanho,
        "erro": "" if bool(texto_limpo and not texto_limpo.startswith("[Erro")) else texto_limpo
    }

