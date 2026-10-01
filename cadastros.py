from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from psycopg import errors

import db
import ui


@dataclass
class Campo:
    nome: str
    rotulo: str
    tipo: str = "texto"
    obrigatorio: bool = True
    tamanho: int | None = None
    minimo: int | None = None
    maximo: int | None = None
    opcoes: tuple = ()
    ref: str | None = None
    bloqueado_em: tuple = ()


@dataclass
class Entidade:
    chave: str
    nome: str
    plural: str
    tabela: str
    pk: str
    campos: list
    sql_base: str
    pk_expr: str
    busca: str
    rotulo_busca: str
    ordem: str
    extras: list = field(default_factory=list)
    coletar_extra: Callable | None = None
    gravar_extra: Callable | None = None


ENTIDADES: dict[str, Entidade] = {}


def listar(ent, where="", params=None):
    sql = f"{ent.sql_base} {where} ORDER BY {ent.ordem}"
    return ui.consultar_e_imprimir(sql, params)


def existe(ent, codigo):
    return db.valor(f"SELECT 1 FROM {ent.tabela} WHERE {ent.pk} = %s", (codigo,)) is not None


def ler_codigo(ent, rotulo=None, permitir_novo=False):
    ui.titulo(f"{ent.plural} cadastrados")
    listar(ent)
    rotulo = rotulo or f"Código do(a) {ent.nome.lower()}"
    if permitir_novo:
        rotulo += " (N = cadastrar novo)"
    while True:
        s = input(f"{rotulo}: ").strip()
        if permitir_novo and s.lower() == "n":
            return cadastrar(ent)
        if s.isdigit() and existe(ent, int(s)):
            return int(s)
        print(f"  [!] {ent.nome} não encontrado(a).")


def ler_varios(ent, rotulo):
    listar(ent)
    validos = {l[0] for l in db.consultar(f"SELECT {ent.pk} FROM {ent.tabela}")[1]}
    escolhidos = []
    while True:
        prompt = rotulo if not escolhidos else "Mais códigos (Enter para concluir)"
        s = input(f"{prompt} - separados por vírgula, N = cadastrar novo: ").strip()
        if not s and escolhidos:
            return escolhidos
        if s.lower() == "n":
            novo = cadastrar(ent)
            validos.add(novo)
            escolhidos.append(novo)
            continue
        try:
            codigos = [int(x) for x in s.replace(" ", "").split(",") if x]
        except ValueError:
            print("  [!] Use apenas números separados por vírgula.")
            continue
        invalidos = [c for c in codigos if c not in validos]
        if invalidos or not codigos:
            print(f"  [!] Código(s) inválido(s): {', '.join(map(str, invalidos)) or '-'}")
            continue
        escolhidos += [c for c in codigos if c not in escolhidos]
        print(f"  Selecionados: {', '.join(map(str, escolhidos))}")


def ler_campo(campo, atual=None, editando=False):
    kw = {"obrigatorio": campo.obrigatorio, "padrao": atual, "editando": editando}
    t = campo.tipo
    if t == "fk":
        ref = ENTIDADES[campo.ref]
        if editando:
            print(f"{campo.rotulo} atual: código {atual}")
            if not ui.confirmar(f"Alterar {campo.rotulo.lower()}?"):
                return atual
        return ler_codigo(ref, f"Código do(a) {campo.rotulo.lower()}", permitir_novo=True)
    if t == "escolha":
        return ui.escolher(campo.rotulo, list(campo.opcoes), padrao=atual, editando=editando)
    if t == "inteiro":
        return ui.ler_int(campo.rotulo, campo.minimo, campo.maximo, **kw)
    if t == "data":
        return ui.ler_data(campo.rotulo, **kw)
    conversores = {"cpf": ui.conv_cpf, "cep": ui.conv_cep, "email": ui.conv_email,
                   "uf": ui.conv_uf}
    conversor = conversores.get(t, ui.conv_texto(campo.tamanho))
    return ui.ler(campo.rotulo, conversor, **kw)


