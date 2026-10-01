# Locadora de Filmes

Sistema de terminal em Python com banco PostgreSQL.

## Requisitos

- PostgreSQL
- Python 3.10 ou superior
- pip

## Banco de dados

Crie o banco `locadora`:

```
createdb -U postgres locadora
```

Carregue o script de criação e carga inicial:

```
psql -U postgres -d locadora -f sql/locadora.sql
```

O script recria todas as tabelas, então pode ser executado de novo para restaurar os dados iniciais.

## Configuração

Edite `app/config.py` e ajuste o bloco `DB_CONFIG`:

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "locadora",
    "user": "postgres",
    "password": "sua_senha",
}
```

## Dependências

```
python -m pip install -r requirements.txt
```

No Windows, use `py` no lugar de `python` caso o comando não seja reconhecido.

## Execução

```
cd app
python main.py
```

O projeto não tem etapa de compilação. Ctrl+C cancela a operação atual e volta ao menu.
