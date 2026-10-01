from datetime import date, timedelta
from decimal import Decimal

import cadastros
import db
import regras
import ui

FORMAS = [("dinheiro", "Dinheiro"), ("debito", "Cartão de débito"),
          ("credito", "Cartão de crédito"), ("pix", "PIX")]

SQL_MULTAS = """
    SELECT m.id_multa AS "Código", c.nome AS "Cliente", m.id_locacao AS "Locação",
           vm.dias_atraso AS "Dias atraso", m.valor_diario AS "Diária (R$)",
           vm.valor_total AS "Total (R$)", m.dt_vencimento AS "Vencimento",
           m.status AS "Situação"
    FROM multa m
    JOIN vw_multa vm ON vm.id_multa = m.id_multa
    JOIN locacao l ON l.id_locacao = m.id_locacao
    JOIN cliente c ON c.id_cliente = l.id_cliente
    {where}
    ORDER BY m.dt_vencimento"""

SQL_PAGAMENTOS = """
    SELECT p.id_pagamento AS "Código", p.dt_pagamento AS "Data", c.nome AS "Cliente",
           CASE WHEN p.id_locacao IS NOT NULL THEN 'Locação ' || p.id_locacao
                ELSE 'Multa ' || p.id_multa END AS "Referente a",
           p.forma_pagamento AS "Forma", p.valor AS "Valor (R$)", fu.nome AS "Recebido por"
    FROM pagamento p
    JOIN funcionario fu ON fu.id_funcionario = p.id_funcionario
    LEFT JOIN multa m ON m.id_multa = p.id_multa
    JOIN locacao l ON l.id_locacao = COALESCE(p.id_locacao, m.id_locacao)
    JOIN cliente c ON c.id_cliente = l.id_cliente
    {where}
    ORDER BY p.dt_pagamento DESC"""


def _ler_funcionario():
    return cadastros.ler_codigo(cadastros.ENTIDADES["funcionario"],
                                "Código do funcionário que está recebendo")


def pagar_locacao(id_locacao=None, id_funcionario=None):
    if id_locacao is None:
        ui.titulo("Locações sem pagamento")
        linhas = ui.consultar_e_imprimir(
            'SELECT l.id_locacao AS "Código", c.nome AS "Cliente", l.dt_locacao AS "Retirada", '
            'l.valor AS "Valor (R$)" FROM locacao l JOIN cliente c ON c.id_cliente = l.id_cliente '
            "WHERE l.valor > 0 AND NOT EXISTS "
            "(SELECT 1 FROM pagamento p WHERE p.id_locacao = l.id_locacao) ORDER BY l.dt_locacao",
            vazio="Todas as locações estão pagas.")
        if not linhas:
            return
        id_locacao = ui.ler_codigo_em("Código da locação", [l[0] for l in linhas])
    valor = db.valor("SELECT valor FROM locacao WHERE id_locacao = %s", (id_locacao,))
    if id_funcionario is None:
        id_funcionario = _ler_funcionario()
    print(f"\nValor a pagar pela locação {id_locacao}: {ui.dinheiro(valor)}")
    forma = ui.escolher("Forma de pagamento", FORMAS)
    codigo = db.valor(
        "INSERT INTO pagamento (valor, forma_pagamento, id_funcionario, id_locacao) "
        "VALUES (%s, %s, %s, %s) RETURNING id_pagamento",
        (valor, forma, id_funcionario, id_locacao))
    ui.sucesso(f"Pagamento {codigo} registrado: {ui.dinheiro(valor)}.")


def pagar_multa(id_multa=None, id_funcionario=None):
    if id_multa is None:
        ui.titulo("Multas pendentes")
        linhas = ui.consultar_e_imprimir(SQL_MULTAS.format(where="WHERE m.status = 'pendente'"),
                                         vazio="Não há multas pendentes.")
        if not linhas:
            return
        id_multa = ui.ler_codigo_em("Código da multa", [l[0] for l in linhas])
    total = db.valor("SELECT valor_total FROM vw_multa WHERE id_multa = %s", (id_multa,))
    if id_funcionario is None:
        id_funcionario = _ler_funcionario()
    print(f"\nValor da multa {id_multa}: {ui.dinheiro(total)}")
    forma = ui.escolher("Forma de pagamento", FORMAS)
    with db.transacao():
        codigo = db.valor(
            "INSERT INTO pagamento (valor, forma_pagamento, id_funcionario, id_multa) "
            "VALUES (%s, %s, %s, %s) RETURNING id_pagamento",
            (total, forma, id_funcionario, id_multa))
        db.executar("UPDATE multa SET status = 'paga' WHERE id_multa = %s", (id_multa,))
    ui.sucesso(f"Pagamento {codigo} registrado. Multa {id_multa} quitada.")