def cadastrar(ent):
    ui.titulo(f"Cadastrar {ent.nome.lower()}")
    valores = {}
    for c in ent.campos:
        valores[c.nome] = ler_campo(c)
    extra = ent.coletar_extra() if ent.coletar_extra else None
    colunas = ", ".join(valores)
    marcadores = ", ".join(["%s"] * len(valores))
    with db.transacao():
        novo = db.valor(
            f"INSERT INTO {ent.tabela} ({colunas}) VALUES ({marcadores}) RETURNING {ent.pk}",
            list(valores.values()))
        if ent.gravar_extra:
            ent.gravar_extra(novo, extra)
    ui.sucesso(f"{ent.nome} cadastrado(a) com o código {novo}.")
    return novo


def buscar(ent):
    ui.titulo(f"Buscar {ent.plural.lower()}")
    termo = ui.ler(f"Digite parte do(a) {ent.rotulo_busca}")
    listar(ent, f"WHERE {ent.busca} ILIKE %s", (f"%{termo}%",))


def alterar(ent):
    codigo = ler_codigo(ent)
    nomes = ", ".join(c.nome for c in ent.campos)
    atual = db.consultar_um(f"SELECT {nomes} FROM {ent.tabela} WHERE {ent.pk} = %s", (codigo,))
    ui.titulo(f"Alterar {ent.nome.lower()} {codigo}")
    print("Enter mantém o valor atual. Em campos opcionais, '-' apaga o valor.\n")
    novos = {}
    for c in ent.campos:
        if atual[c.nome] in c.bloqueado_em:
            print(f"{c.rotulo}: {ui.formatar(atual[c.nome])} (não pode ser alterado agora)")
            continue
        novos[c.nome] = ler_campo(c, atual[c.nome], editando=True)
    alterados = {k: v for k, v in novos.items() if v != atual[k]}
    if not alterados:
        ui.info("Nenhuma alteração realizada.")
        return
    sets = ", ".join(f"{k} = %s" for k in alterados)
    db.executar(f"UPDATE {ent.tabela} SET {sets} WHERE {ent.pk} = %s",
                [*alterados.values(), codigo])
    ui.sucesso(f"{ent.nome} {codigo} alterado(a).")


def excluir(ent):
    codigo = ler_codigo(ent)
    ui.titulo(f"Excluir {ent.nome.lower()} {codigo}")
    listar(ent, f"WHERE {ent.pk_expr} = %s", (codigo,))
    if not ui.confirmar("Confirma a exclusão?"):
        ui.info("Exclusão cancelada.")
        return
    try:
        db.executar(f"DELETE FROM {ent.tabela} WHERE {ent.pk} = %s", (codigo,))
    except errors.ForeignKeyViolation as e:
        raise ui.Aviso(f"Não é possível excluir: o registro é usado na tabela "
                       f"'{e.diag.table_name}'.") from None
    ui.sucesso(f"{ent.nome} {codigo} excluído(a).")


def menu_entidade(ent):
    itens = [
        ("Cadastrar", lambda: cadastrar(ent)),
        ("Listar todos", lambda: (ui.titulo(ent.plural), listar(ent))),
        (f"Buscar por {ent.rotulo_busca}", lambda: buscar(ent)),
        ("Alterar", lambda: alterar(ent)),
        ("Excluir", lambda: excluir(ent)),
    ] + ent.extras
    ui.menu(ent.plural, itens)


def menu_cadastros():
    ui.menu("CADASTROS", [(e.plural, ui.submenu(lambda e=e: menu_entidade(e)))
                          for e in ENTIDADES.values()])


def coletar_telefones():
    print("\nTelefones do cliente (ao menos um).")
    telefones = []
    while True:
        tel = ui.ler("Telefone com DDD" + (" (Enter para concluir)" if telefones else ""),
                     ui.conv_telefone, obrigatorio=not telefones)
        if tel is None:
            return telefones
        if tel not in telefones:
            telefones.append(tel)


def gravar_telefones(id_cliente, telefones):
    for tel in telefones:
        db.executar("INSERT INTO telefone_cliente (id_cliente, telefone) VALUES (%s, %s)",
                    (id_cliente, tel))


