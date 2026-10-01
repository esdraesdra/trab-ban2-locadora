from datetime import date, timedelta
from decimal import Decimal

import cadastros
import db
import regras
import ui
from config import VALOR_DIARIO_MULTA


def _periodo():
    hoje = date.today()
    inicio = ui.ler_data("Data inicial", padrao=hoje - timedelta(days=90))
    fim = ui.ler_data("Data final", padrao=hoje)
    if fim < inicio:
        raise ui.Aviso("A data final deve ser igual ou posterior à inicial.")
    return inicio, fim


def filmes_mais_locados():
    inicio, fim = _periodo()
    ui.titulo(f"Filmes mais locados de {ui.formatar(inicio)} a {ui.formatar(fim)}")
    ui.consultar_e_imprimir("""
        SELECT f.titulo AS "Filme", s.nome AS "Estúdio",
               (SELECT string_agg(g.nome, ', ' ORDER BY g.nome) FROM filme_genero fg
                JOIN genero g ON g.id_genero = fg.id_genero
                WHERE fg.id_filme = f.id_filme) AS "Gêneros",
               COUNT(*) AS "Locações",
               COUNT(DISTINCT l.id_cliente) AS "Clientes distintos"
        FROM locacao_exemplar le
        JOIN locacao l  ON l.id_locacao  = le.id_locacao
        JOIN exemplar e ON e.id_exemplar = le.id_exemplar
        JOIN filme f    ON f.id_filme    = e.id_filme
        JOIN estudio s  ON s.id_estudio  = f.id_estudio
        WHERE l.dt_locacao::date BETWEEN %s AND %s
        GROUP BY f.id_filme, f.titulo, s.nome
        ORDER BY COUNT(*) DESC, f.titulo""", (inicio, fim),
        vazio="Nenhuma locação no período.")


def faturamento_por_funcionario():
    inicio, fim = _periodo()
    ui.titulo(f"Faturamento por funcionário de {ui.formatar(inicio)} a {ui.formatar(fim)}")
    linhas = ui.consultar_e_imprimir("""
        SELECT fu.nome AS "Funcionário", fu.cargo AS "Cargo",
               COUNT(p.id_pagamento) AS "Pagamentos",
               COALESCE(SUM(p.valor) FILTER (WHERE p.id_locacao IS NOT NULL), 0) AS "Locações (R$)",
               COALESCE(SUM(p.valor) FILTER (WHERE p.id_multa IS NOT NULL), 0) AS "Multas (R$)",
               COALESCE(SUM(p.valor), 0) AS "Total (R$)"
        FROM funcionario fu
        LEFT JOIN pagamento p ON p.id_funcionario = fu.id_funcionario
                             AND p.dt_pagamento::date BETWEEN %s AND %s
        GROUP BY fu.id_funcionario, fu.nome, fu.cargo
        ORDER BY 6 DESC, fu.nome""", (inicio, fim))
    if linhas:
        print(f"Total geral recebido: {ui.dinheiro(sum(l[5] for l in linhas))}")


def clientes_com_multas():
    regras.atualizar_situacoes()
    ui.titulo("Clientes com multas em aberto")
    linhas = ui.consultar_e_imprimir("""
        SELECT c.nome AS "Cliente",
               (SELECT string_agg(t.telefone, ', ') FROM telefone_cliente t
                WHERE t.id_cliente = c.id_cliente) AS "Telefones",
               m.id_multa AS "Multa", l.id_locacao AS "Locação",
               vm.dias_atraso AS "Dias atraso", vm.valor_total AS "Valor (R$)",
               m.dt_vencimento AS "Vencimento",
               CASE WHEN m.dt_vencimento < CURRENT_DATE THEN 'VENCIDA' ELSE 'a vencer' END
                   AS "Situação"
        FROM multa m
        JOIN vw_multa vm ON vm.id_multa   = m.id_multa
        JOIN locacao l   ON l.id_locacao  = m.id_locacao
        JOIN cliente c   ON c.id_cliente  = l.id_cliente
        WHERE m.status = 'pendente'
        ORDER BY m.dt_vencimento""", vazio="Nenhum cliente com multa em aberto.")
    if linhas:
        print(f"Total em aberto: {ui.dinheiro(sum(l[5] for l in linhas))}")


