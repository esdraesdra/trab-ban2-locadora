from datetime import date, datetime, timedelta

import cadastros
import db
import financeiro
import regras
import ui
from config import (DIAS_VENCIMENTO_MULTA, PRAZO_MAXIMO_DIAS, PRAZO_PADRAO_DIAS,
                    PRECO_MIDIA, VALOR_DIARIO_MULTA)

SQL_LOCACOES = """
    SELECT l.id_locacao AS "Código", c.nome AS "Cliente", fu.nome AS "Funcionário",
           l.dt_locacao AS "Retirada", l.dt_prevista_devolucao AS "Devolver até",
           l.status AS "Situação",
           (SELECT COUNT(*) FROM locacao_exemplar le
            WHERE le.id_locacao = l.id_locacao AND le.dt_devolucao IS NULL) AS "Pendentes",
           l.valor AS "Valor (R$)",
           CASE WHEN EXISTS (SELECT 1 FROM pagamento p WHERE p.id_locacao = l.id_locacao)
                THEN 'sim' ELSE 'não' END AS "Paga"
    FROM locacao l
    JOIN cliente c ON c.id_cliente = l.id_cliente
    JOIN funcionario fu ON fu.id_funcionario = l.id_funcionario
    {where}
    ORDER BY l.dt_locacao DESC"""


def _listar(where="", params=None):
    return ui.consultar_e_imprimir(SQL_LOCACOES.format(where=where), params,
                                   vazio="Nenhuma locação encontrada.")


def _listar_abertas():
    ui.titulo("Locações em aberto")
    return _listar("WHERE l.status <> 'encerrada'")


def efetuar_locacao():
    regras.atualizar_situacoes()
    ent = cadastros.ENTIDADES
    id_funcionario = cadastros.ler_codigo(ent["funcionario"],
                                          "Código do funcionário que está registrando")
    id_cliente = cadastros.ler_codigo(ent["cliente"])
    regras.verificar_multas_pendentes(id_cliente)
    idade = regras.idade_cliente(id_cliente)

    escolhidos, id_reserva = [], None
    reserva = db.consultar_um(
        "SELECT id_reserva FROM reserva WHERE id_cliente = %s AND status = 'ativa' "
        "ORDER BY dt_reserva LIMIT 1", (id_cliente,))
    if reserva:
        colunas, linhas = db.consultar(
            'SELECT e.id_exemplar AS "Código", f.titulo AS "Filme", e.tipo_midia AS "Mídia" '
            "FROM reserva_exemplar re JOIN exemplar e ON e.id_exemplar = re.id_exemplar "
            "JOIN filme f ON f.id_filme = e.id_filme "
            "WHERE re.id_reserva = %s AND e.status = 'disponivel' ORDER BY f.titulo",
            (reserva["id_reserva"],))
        ui.titulo(f"O cliente possui a reserva ativa {reserva['id_reserva']}")
        ui.imprimir_tabela(colunas, linhas)
        if linhas and ui.confirmar("Locar os exemplares reservados?", padrao=True):
            escolhidos = [tuple(l) for l in linhas]
            id_reserva = reserva["id_reserva"]

    if not escolhidos or ui.confirmar("Adicionar outros exemplares?"):
        ui.titulo("Exemplares disponíveis")
        escolhidos += regras.escolher_exemplares(
            id_cliente, idade, para_reserva=False,
            ja_escolhidos={e[0] for e in escolhidos}, obrigatorio=not escolhidos)

    prazo = ui.ler_int(f"Prazo de devolução em dias (1 a {PRAZO_MAXIMO_DIAS})", 1,
                       PRAZO_MAXIMO_DIAS, padrao=PRAZO_PADRAO_DIAS)
    dt_prevista = date.today() + timedelta(days=prazo)
    sugerido = sum(PRECO_MIDIA[midia] for _, _, midia in escolhidos)
    valor = ui.ler_decimal("Valor da locação (R$)", minimo=0, padrao=sugerido)

    ui.titulo("Resumo da locação")
    ui.imprimir_tabela(["Código", "Filme", "Mídia"], escolhidos)
    print(f"Devolver até: {ui.formatar(dt_prevista)}   Valor: {ui.dinheiro(valor)}")
    if not ui.confirmar("Confirmar locação?", padrao=True):
        ui.info("Locação cancelada.")
        return

    with db.transacao():
        id_locacao = db.valor(
            "INSERT INTO locacao (dt_prevista_devolucao, valor, id_cliente, id_funcionario) "
            "VALUES (%s, %s, %s, %s) RETURNING id_locacao",
            (dt_prevista, valor, id_cliente, id_funcionario))
        for id_exemplar, titulo, _ in escolhidos:
            db.executar("INSERT INTO locacao_exemplar (id_locacao, id_exemplar) VALUES (%s, %s)",
                        (id_locacao, id_exemplar))
            if db.executar("UPDATE exemplar SET status = 'locado' "
                           "WHERE id_exemplar = %s AND status = 'disponivel'",
                           (id_exemplar,)) != 1:
                raise ui.Aviso(f"O exemplar {id_exemplar} ({titulo}) não está mais disponível.")
        if id_reserva:
            db.executar("UPDATE reserva SET status = 'atendida' WHERE id_reserva = %s",
                        (id_reserva,))
    ui.sucesso(f"Locação {id_locacao} registrada.")

    if valor > 0 and ui.confirmar("Registrar o pagamento agora?", padrao=True):
        financeiro.pagar_locacao(id_locacao, id_funcionario)


