import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from config import DB_CONFIG

_conn = None


def conectar():
    global _conn
    _conn = psycopg.connect(**DB_CONFIG, autocommit=True, connect_timeout=5)
    return _conn


def fechar():
    if _conn is not None and not _conn.closed:
        _conn.close()


def transacao():
    return _conn.transaction()


def consultar(sql, params=None):
    cur = _conn.execute(sql, params)
    colunas = [d.name for d in cur.description]
    return colunas, cur.fetchall()


def consultar_um(sql, params=None):
    with _conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def valor(sql, params=None):
    linha = _conn.execute(sql, params).fetchone()
    return linha[0] if linha else None


def executar(sql, params=None):
    return _conn.execute(sql, params).rowcount


def mensagem_erro(e):
    diag = getattr(e, "diag", None)
    detalhe = (diag.message_detail or "") if diag else ""
    if isinstance(e, errors.ForeignKeyViolation):
        tabela = diag.table_name if diag else "?"
        return ("Operação não permitida: o registro está relacionado a outro "
                f"registro (tabela '{tabela}'). {detalhe}").strip()
    if isinstance(e, errors.UniqueViolation):
        return f"Já existe um registro com esse valor. {detalhe}".strip()
    if isinstance(e, errors.CheckViolation):
        restricao = diag.constraint_name if diag else "?"
        return f"Valor inválido: viola a regra '{restricao}' do banco."
    if isinstance(e, errors.NotNullViolation):
        coluna = diag.column_name if diag else "?"
        return f"O campo '{coluna}' é obrigatório."
    if isinstance(e, psycopg.OperationalError):
        return f"Falha de comunicação com o banco: {e}"
    primaria = diag.message_primary if diag and diag.message_primary else str(e)
    return f"Erro no banco de dados: {primaria}"