def gerenciar_telefones():
    id_cliente = ler_codigo(ENTIDADES["cliente"])
    sql = "SELECT telefone AS \"Telefone\" FROM telefone_cliente WHERE id_cliente = %s ORDER BY 1"

    def mostrar():
        nome = db.valor("SELECT nome FROM cliente WHERE id_cliente = %s", (id_cliente,))
        print(f"Cliente: {nome}")
        ui.consultar_e_imprimir(sql, (id_cliente,))

    def adicionar():
        tel = ui.ler("Novo telefone com DDD", ui.conv_telefone)
        db.executar("INSERT INTO telefone_cliente (id_cliente, telefone) VALUES (%s, %s)",
                    (id_cliente, tel))
        ui.sucesso("Telefone adicionado.")

    def remover():
        atuais = [l[0] for l in db.consultar(sql, (id_cliente,))[1]]
        if len(atuais) <= 1:
            raise ui.Aviso("O cliente precisa ter ao menos um telefone.")
        tel = ui.ler("Telefone a remover", ui.conv_telefone)
        if tel not in atuais:
            raise ui.Aviso("Telefone não encontrado para este cliente.")
        db.executar("DELETE FROM telefone_cliente WHERE id_cliente = %s AND telefone = %s",
                    (id_cliente, tel))
        ui.sucesso("Telefone removido.")

    ui.menu("Telefones do cliente", [("Adicionar telefone", adicionar),
                                     ("Remover telefone", remover)], antes=mostrar)


def coletar_generos_diretores():
    print("\nGêneros do filme (ao menos um):")
    generos = ler_varios(ENTIDADES["genero"], "Códigos dos gêneros")
    print("\nDiretores do filme (ao menos um):")
    diretores = ler_varios(ENTIDADES["diretor"], "Códigos dos diretores")
    return generos, diretores


def gravar_generos_diretores(id_filme, extra):
    generos, diretores = extra
    for g in generos:
        db.executar("INSERT INTO filme_genero (id_filme, id_genero) VALUES (%s, %s)", (id_filme, g))
    for d in diretores:
        db.executar("INSERT INTO filme_diretor (id_filme, id_diretor) VALUES (%s, %s)", (id_filme, d))


def gerenciar_generos_diretores():
    id_filme = ler_codigo(ENTIDADES["filme"])
    sql_g = ("SELECT g.id_genero AS \"Código\", g.nome AS \"Gênero\" FROM filme_genero fg "
             "JOIN genero g ON g.id_genero = fg.id_genero WHERE fg.id_filme = %s ORDER BY 2")
    sql_d = ("SELECT d.id_diretor AS \"Código\", d.nome AS \"Diretor\" FROM filme_diretor fd "
             "JOIN diretor d ON d.id_diretor = fd.id_diretor WHERE fd.id_filme = %s ORDER BY 2")

    def mostrar():
        print("Filme:", db.valor("SELECT titulo FROM filme WHERE id_filme = %s", (id_filme,)))
        ui.consultar_e_imprimir(sql_g, (id_filme,))
        ui.consultar_e_imprimir(sql_d, (id_filme,))

    def adicionar(tabela, coluna, ent):
        codigos = ler_varios(ENTIDADES[ent], "Códigos a adicionar")
        with db.transacao():
            for c in codigos:
                db.executar(f"INSERT INTO {tabela} (id_filme, {coluna}) VALUES (%s, %s) "
                            "ON CONFLICT DO NOTHING", (id_filme, c))
        ui.sucesso("Vínculo(s) adicionado(s).")

    def remover(tabela, coluna, sql, nome):
        atuais = [l[0] for l in db.consultar(sql, (id_filme,))[1]]
        if len(atuais) <= 1:
            raise ui.Aviso(f"O filme precisa ter ao menos um {nome}.")
        codigo = ui.ler_codigo_em(f"Código do {nome} a remover", atuais)
        db.executar(f"DELETE FROM {tabela} WHERE id_filme = %s AND {coluna} = %s",
                    (id_filme, codigo))
        ui.sucesso(f"{nome.capitalize()} removido do filme.")

    ui.menu("Gêneros e diretores do filme", [
        ("Adicionar gênero", lambda: adicionar("filme_genero", "id_genero", "genero")),
        ("Remover gênero", lambda: remover("filme_genero", "id_genero", sql_g, "gênero")),
        ("Adicionar diretor", lambda: adicionar("filme_diretor", "id_diretor", "diretor")),
        ("Remover diretor", lambda: remover("filme_diretor", "id_diretor", sql_d, "diretor")),
    ], antes=mostrar)


