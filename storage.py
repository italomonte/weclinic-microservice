import sqlite3
from contextlib import closing
import logging

logger = logging.getLogger(__name__)

DB_PATH = "storage.db"


def init_db():
    """Inicializa o banco de dados SQLite e cria a tabela processed se não existir."""
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS processed (
                id INTEGER PRIMARY KEY,
                tipo TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()
            logger.info("Banco de dados inicializado com sucesso")
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
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM processed WHERE id = ?", (item_id,))
            return cur.fetchone() is not None
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
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO processed (id, tipo) VALUES (?, ?)", (item_id, tipo))
            conn.commit()
            logger.debug(f"ID {item_id} marcado como processado (tipo: {tipo})")
    except sqlite3.IntegrityError:
        # ID já existe, não faz nada
        logger.debug(f"ID {item_id} já estava marcado como processado")
    except Exception as e:
        logger.error(f"Erro ao marcar ID {item_id} como processado: {e}")
        raise