def registrar_devolucao():
    regras.atualizar_situacoes()
    linhas = _listar_abertas()
    if not linhas:
        return
    id_locacao = ui.ler_codigo_em("Código da locação", [l[0] for l in linhas])
    loc = db.consultar_um("SELECT dt_locacao, dt_prevista_devolucao FROM locacao "
                          "WHERE id_locacao = %s", (id_locacao,))

    colunas, pendentes = db.consultar(
        'SELECT e.id_exemplar AS "Código", f.titulo AS "Filme", e.tipo_midia AS "Mídia" '
        "FROM locacao_exemplar le JOIN exemplar e ON e.id_exemplar = le.id_exemplar "
        "JOIN filme f ON f.id_filme = e.id_filme "
        "WHERE le.id_locacao = %s AND le.dt_devolucao IS NULL ORDER BY f.titulo", (id_locacao,))
    ui.titulo(f"Exemplares pendentes da locação {id_locacao}")
    ui.imprimir_tabela(colunas, pendentes)
    titulos = {l[0]: l[1] for l in pendentes}
    devolvidos = ui.ler_lista_codigos("Códigos devolvidos (Enter = todos)", titulos,
                                      permitir_vazio=True) or list(titulos)

    hoje = date.today()
    while True:
        data = ui.ler_data("Data da devolução", padrao=hoje)
        if loc["dt_locacao"].date() <= data <= hoje:
            break
        print("  [!] A data deve estar entre a retirada e hoje.")
    momento = datetime.now() if data == hoje else datetime.combine(data, datetime.now().time())

    danificados = {c for c in devolvidos
                   if ui.confirmar(f"O exemplar {c} ({titulos[c]}) voltou danificado?")}

    multa = None
    with db.transacao():
        for c in devolvidos:
            db.executar("UPDATE locacao_exemplar SET dt_devolucao = %s "
                        "WHERE id_locacao = %s AND id_exemplar = %s", (momento, id_locacao, c))
            db.executar("UPDATE exemplar SET status = %s WHERE id_exemplar = %s",
                        ("danificado" if c in danificados else "disponivel", c))
        restantes = db.valor("SELECT COUNT(*) FROM locacao_exemplar "
                             "WHERE id_locacao = %s AND dt_devolucao IS NULL", (id_locacao,))
        if restantes == 0:
            db.executar("UPDATE locacao SET status = 'encerrada' WHERE id_locacao = %s",
                        (id_locacao,))
            atraso = db.valor(
                "SELECT GREATEST(0, MAX(le.dt_devolucao)::date - l.dt_prevista_devolucao) "
                "FROM locacao l JOIN locacao_exemplar le ON le.id_locacao = l.id_locacao "
                "WHERE l.id_locacao = %s GROUP BY l.dt_prevista_devolucao", (id_locacao,))
            if atraso > 0:
                multa = db.consultar_um(
                    "INSERT INTO multa (valor_diario, dt_vencimento, id_locacao) "
                    "VALUES (%s, %s, %s) RETURNING id_multa, dt_vencimento",
                    (VALOR_DIARIO_MULTA, data + timedelta(days=DIAS_VENCIMENTO_MULTA),
                     id_locacao))
                multa["dias"] = atraso

    ui.sucesso(f"{len(devolvidos)} exemplar(es) devolvido(s).")
    if restantes:
        ui.info(f"Ainda falta(m) {restantes} exemplar(es). A locação continua em aberto.")
        return
    ui.info(f"Locação {id_locacao} encerrada.")
    if multa:
        total = VALOR_DIARIO_MULTA * multa["dias"]
        ui.atencao(f"Devolução com {multa['dias']} dia(s) de atraso. Multa {multa['id_multa']} "
                f"gerada: {ui.dinheiro(total)} ({ui.dinheiro(VALOR_DIARIO_MULTA)} por dia), "
                f"vencimento em {ui.formatar(multa['dt_vencimento'])}.")
        if ui.confirmar("Registrar o pagamento da multa agora?"):
            financeiro.pagar_multa(multa["id_multa"])


def listar_locacoes():
    regras.atualizar_situacoes()
    filtro = ui.escolher("Mostrar", [
        ("WHERE l.status <> 'encerrada'", "Em aberto (em andamento e atrasadas)"),
        ("WHERE l.status = 'atrasada'", "Somente atrasadas"),
        ("WHERE l.status = 'encerrada'", "Somente encerradas"),
        ("", "Todas")])
    ui.titulo("Locações")
    _listar(filtro)


