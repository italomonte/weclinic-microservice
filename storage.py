import os
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
from contextlib import closing
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Conexão com PostgreSQL via DATABASE_URL (formato: postgresql://user:pass@host:port/dbname)
DATABASE_URL = os.getenv("DATABASE_URL")

# Pool de conexões (reutiliza conexões)
connection_pool = None


def get_connection():
    """
    Obtém uma conexão do pool ou cria uma nova conexão.
    """
    global connection_pool
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não configurada no .env")
    
    try:
        if connection_pool is None:
            # Cria pool de conexões (min=1, max=5)
            connection_pool = psycopg2.pool.SimpleConnectionPool(1, 5, DATABASE_URL)
            logger.debug("Pool de conexões PostgreSQL criado")
        
        return connection_pool.getconn()
    except psycopg2.Error as e:
        logger.error(f"Erro ao obter conexão: {e}")
        raise


def return_connection(conn):
    """Retorna conexão ao pool."""
    global connection_pool
    if connection_pool and conn:
        connection_pool.putconn(conn)


def init_db():
    """Inicializa o banco de dados PostgreSQL e cria a tabela processed se não existir."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não configurada no .env")
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processed (
                        id BIGINT PRIMARY KEY,
                        tipo VARCHAR(50),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("Banco de dados PostgreSQL inicializado com sucesso")
        finally:
            return_connection(conn)
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")
        raise


def is_processed(item_id):
    """
    Verifica se um ID já foi processado.
    
    Args:
        item_id: ID do agendamento
        
    Returns:
        True se já foi processado, False caso contrário
    """
    if not DATABASE_URL:
        logger.error("DATABASE_URL não configurada")
        return False
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM processed WHERE id = %s", (item_id,))
                return cur.fetchone() is not None
        finally:
            return_connection(conn)
    except Exception as e:
        logger.error(f"Erro ao verificar processamento do ID {item_id}: {e}")
        return False


def mark_processed(item_id, tipo='agendamento'):
    """
    Marca um ID como processado.
    
    Args:
        item_id: ID do agendamento
        tipo: Tipo do registro (padrão: 'agendamento')
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não configurada")
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processed (id, tipo) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                    (item_id, tipo)
                )
                conn.commit()
                logger.debug(f"ID {item_id} marcado como processado (tipo: {tipo})")
        finally:
            return_connection(conn)
    except psycopg2.IntegrityError:
        # ID já existe (tratado pelo ON CONFLICT, mas mantido para logs)
        logger.debug(f"ID {item_id} já estava marcado como processado")
    except Exception as e:
        logger.error(f"Erro ao marcar ID {item_id} como processado: {e}")
        raise

