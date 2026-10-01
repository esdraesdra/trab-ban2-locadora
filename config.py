from decimal import Decimal

DB_CONFIG = {
    "host": "localhost",    
    "port": 5432,            
    "dbname": "postgres",    
    "user": "postgres",      
    "password": 12345678,  
}


PRAZO_PADRAO_DIAS = 7         
PRAZO_MAXIMO_DIAS = 30         
VALIDADE_RESERVA_DIAS = 7      
VALOR_DIARIO_MULTA = Decimal("2.50")
DIAS_VENCIMENTO_MULTA = 10     

PRECO_MIDIA = {
    "DVD": Decimal("4.00"),
    "Blu-Ray": Decimal("6.00"),
    "4K": Decimal("8.00"),
}