def listar_pagamentos():
    hoje = date.today()
    inicio = ui.ler_data("Data inicial", padrao=hoje - timedelta(days=30))
    fim = ui.ler_data("Data final", padrao=hoje)
    ui.titulo(f"Pagamentos de {ui.formatar(inicio)} a {ui.formatar(fim)}")
    linhas = ui.consultar_e_imprimir(
        SQL_PAGAMENTOS.format(where="WHERE p.dt_pagamento::date BETWEEN %s AND %s"),
        (inicio, fim), vazio="Nenhum pagamento no período.")
    if linhas:
        print(f"Total recebido: {ui.dinheiro(sum(l[5] for l in linhas))}")


def _escolher_pagamento():
    ui.titulo("Pagamentos")
    linhas = ui.consultar_e_imprimir(SQL_PAGAMENTOS.format(where=""))
    if not linhas:
        return None
    return ui.ler_codigo_em("Código do pagamento", [l[0] for l in linhas])


def alterar_forma_pagamento():
    codigo = _escolher_pagamento()
    if codigo is None:
        return
    atual = db.valor("SELECT forma_pagamento FROM pagamento WHERE id_pagamento = %s", (codigo,))
    forma = ui.escolher("Nova forma de pagamento", FORMAS, padrao=atual, editando=True)
    db.executar("UPDATE pagamento SET forma_pagamento = %s WHERE id_pagamento = %s",
                (forma, codigo))
    ui.sucesso(f"Pagamento {codigo} alterado.")


def estornar_pagamento():
    codigo = _escolher_pagamento()
    if codigo is None:
        return
    if not ui.confirmar(f"Estornar (excluir) o pagamento {codigo}?"):
        ui.info("Operação cancelada.")
        return
    with db.transacao():
        id_multa = db.valor("SELECT id_multa FROM pagamento WHERE id_pagamento = %s", (codigo,))
        db.executar("DELETE FROM pagamento WHERE id_pagamento = %s", (codigo,))
        if id_multa:
            db.executar("UPDATE multa SET status = 'pendente' WHERE id_multa = %s", (id_multa,))
    ui.sucesso(f"Pagamento {codigo} estornado."
               + (f" A multa {id_multa} voltou a ficar pendente." if id_multa else ""))


def menu_pagamentos():
    ui.menu("PAGAMENTOS", [
        ("Pagar locação", pagar_locacao),
        ("Pagar multa", pagar_multa),
        ("Listar pagamentos por período", listar_pagamentos),
        ("Alterar forma de pagamento", alterar_forma_pagamento),
        ("Estornar pagamento", estornar_pagamento),
    ])


def listar_multas():
    regras.atualizar_situacoes()
    filtro = ui.escolher("Mostrar", [("WHERE m.status = 'pendente'", "Somente pendentes"),
                                     ("", "Todas")])
    ui.titulo("Multas")
    ui.consultar_e_imprimir(SQL_MULTAS.format(where=filtro), vazio="Nenhuma multa encontrada.")


def _escolher_multa_pendente():
    ui.titulo("Multas pendentes")
    linhas = ui.consultar_e_imprimir(SQL_MULTAS.format(where="WHERE m.status = 'pendente'"),
                                     vazio="Não há multas pendentes.")
    if not linhas:
        return None
    return ui.ler_codigo_em("Código da multa", [l[0] for l in linhas])


def alterar_multa():
    codigo = _escolher_multa_pendente()
    if codigo is None:
        return
    atual = db.consultar_um("SELECT valor_diario, dt_vencimento FROM multa WHERE id_multa = %s",
                            (codigo,))
    print("Enter mantém o valor atual.")
    diaria = ui.ler_decimal("Valor diário (R$)", minimo=Decimal("0.01"), padrao=atual["valor_diario"],
                            editando=True)
    vencimento = ui.ler_data("Vencimento", padrao=atual["dt_vencimento"], editando=True)
    db.executar("UPDATE multa SET valor_diario = %s, dt_vencimento = %s WHERE id_multa = %s",
                (diaria, vencimento, codigo))
    ui.sucesso(f"Multa {codigo} alterada.")


def excluir_multa():
    codigo = _escolher_multa_pendente()
    if codigo is None:
        return
    if ui.confirmar(f"Excluir (abonar) a multa {codigo}?"):
        db.executar("DELETE FROM multa WHERE id_multa = %s", (codigo,))
        ui.sucesso(f"Multa {codigo} excluída.")


def menu_multas():
    ui.menu("MULTAS", [
        ("Listar multas", listar_multas),
        ("Pagar multa", pagar_multa),
        ("Alterar valor diário / vencimento", alterar_multa),
        ("Excluir (abonar) multa", excluir_multa),
    ])
