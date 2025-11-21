import os
import psycopg2
from psycopg2 import pool
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
                        id BIGINT NOT NULL,
                        tipo VARCHAR(50) DEFAULT 'agendamento',
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

                # Garante default e não-nulo para a coluna tipo
                cur.execute("ALTER TABLE processed ALTER COLUMN tipo SET DEFAULT 'agendamento'")
                cur.execute("UPDATE processed SET tipo = 'agendamento' WHERE tipo IS NULL")
                cur.execute("ALTER TABLE processed ALTER COLUMN tipo SET NOT NULL")
                conn.commit()

                # Ajusta chave primária para permitir múltiplos tipos por ID
                cur.execute("ALTER TABLE processed DROP CONSTRAINT IF EXISTS processed_pkey")
                cur.execute("ALTER TABLE processed ADD CONSTRAINT processed_pkey PRIMARY KEY (id, tipo)")
                conn.commit()

                logger.info("Banco de dados PostgreSQL inicializado com sucesso (schema verificado)")
        finally:
            return_connection(conn)
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")
        raise


def is_processed(item_id, tipo=None):
    """
    Verifica se um ID já foi processado.
    
    Args:
        item_id: ID do agendamento
        tipo: Tipo específico do processamento (agendamento, cancelamento, etc.)
              Se None, verifica se existe em QUALQUER tipo
        
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
                if tipo is None:
                    # Verifica se existe em qualquer tipo
                    cur.execute("SELECT 1 FROM processed WHERE id = %s", (item_id,))
                else:
                    # Verifica tipo específico
                    cur.execute("SELECT 1 FROM processed WHERE id = %s AND tipo = %s", (item_id, tipo))
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
                    "INSERT INTO processed (id, tipo) VALUES (%s, %s) ON CONFLICT (id, tipo) DO NOTHING",
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