CLASSIFICACOES = ((0, "Livre"), (10, "10 anos"), (12, "12 anos"), (14, "14 anos"),
                  (16, "16 anos"), (18, "18 anos"))

SQL_RESERVADO = """EXISTS (SELECT 1 FROM reserva_exemplar re
                   JOIN reserva r ON r.id_reserva = re.id_reserva
                   WHERE re.id_exemplar = e.id_exemplar AND r.status = 'ativa')"""


def _registrar(ent):
    ENTIDADES[ent.chave] = ent


_registrar(Entidade(
    "estado", "Estado", "Estados", "estado", "id_estado",
    [Campo("nome", "Nome", tamanho=50), Campo("sigla", "Sigla (UF)", tipo="uf")],
    'SELECT e.id_estado AS "Código", e.nome AS "Estado", e.sigla AS "UF" FROM estado e',
    "e.id_estado", "e.nome", "nome", "e.nome"))

_registrar(Entidade(
    "cidade", "Cidade", "Cidades", "cidade", "id_cidade",
    [Campo("nome", "Nome", tamanho=100), Campo("id_estado", "Estado", tipo="fk", ref="estado")],
    'SELECT c.id_cidade AS "Código", c.nome AS "Cidade", e.sigla AS "UF" '
    "FROM cidade c JOIN estado e ON e.id_estado = c.id_estado",
    "c.id_cidade", "c.nome", "nome", "c.nome"))

_registrar(Entidade(
    "endereco", "Endereço", "Endereços", "endereco", "id_endereco",
    [Campo("rua", "Rua", tamanho=150), Campo("nr_casa", "Número", tamanho=10),
     Campo("bairro", "Bairro", tamanho=100), Campo("cep", "CEP", tipo="cep"),
     Campo("id_cidade", "Cidade", tipo="fk", ref="cidade")],
    'SELECT en.id_endereco AS "Código", en.rua AS "Rua", en.nr_casa AS "Nº", '
    'en.bairro AS "Bairro", en.cep AS "CEP", ci.nome || \'/\' || es.sigla AS "Cidade" '
    "FROM endereco en JOIN cidade ci ON ci.id_cidade = en.id_cidade "
    "JOIN estado es ON es.id_estado = ci.id_estado",
    "en.id_endereco", "en.rua || ' ' || en.bairro", "rua ou bairro", "ci.nome, en.rua"))

_registrar(Entidade(
    "cliente", "Cliente", "Clientes", "cliente", "id_cliente",
    [Campo("nome", "Nome", tamanho=100), Campo("cpf", "CPF", tipo="cpf"),
     Campo("email", "E-mail", tipo="email", obrigatorio=False),
     Campo("dt_nascimento", "Data de nascimento", tipo="data"),
     Campo("id_endereco", "Endereço", tipo="fk", ref="endereco")],
    'SELECT c.id_cliente AS "Código", c.nome AS "Nome", c.cpf AS "CPF", '
    'date_part(\'year\', age(c.dt_nascimento))::int AS "Idade", '
    "(SELECT string_agg(t.telefone, ', ' ORDER BY t.telefone) FROM telefone_cliente t "
    ' WHERE t.id_cliente = c.id_cliente) AS "Telefones", c.email AS "E-mail", '
    'ci.nome AS "Cidade" '
    "FROM cliente c JOIN endereco en ON en.id_endereco = c.id_endereco "
    "JOIN cidade ci ON ci.id_cidade = en.id_cidade",
    "c.id_cliente", "c.nome || ' ' || c.cpf", "nome ou CPF", "c.nome",
    extras=[("Gerenciar telefones", ui.submenu(gerenciar_telefones))],
    coletar_extra=coletar_telefones, gravar_extra=gravar_telefones))

_registrar(Entidade(
    "funcionario", "Funcionário", "Funcionários", "funcionario", "id_funcionario",
    [Campo("nome", "Nome", tamanho=100), Campo("cpf", "CPF", tipo="cpf"),
     Campo("cargo", "Cargo", tamanho=50)],
    'SELECT f.id_funcionario AS "Código", f.nome AS "Nome", f.cpf AS "CPF", '
    'f.cargo AS "Cargo" FROM funcionario f',
    "f.id_funcionario", "f.nome || ' ' || f.cpf", "nome ou CPF", "f.nome"))

