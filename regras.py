import db
import ui
from config import VALIDADE_RESERVA_DIAS


def atualizar_situacoes():
    with db.transacao():
        db.executar("UPDATE locacao SET status = 'atrasada' "
                    "WHERE status = 'em andamento' AND dt_prevista_devolucao < CURRENT_DATE")
        db.executar("UPDATE reserva SET status = 'expirada' WHERE status = 'ativa' "
                    "AND dt_reserva + make_interval(days => %s) < now()",
                    (VALIDADE_RESERVA_DIAS,))


def idade_cliente(id_cliente):
    return db.valor("SELECT date_part('year', age(dt_nascimento))::int FROM cliente "
                    "WHERE id_cliente = %s", (id_cliente,))


def verificar_multas_pendentes(id_cliente):
    sql = """
        SELECT m.id_multa AS "Multa", m.id_locacao AS "Locação",
               vm.valor_total AS "Valor (R$)", m.dt_vencimento AS "Vencimento"
        FROM multa m
        JOIN vw_multa vm ON vm.id_multa = m.id_multa
        JOIN locacao l ON l.id_locacao = m.id_locacao
        WHERE l.id_cliente = %s AND m.status = 'pendente'
        ORDER BY m.dt_vencimento"""
    colunas, linhas = db.consultar(sql, (id_cliente,))
    if linhas:
        ui.imprimir_tabela(colunas, linhas)
        raise ui.Aviso("O cliente possui multas pendentes e não pode fazer novas locações. "
                       "Registre o pagamento em Pagamentos > Pagar multa.")


SQL_DISPONIVEIS = """
    SELECT e.id_exemplar AS "Código", f.titulo AS "Filme", e.tipo_midia AS "Mídia",
           f.classificacao_idade AS "Classificação"
    FROM exemplar e
    JOIN filme f ON f.id_filme = e.id_filme
    WHERE e.status = 'disponivel'
      AND NOT EXISTS (SELECT 1 FROM reserva_exemplar re
                      JOIN reserva r ON r.id_reserva = re.id_reserva
                      WHERE re.id_exemplar = e.id_exemplar AND r.status = 'ativa'
                        AND r.id_cliente <> %(cliente)s)
      AND f.titulo ILIKE %(filtro)s
    ORDER BY f.titulo, e.id_exemplar"""


def escolher_exemplares(id_cliente, idade, para_reserva, ja_escolhidos=(), obrigatorio=True):
    filtro = input("Filtrar por título (Enter = todos): ").strip()
    cliente_ref = -1 if para_reserva else id_cliente
    colunas, linhas = db.consultar(SQL_DISPONIVEIS, {"cliente": cliente_ref,
                                                     "filtro": f"%{filtro}%"})
    linhas = [l for l in linhas if l[0] not in ja_escolhidos]
    ui.imprimir_tabela(colunas, linhas, vazio="Nenhum exemplar disponível com esse filtro.")
    if not linhas:
        if obrigatorio:
            raise ui.Aviso("Não há exemplares disponíveis para esta operação.")
        return []
    por_codigo = {l[0]: l for l in linhas}
    while True:
        codigos = ui.ler_lista_codigos("Códigos dos exemplares (separados por vírgula)",
                                       por_codigo, permitir_vazio=not obrigatorio)
        proibidos = [por_codigo[c] for c in codigos if por_codigo[c][3] > idade]
        if not proibidos:
            return [(c, por_codigo[c][1], por_codigo[c][2]) for c in codigos]
        for _, titulo, _, classif in proibidos:
            print(f"  [!] Cliente com {idade} anos não pode locar '{titulo}' "
                  f"(classificação {classif} anos).")
