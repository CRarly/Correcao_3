import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from core.browser_session import obter_primeiro_nome_docente
from core.motor_foruns import motor_foruns
from core.motor_atividades import motor_atividades
from core.dom_helpers import remover_nota_e_feedback_consistent_evaluation

print("=== 1. TESTANDO EXTRAÇÃO DE PRIMEIRO NOME DO DOCENTE ===")
testes_docente = [
    ("Prof. LUIZ GUSTAVO DOS SANTOS", "Luiz"),
    ("Prof. Arly Cristopher Nascimento Alves", "Arly"),
    ("Profa. Maria Helena", "Maria Helena"),
    ("Prof. João Silva", "João Silva"),
    ("Prof. Avaliador", "Avaliador"),
    ("Carlos Drummond", "Carlos"),
    ("", "Avaliador")
]
for doc_in, esperado in testes_docente:
    obtido = obter_primeiro_nome_docente(doc_in)
    assert obtido == esperado, f"Erro: {doc_in} -> esperado {esperado}, obtido {obtido}"
    print(f"  OK: '{doc_in}' -> '{obtido}' (Assinatura: 'Atenciosamente, Prof. {obtido}')")

print("\n=== 2. TESTANDO FEEDBACK DE FÓRUM (MOTOR_FORUNS) ===")
# 2.1 Feedback normal com postagem
res_forum = motor_foruns.avaliar_estudante_forum(
    post_principal="O planejamento educacional no ensino fundamental articula as diretrizes curriculares nacionais com as práticas pedagógicas contemporâneas, portanto promovendo uma aprendizagem significativa.",
    comentarios=["Concordo plenamente com a perspectiva do colega sobre as diretrizes."],
    nome_aluno="Carlos Souza",
    comando="Discuta o planejamento educacional no ensino fundamental articulando diretrizes curriculares e práticas pedagógicas.",
    criterios_info={"exige_comentarios": True, "peso_post_principal": 0.5, "peso_comentarios": 0.5},
    nota_maxima=1.0,
    docente="Prof. LUIZ GUSTAVO DOS SANTOS"
)
fb_forum = res_forum["feedback_html"]
assert "<p>Olá, {FirstName}!</p>" in fb_forum, f"Faltou saudação: {fb_forum}"
assert "<p>Atenciosamente, Prof. Luiz</p>" in fb_forum, f"Faltou assinatura: {fb_forum}"
print("  OK: Feedback normal de Fórum possui 'Olá, {FirstName}!' e 'Atenciosamente, Prof. Luiz'")

# 2.2 Feedback fórum zerado (is_vazio)
res_forum_zero = motor_foruns.avaliar_estudante_forum(
    post_principal="-Nenhum texto inserido-",
    comentarios=[],
    nome_aluno="Beatriz Lima",
    comando="Discuta o planejamento educacional.",
    criterios_info={},
    nota_maxima=1.0,
    docente="Prof. Arly Cristopher Nascimento Alves"
)
fb_f_zero = res_forum_zero["feedback_html"]
assert "<p>Olá, {FirstName}!</p>" in fb_f_zero, f"Faltou saudação em zero: {fb_f_zero}"
assert "<p>Atenciosamente, Prof. Arly</p>" in fb_f_zero, f"Faltou assinatura em zero: {fb_f_zero}"
print("  OK: Feedback zerado de Fórum possui 'Olá, {FirstName}!' e 'Atenciosamente, Prof. Arly'")


print("\n=== 3. TESTANDO FEEDBACK DE ATIVIDADE ABERTA (MOTOR_ATIVIDADES) ===")
# 3.1 Feedback normal com envio
res_ativ = motor_atividades.avaliar_estudante_atividade(
    texto_submissao="O relatório de estágio descreve a organização do espaço escolar e a gestão pedagógica observada durante o período de vivência institucional na educação básica.",
    nome_aluno="Carlos Souza",
    instrucoes="Elabore um relatório de estágio sobre a organização do espaço escolar e gestão pedagógica.",
    criterios_info={},
    nota_maxima=1.5,
    total_arqs=1,
    docente="Prof. LUIZ GUSTAVO DOS SANTOS"
)
fb_ativ = res_ativ["feedback_html"]
assert "<p>Olá, {FirstName}!</p>" in fb_ativ, f"Faltou saudação: {fb_ativ}"
assert "<p>Atenciosamente, Prof. Luiz</p>" in fb_ativ, f"Faltou assinatura: {fb_ativ}"
print("  OK: Feedback normal de Atividade Aberta possui 'Olá, {FirstName}!' e 'Atenciosamente, Prof. Luiz'")

# 3.2 Feedback atividade zerado (is_vazio)
res_ativ_zero = motor_atividades.avaliar_estudante_atividade(
    texto_submissao="",
    nome_aluno="Beatriz Lima",
    instrucoes="Elabore o relatório de estágio.",
    criterios_info={},
    nota_maxima=1.5,
    total_arqs=0,
    docente="Prof. Arly Cristopher Nascimento Alves"
)
fb_a_zero = res_ativ_zero["feedback_html"]
assert "<p>Olá, {FirstName}!</p>" in fb_a_zero, f"Faltou saudação em zero: {fb_a_zero}"
assert "<p>Atenciosamente, Prof. Arly</p>" in fb_a_zero, f"Faltou assinatura em zero: {fb_a_zero}"
print("  OK: Feedback zerado de Atividade possui 'Olá, {FirstName}!' e 'Atenciosamente, Prof. Arly'")

# 3.3 Feedback atividade fuga ao tema
res_ativ_fuga = motor_atividades.avaliar_estudante_atividade(
    texto_submissao="A astronomia e a física quântica dos buracos negros no cosmos sideral.",
    nome_aluno="João Pedro",
    instrucoes="Elabore um plano de aula sobre biologia celular e mitocôndrias.",
    criterios_info={},
    nota_maxima=1.5,
    total_arqs=1,
    docente="Prof. LUIZ GUSTAVO DOS SANTOS"
)
fb_a_fuga = res_ativ_fuga["feedback_html"]
assert "<p>Olá, {FirstName}!</p>" in fb_a_fuga, f"Faltou saudação em fuga: {fb_a_fuga}"
assert "<p>Atenciosamente, Prof. Luiz</p>" in fb_a_fuga, f"Faltou assinatura em fuga: {fb_a_fuga}"
print("  OK: Feedback fuga ao tema possui 'Olá, {FirstName}!' e 'Atenciosamente, Prof. Luiz'")

print("\n=== TODOS OS TESTES DE VALIDAÇÃO PASSARAM COM SUCESSO! ===")
