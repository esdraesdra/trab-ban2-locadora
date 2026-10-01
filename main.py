import sys

import cadastros
import db
import financeiro
import locacoes
import regras
import relatorios
import reservas
import ui
from config import DB_CONFIG


def conectar():
    try:
        db.conectar()
    except Exception as e:
        ui.erro("Não foi possível conectar ao banco de dados.")
        print(f"   Detalhe: {e}")
        print("\n   Verifique em app/config.py:")
        for chave in ("host", "port", "dbname", "user"):
            print(f"     {chave:<8} = {DB_CONFIG[chave]}")
        print("   e se o servidor PostgreSQL está ligado, o banco foi criado e a senha está certa.")
        sys.exit(1)


def main():
    conectar()
    regras.atualizar_situacoes()
    ui.menu("LOCADORA DE FILMES - MENU PRINCIPAL", [
        ("Cadastros", ui.submenu(cadastros.menu_cadastros)),
        ("Reservas", ui.submenu(reservas.menu_reservas)),
        ("Locações e devoluções", ui.submenu(locacoes.menu_locacoes)),
        ("Multas", ui.submenu(financeiro.menu_multas)),
        ("Pagamentos", ui.submenu(financeiro.menu_pagamentos)),
        ("Relatórios", ui.submenu(relatorios.menu_relatorios)),
    ], texto_sair="Sair")
    db.fechar()
    print("\nAté logo!")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        db.fechar()
        print("\n\nAplicação encerrada.")
