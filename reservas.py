import cadastros
import db
import regras
import ui
from config import VALIDADE_RESERVA_DIAS

SQL_RESERVAS = """
    SELECT r.id_reserva AS "Código", c.nome AS "Cliente", r.dt_reserva AS "Data",
           (r.dt_reserva + make_interval(days => %(dias)s))::date AS "Válida até",
           r.status AS "Situação",
           (SELECT string_agg(f.titulo || ' (' || e.tipo_midia || ', ex. ' || e.id_exemplar || ')',
                              '; ' ORDER BY f.titulo)
            FROM reserva_exemplar re
            JOIN exemplar e ON e.id_exemplar = re.id_exemplar
            JOIN filme f ON f.id_filme = e.id_filme
            WHERE re.id_reserva = r.id_reserva) AS "Exemplares"
    FROM reserva r
    JOIN cliente c ON c.id_cliente = r.id_cliente
    {where}
    ORDER BY r.dt_reserva DESC"""


def _listar(where="", params=None):
    params = {"dias": VALIDADE_RESERVA_DIAS, **(params or {})}
    return ui.consultar_e_imprimir(SQL_RESERVAS.format(where=where), params,
                                   vazio="Nenhuma reserva encontrada.")


def fazer_reserva():
    regras.atualizar_situacoes()
    id_cliente = cadastros.ler_codigo(cadastros.ENTIDADES["cliente"])
    idade = regras.idade_cliente(id_cliente)
    ui.titulo("Nova reserva - exemplares disponíveis")
    exemplares = regras.escolher_exemplares(id_cliente, idade, para_reserva=True)

    print("\nExemplares selecionados:")
    ui.imprimir_tabela(["Código", "Filme", "Mídia"], exemplares)
    if not ui.confirmar("Confirmar reserva?", padrao=True):
        ui.info("Reserva cancelada.")
        return
    with db.transacao():
        reserva = db.consultar_um(
            "INSERT INTO reserva (id_cliente) VALUES (%s) RETURNING id_reserva, dt_reserva",
            (id_cliente,))
        for id_exemplar, _, _ in exemplares:
            db.executar("INSERT INTO reserva_exemplar (id_reserva, id_exemplar) VALUES (%s, %s)",
                        (reserva["id_reserva"], id_exemplar))
    validade = db.valor("SELECT (%s::timestamp + make_interval(days => %s))::date",
                        (reserva["dt_reserva"], VALIDADE_RESERVA_DIAS))
    ui.sucesso(f"Reserva {reserva['id_reserva']} registrada. "
               f"Os exemplares ficam separados até {ui.formatar(validade)}.")


def listar_reservas():
    regras.atualizar_situacoes()
    filtro = ui.escolher("Mostrar", [("ativa", "Somente ativas"), (None, "Todas")])
    ui.titulo("Reservas")
    if filtro:
        _listar("WHERE r.status = %(status)s", {"status": filtro})
    else:
        _listar()


def buscar_por_cliente():
    termo = ui.ler("Parte do nome do cliente")
    ui.titulo("Reservas do cliente")
    _listar("WHERE c.nome ILIKE %(termo)s", {"termo": f"%{termo}%"})


def cancelar_reserva():
    regras.atualizar_situacoes()
    ui.titulo("Reservas ativas")
    linhas = _listar("WHERE r.status = 'ativa'")
    if not linhas:
        return
    codigo = ui.ler_codigo_em("Código da reserva a cancelar", [l[0] for l in linhas])
    if ui.confirmar(f"Cancelar a reserva {codigo}?"):
        db.executar("UPDATE reserva SET status = 'cancelada' WHERE id_reserva = %s", (codigo,))
        ui.sucesso(f"Reserva {codigo} cancelada. Os exemplares foram liberados.")


def excluir_reserva():
    ui.titulo("Todas as reservas")
    linhas = _listar()
    if not linhas:
        return
    codigo = ui.ler_codigo_em("Código da reserva a excluir", [l[0] for l in linhas])
    if ui.confirmar(f"Excluir definitivamente a reserva {codigo}?"):
        db.executar("DELETE FROM reserva WHERE id_reserva = %s", (codigo,))
        ui.sucesso(f"Reserva {codigo} excluída.")


def menu_reservas():
    ui.menu("RESERVAS", [
        ("Fazer reserva", fazer_reserva),
        ("Listar reservas", listar_reservas),
        ("Buscar reservas por cliente", buscar_por_cliente),
        ("Cancelar reserva", cancelar_reserva),
        ("Excluir reserva", excluir_reserva),
    ])
