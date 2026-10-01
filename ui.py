import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import psycopg

import db


class Aviso(Exception):
    pass


def formatar(v):
    if v is None:
        return "-"
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, Decimal):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(v, bool):
        return "sim" if v else "não"
    return str(v)


def dinheiro(v):
    return f"R$ {formatar(Decimal(v))}"


def titulo(texto):
    print("\n" + "=" * 60)
    print(f" {texto}")
    print("=" * 60)


def sucesso(msg):
    print(f"\n[OK] {msg}")


def info(msg):
    print(f"\n[i] {msg}")


def atencao(msg):
    print(f"\n[ATENÇÃO] {msg}")


def erro(msg):
    print(f"\n[ERRO] {msg}")


def imprimir_tabela(colunas, linhas, largura_max=38, vazio="Nenhum registro encontrado."):
    if not linhas:
        info(vazio)
        return
    celulas = [[formatar(v) for v in linha] for linha in linhas]
    celulas = [[c if len(c) <= largura_max else c[: largura_max - 3] + "..." for c in l]
               for l in celulas]
    larguras = [len(c) for c in colunas]
    for linha in celulas:
        for i, c in enumerate(linha):
            larguras[i] = max(larguras[i], len(c))
    sep = "+" + "+".join("-" * (w + 2) for w in larguras) + "+"

    def fmt(valores):
        return "|" + "|".join(f" {v:<{w}} " for v, w in zip(valores, larguras)) + "|"

    print(sep)
    print(fmt(colunas))
    print(sep)
    for linha in celulas:
        print(fmt(linha))
    print(sep)
    print(f"{len(linhas)} registro(s).")


def consultar_e_imprimir(sql, params=None, vazio="Nenhum registro encontrado."):
    colunas, linhas = db.consultar(sql, params)
    imprimir_tabela(colunas, linhas, vazio=vazio)
    return linhas


def pausar():
    input("\nPressione Enter para continuar...")


def conv_texto(tamanho=None):
    def f(s):
        if tamanho and len(s) > tamanho:
            raise ValueError(f"Máximo de {tamanho} caracteres.")
        return s
    return f


def conv_int(minimo=None, maximo=None):
    def f(s):
        try:
            n = int(s)
        except ValueError:
            raise ValueError("Digite um número inteiro.")
        if minimo is not None and n < minimo:
            raise ValueError(f"O valor mínimo é {minimo}.")
        if maximo is not None and n > maximo:
            raise ValueError(f"O valor máximo é {maximo}.")
        return n
    return f


def conv_decimal(minimo=None):
    def f(s):
        try:
            v = Decimal(s.replace(",", ".")).quantize(Decimal("0.01"))
        except InvalidOperation:
            raise ValueError("Digite um valor numérico (ex.: 12,50).")
        if minimo is not None and v < minimo:
            raise ValueError(f"O valor mínimo é {formatar(Decimal(minimo))}.")
        return v
    return f


def conv_data(s):
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError("Use o formato dd/mm/aaaa.")


def _somente_digitos(s):
    return re.sub(r"\D", "", s)


def cpf_valido(cpf):
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for tam in (9, 10):
        soma = sum(int(cpf[i]) * (tam + 1 - i) for i in range(tam))
        dig = (soma * 10) % 11 % 10
        if dig != int(cpf[tam]):
            return False
    return True


def conv_cpf(s):
    cpf = _somente_digitos(s)
    if not cpf_valido(cpf):
        raise ValueError("CPF inválido.")
    return cpf


def conv_cep(s):
    cep = _somente_digitos(s)
    if len(cep) != 8:
        raise ValueError("O CEP deve ter 8 dígitos.")
    return cep


def conv_email(s):
    if len(s) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s):
        raise ValueError("E-mail inválido.")
    return s


def conv_telefone(s):
    tel = _somente_digitos(s)
    if len(tel) not in (10, 11):
        raise ValueError("Informe DDD + número (10 ou 11 dígitos).")
    return tel


