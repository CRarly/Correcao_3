# Brightspace Grader 2.0 - Módulo Cognitivo
from .extrator_documentos import extrair_texto_documento
from .detector_plagio import detector_plagio
from .analisador_pedagogico import analisador_pedagogico
from .construtor_feedback import construtor_feedback

__all__ = [
    "extrair_texto_documento",
    "detector_plagio",
    "analisador_pedagogico",
    "construtor_feedback"
]