_registrar(Entidade(
    "estudio", "Estúdio", "Estúdios", "estudio", "id_estudio",
    [Campo("nome", "Nome", tamanho=100)],
    'SELECT s.id_estudio AS "Código", s.nome AS "Estúdio", '
    '(SELECT COUNT(*) FROM filme f WHERE f.id_estudio = s.id_estudio) AS "Filmes" FROM estudio s',
    "s.id_estudio", "s.nome", "nome", "s.nome"))

_registrar(Entidade(
    "genero", "Gênero", "Gêneros", "genero", "id_genero",
    [Campo("nome", "Nome", tamanho=50)],
    'SELECT g.id_genero AS "Código", g.nome AS "Gênero" FROM genero g',
    "g.id_genero", "g.nome", "nome", "g.nome"))

_registrar(Entidade(
    "diretor", "Diretor", "Diretores", "diretor", "id_diretor",
    [Campo("nome", "Nome", tamanho=100)],
    'SELECT d.id_diretor AS "Código", d.nome AS "Diretor" FROM diretor d',
    "d.id_diretor", "d.nome", "nome", "d.nome"))

_registrar(Entidade(
    "filme", "Filme", "Filmes", "filme", "id_filme",
    [Campo("titulo", "Título", tamanho=150),
     Campo("ano_lancamento", "Ano de lançamento", tipo="inteiro", minimo=1888,
           maximo=date.today().year + 1),
     Campo("duracao_minutos", "Duração (minutos)", tipo="inteiro", minimo=1, maximo=999),
     Campo("classificacao_idade", "Classificação indicativa", tipo="escolha",
           opcoes=CLASSIFICACOES),
     Campo("id_estudio", "Estúdio", tipo="fk", ref="estudio")],
    'SELECT f.id_filme AS "Código", f.titulo AS "Título", f.ano_lancamento AS "Ano", '
    'f.duracao_minutos AS "Min", CASE f.classificacao_idade WHEN 0 THEN \'L\' '
    'ELSE f.classificacao_idade::text END AS "Class.", s.nome AS "Estúdio", '
    "(SELECT string_agg(g.nome, ', ' ORDER BY g.nome) FROM filme_genero fg "
    ' JOIN genero g ON g.id_genero = fg.id_genero WHERE fg.id_filme = f.id_filme) AS "Gêneros", '
    "(SELECT string_agg(d.nome, ', ' ORDER BY d.nome) FROM filme_diretor fd "
    ' JOIN diretor d ON d.id_diretor = fd.id_diretor WHERE fd.id_filme = f.id_filme) AS "Diretores" '
    "FROM filme f JOIN estudio s ON s.id_estudio = f.id_estudio",
    "f.id_filme", "f.titulo", "título", "f.titulo",
    extras=[("Gerenciar gêneros e diretores", ui.submenu(gerenciar_generos_diretores))],
    coletar_extra=coletar_generos_diretores, gravar_extra=gravar_generos_diretores))

_registrar(Entidade(
    "exemplar", "Exemplar", "Exemplares", "exemplar", "id_exemplar",
    [Campo("id_filme", "Filme", tipo="fk", ref="filme"),
     Campo("tipo_midia", "Tipo de mídia", tipo="escolha",
           opcoes=(("DVD", "DVD"), ("Blu-Ray", "Blu-Ray"), ("4K", "4K"))),
     Campo("status", "Situação", tipo="escolha",
           opcoes=(("disponivel", "Disponível"), ("danificado", "Danificado")),
           bloqueado_em=("locado",))],
    'SELECT e.id_exemplar AS "Código", f.titulo AS "Filme", e.tipo_midia AS "Mídia", '
    f'e.status AS "Situação", CASE WHEN {SQL_RESERVADO} THEN \'sim\' ELSE \'\' END AS "Reservado" '
    "FROM exemplar e JOIN filme f ON f.id_filme = e.id_filme",
    "e.id_exemplar", "f.titulo", "título do filme", "f.titulo, e.id_exemplar"))