def conv_uf(s):
    if not re.fullmatch(r"[A-Za-z]{2}", s):
        raise ValueError("A sigla deve ter 2 letras.")
    return s.upper()


def ler(rotulo, conversor=conv_texto(), obrigatorio=True, padrao=None, editando=False):
    sufixo = ""
    if editando or padrao is not None:
        sufixo = f" [{formatar(padrao)}]"
    elif not obrigatorio and "Enter" not in rotulo:
        sufixo = " (opcional)"
    while True:
        s = input(f"{rotulo}{sufixo}: ").strip()
        if not s:
            if editando or padrao is not None:
                return padrao
            if not obrigatorio:
                return None
            print("  [!] Campo obrigatório.")
            continue
        if s == "-" and editando and not obrigatorio:
            return None
        try:
            return conversor(s)
        except ValueError as e:
            print(f"  [!] {e}")


def ler_int(rotulo, minimo=None, maximo=None, **kw):
    return ler(rotulo, conv_int(minimo, maximo), **kw)


def ler_decimal(rotulo, minimo=None, **kw):
    return ler(rotulo, conv_decimal(minimo), **kw)


def ler_data(rotulo, **kw):
    return ler(f"{rotulo} (dd/mm/aaaa)", conv_data, **kw)


def confirmar(pergunta, padrao=False):
    opcoes = "S/n" if padrao else "s/N"
    while True:
        s = input(f"{pergunta} ({opcoes}): ").strip().lower()
        if not s:
            return padrao
        if s in ("s", "sim"):
            return True
        if s in ("n", "nao", "não"):
            return False


def escolher(rotulo, opcoes, padrao=None, editando=False):
    print(f"{rotulo}:")
    for i, (_, texto) in enumerate(opcoes, 1):
        print(f"  {i} - {texto}")
    atual = next((t for v, t in opcoes if v == padrao), None)
    sufixo = f" [{atual}]" if (editando or padrao is not None) and atual else ""
    while True:
        s = input(f"Opção{sufixo}: ").strip()
        if not s and sufixo:
            return padrao
        if s.isdigit() and 1 <= int(s) <= len(opcoes):
            return opcoes[int(s) - 1][0]
        print("  [!] Opção inválida.")


def ler_codigo_em(rotulo, validos):
    validos = set(validos)
    while True:
        n = ler_int(rotulo)
        if n in validos:
            return n
        print("  [!] Código inválido para esta operação.")


def ler_lista_codigos(rotulo, validos, permitir_vazio=False):
    validos = set(validos)
    while True:
        s = input(f"{rotulo}: ").strip()
        if not s:
            if permitir_vazio:
                return []
            print("  [!] Informe ao menos um código.")
            continue
        try:
            codigos = list(dict.fromkeys(int(x) for x in re.split(r"[,\s]+", s) if x))
        except ValueError:
            print("  [!] Use apenas números separados por vírgula.")
            continue
        invalidos = [c for c in codigos if c not in validos]
        if invalidos:
            print(f"  [!] Código(s) inválido(s): {', '.join(map(str, invalidos))}")
            continue
        return codigos


def submenu(funcao):
    funcao.submenu = True
    return funcao


def executar_acao(funcao):
    try:
        funcao()
    except KeyboardInterrupt:
        print("\n\nOperação cancelada.")
    except Aviso as e:
        erro(str(e))
    except psycopg.Error as e:
        erro(db.mensagem_erro(e))
    if not getattr(funcao, "submenu", False):
        pausar()


def menu(nome, itens, texto_sair="Voltar", antes=None):
    while True:
        titulo(nome)
        if antes:
            antes()
        for i, (texto, _) in enumerate(itens, 1):
            print(f"  {i} - {texto}")
        print(f"  0 - {texto_sair}")
        s = input("\nOpção: ").strip()
        if s == "0":
            return
        if s.isdigit() and 1 <= int(s) <= len(itens):
            executar_acao(itens[int(s) - 1][1])
        else:
            print("  [!] Opção inválida.")