def buscar_por_cliente():
    termo = ui.ler("Parte do nome do cliente")
    ui.titulo("Locações do cliente")
    _listar("WHERE c.nome ILIKE %s", (f"%{termo}%",))


def detalhar_locacao():
    regras.atualizar_situacoes()
    codigo = ui.ler_int("Código da locação")
    ui.titulo(f"Locação {codigo}")
    if not _listar("WHERE l.id_locacao = %s", (codigo,)):
        return
    print("\nExemplares:")
    ui.consultar_e_imprimir(
        'SELECT e.id_exemplar AS "Código", f.titulo AS "Filme", e.tipo_midia AS "Mídia", '
        'le.dt_devolucao AS "Devolvido em" FROM locacao_exemplar le '
        "JOIN exemplar e ON e.id_exemplar = le.id_exemplar "
        "JOIN filme f ON f.id_filme = e.id_filme WHERE le.id_locacao = %s ORDER BY f.titulo",
        (codigo,))
    print("\nMulta:")
    ui.consultar_e_imprimir(
        'SELECT m.id_multa AS "Código", vm.dias_atraso AS "Dias de atraso", '
        'vm.valor_total AS "Valor (R$)", m.dt_vencimento AS "Vencimento", m.status AS "Situação" '
        "FROM multa m JOIN vw_multa vm ON vm.id_multa = m.id_multa WHERE m.id_locacao = %s",
        (codigo,), vazio="Sem multa.")
    print("\nPagamentos:")
    ui.consultar_e_imprimir(
        'SELECT p.id_pagamento AS "Código", '
        "CASE WHEN p.id_locacao IS NOT NULL THEN 'Locação' ELSE 'Multa' END AS \"Referente a\", "
        'p.dt_pagamento AS "Data", p.forma_pagamento AS "Forma", p.valor AS "Valor (R$)" '
        "FROM pagamento p LEFT JOIN multa m ON m.id_multa = p.id_multa "
        "WHERE p.id_locacao = %s OR m.id_locacao = %s ORDER BY p.dt_pagamento",
        (codigo, codigo), vazio="Nenhum pagamento.")


def alterar_prazo():
    regras.atualizar_situacoes()
    linhas = _listar_abertas()
    if not linhas:
        return
    codigo = ui.ler_codigo_em("Código da locação", [l[0] for l in linhas])
    loc = db.consultar_um("SELECT dt_locacao, dt_prevista_devolucao FROM locacao "
                          "WHERE id_locacao = %s", (codigo,))
    retirada = loc["dt_locacao"].date()
    limite = retirada + timedelta(days=PRAZO_MAXIMO_DIAS)
    print(f"O prazo pode ir até {ui.formatar(limite)} ({PRAZO_MAXIMO_DIAS} dias após a retirada).")
    while True:
        nova = ui.ler_data("Nova data limite", padrao=loc["dt_prevista_devolucao"])
        if max(retirada, date.today()) <= nova <= limite:
            break
        print(f"  [!] Informe uma data entre {ui.formatar(max(retirada, date.today()))} "
              f"e {ui.formatar(limite)}.")
    db.executar("UPDATE locacao SET dt_prevista_devolucao = %s, status = 'em andamento' "
                "WHERE id_locacao = %s", (nova, codigo))
    ui.sucesso(f"Prazo da locação {codigo} alterado para {ui.formatar(nova)}.")


def excluir_locacao():
    ui.titulo("Locações")
    linhas = _listar()
    if not linhas:
        return
    codigo = ui.ler_codigo_em("Código da locação a excluir", [l[0] for l in linhas])
    if db.valor("SELECT 1 FROM pagamento WHERE id_locacao = %s "
                "UNION SELECT 1 FROM multa WHERE id_locacao = %s", (codigo, codigo)):
        raise ui.Aviso("A locação possui pagamento ou multa. Estorne o pagamento e "
                       "exclua a multa antes de excluir a locação.")
    if not ui.confirmar(f"Excluir a locação {codigo}? Exemplares não devolvidos voltam "
                        "a ficar disponíveis."):
        ui.info("Exclusão cancelada.")
        return
    with db.transacao():
        db.executar("UPDATE exemplar SET status = 'disponivel' WHERE status = 'locado' "
                    "AND id_exemplar IN (SELECT id_exemplar FROM locacao_exemplar "
                    "WHERE id_locacao = %s AND dt_devolucao IS NULL)", (codigo,))
        db.executar("DELETE FROM locacao WHERE id_locacao = %s", (codigo,))
    ui.sucesso(f"Locação {codigo} excluída.")


def menu_locacoes():
    ui.menu("LOCAÇÕES E DEVOLUÇÕES", [
        ("Efetuar locação", efetuar_locacao),
        ("Registrar devolução", registrar_devolucao),
        ("Listar locações", listar_locacoes),
        ("Buscar locações por cliente", buscar_por_cliente),
        ("Detalhar locação", detalhar_locacao),
        ("Alterar prazo de devolução", alterar_prazo),
        ("Excluir locação", excluir_locacao),
    ])