def locacoes_em_atraso():
    regras.atualizar_situacoes()
    ui.titulo("Exemplares em atraso (ainda não devolvidos)")
    ui.consultar_e_imprimir("""
        SELECT l.id_locacao AS "Locação", c.nome AS "Cliente",
               (SELECT string_agg(t.telefone, ', ') FROM telefone_cliente t
                WHERE t.id_cliente = c.id_cliente) AS "Telefones",
               f.titulo AS "Filme", e.tipo_midia AS "Mídia",
               l.dt_prevista_devolucao AS "Devolver até",
               CURRENT_DATE - l.dt_prevista_devolucao AS "Dias atraso",
               (CURRENT_DATE - l.dt_prevista_devolucao) * %s AS "Multa estimada (R$)"
        FROM locacao l
        JOIN cliente c           ON c.id_cliente  = l.id_cliente
        JOIN locacao_exemplar le ON le.id_locacao = l.id_locacao
        JOIN exemplar e          ON e.id_exemplar = le.id_exemplar
        JOIN filme f             ON f.id_filme    = e.id_filme
        WHERE le.dt_devolucao IS NULL AND l.dt_prevista_devolucao < CURRENT_DATE
        ORDER BY 7 DESC, c.nome""", (VALOR_DIARIO_MULTA,), vazio="Nenhum exemplar em atraso.")
    print(f"Multa estimada com base na diária de {ui.dinheiro(VALOR_DIARIO_MULTA)}.")


def historico_cliente():
    id_cliente = cadastros.ler_codigo(cadastros.ENTIDADES["cliente"])
    nome = db.valor("SELECT nome FROM cliente WHERE id_cliente = %s", (id_cliente,))
    ui.titulo(f"Histórico de locações - {nome}")
    linhas = ui.consultar_e_imprimir("""
        SELECT l.id_locacao AS "Locação", l.dt_locacao AS "Retirada",
               f.titulo AS "Filme", e.tipo_midia AS "Mídia",
               l.dt_prevista_devolucao AS "Devolver até", le.dt_devolucao AS "Devolvido em",
               fu.nome AS "Atendente", l.status AS "Situação",
               COALESCE(m.status, '-') AS "Multa"
        FROM locacao l
        JOIN locacao_exemplar le ON le.id_locacao    = l.id_locacao
        JOIN exemplar e          ON e.id_exemplar    = le.id_exemplar
        JOIN filme f             ON f.id_filme       = e.id_filme
        JOIN funcionario fu      ON fu.id_funcionario = l.id_funcionario
        LEFT JOIN multa m        ON m.id_locacao     = l.id_locacao
        WHERE l.id_cliente = %s
        ORDER BY l.dt_locacao DESC, f.titulo""", (id_cliente,),
        vazio="O cliente ainda não fez locações.")
    if linhas:
        gasto = db.valor("""
            SELECT COALESCE(SUM(p.valor), 0) FROM pagamento p
            LEFT JOIN multa m ON m.id_multa = p.id_multa
            JOIN locacao l ON l.id_locacao = COALESCE(p.id_locacao, m.id_locacao)
            WHERE l.id_cliente = %s""", (id_cliente,))
        print(f"Total já pago pelo cliente: {ui.dinheiro(gasto or Decimal(0))}")


def situacao_acervo():
    regras.atualizar_situacoes()
    ui.titulo("Situação do acervo por filme")
    ui.consultar_e_imprimir("""
        SELECT f.titulo AS "Filme", s.nome AS "Estúdio",
               COUNT(e.id_exemplar) AS "Exemplares",
               COUNT(*) FILTER (WHERE e.status = 'disponivel' AND r.id_exemplar IS NULL)
                   AS "Disponíveis",
               COUNT(r.id_exemplar) AS "Reservados",
               COUNT(*) FILTER (WHERE e.status = 'locado') AS "Locados",
               COUNT(*) FILTER (WHERE e.status = 'danificado') AS "Danificados"
        FROM filme f
        JOIN estudio s       ON s.id_estudio = f.id_estudio
        LEFT JOIN exemplar e ON e.id_filme   = f.id_filme
        LEFT JOIN (SELECT DISTINCT re.id_exemplar
                   FROM reserva_exemplar re
                   JOIN reserva rv ON rv.id_reserva = re.id_reserva
                   WHERE rv.status = 'ativa') r ON r.id_exemplar = e.id_exemplar
        GROUP BY f.id_filme, f.titulo, s.nome
        ORDER BY f.titulo""")


def menu_relatorios():
    ui.menu("RELATÓRIOS", [
        ("Filmes mais locados por período", filmes_mais_locados),
        ("Faturamento por funcionário", faturamento_por_funcionario),
        ("Clientes com multas em aberto", clientes_com_multas),
        ("Exemplares em atraso", locacoes_em_atraso),
        ("Histórico de locações de um cliente", historico_cliente),
        ("Situação do acervo por filme", situacao_acervo),
    ])
