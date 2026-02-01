import os
import psycopg2
from psycopg2 import pool
import logging
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Conexão com PostgreSQL via DATABASE_URL (formato: postgresql://user:pass@host:port/dbname)
DATABASE_URL = os.getenv("DATABASE_URL")

# Pool de conexões (reutiliza conexões)
connection_pool = None

# ============================================================================
# PROTEÇÃO ANTI-LOOP: Rate Limiting e Circuit Breaker
# ============================================================================

# Rate limiting: controla envios por número de telefone
# Formato: {numero: [(timestamp1, tipo1), (timestamp2, tipo2), ...]}
_rate_limit_cache = {}
RATE_LIMIT_MAX_PER_HOUR = int(os.getenv("RATE_LIMIT_MAX_PER_HOUR", "5"))  # Max mensagens por número por hora
RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hora

# Circuit breaker: para o sistema se houver muitos erros de DB
_circuit_breaker = {
    "failures": 0,
    "last_failure": None,
    "is_open": False,
    "open_until": None
}
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))  # Falhas para abrir
CIRCUIT_BREAKER_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"))  # Segundos para tentar novamente

# Limite de mensagens por ciclo (proteção global)
_cycle_message_count = 0
_cycle_start_time = None
MAX_MESSAGES_PER_CYCLE = int(os.getenv("MAX_MESSAGES_PER_CYCLE", "100"))

# Cache de IDs já processados neste ciclo (evita reprocessamento dentro do mesmo ciclo)
_processed_this_cycle = set()


def reset_cycle_protection():
    """Reseta contadores de proteção para um novo ciclo."""
    global _cycle_message_count, _cycle_start_time, _processed_this_cycle
    _cycle_message_count = 0
    _cycle_start_time = datetime.now()
    _processed_this_cycle = set()
    logger.debug("Proteção de ciclo resetada")


def check_cycle_limit():
    """
    Verifica se atingiu o limite de mensagens por ciclo.
    
    Returns:
        True se pode enviar, False se atingiu o limite
    """
    global _cycle_message_count
    if _cycle_message_count >= MAX_MESSAGES_PER_CYCLE:
        logger.warning(f"🚨 LIMITE DE CICLO ATINGIDO: {_cycle_message_count}/{MAX_MESSAGES_PER_CYCLE} mensagens")
        return False
    return True


def increment_cycle_count():
    """Incrementa contador de mensagens do ciclo."""
    global _cycle_message_count
    _cycle_message_count += 1
    if _cycle_message_count % 10 == 0:
        logger.info(f"📊 Mensagens neste ciclo: {_cycle_message_count}/{MAX_MESSAGES_PER_CYCLE}")


def is_processed_this_cycle(item_id, tipo):
    """Verifica se já foi processado neste ciclo (cache em memória)."""
    key = f"{item_id}:{tipo}"
    return key in _processed_this_cycle


def mark_processed_this_cycle(item_id, tipo):
    """Marca como processado neste ciclo (cache em memória)."""
    key = f"{item_id}:{tipo}"
    _processed_this_cycle.add(key)


def check_rate_limit(numero):
    """
    Verifica se um número está dentro do rate limit.
    
    Args:
        numero: Número de telefone
        
    Returns:
        True se pode enviar, False se excedeu o limite
    """
    if not numero:
        return False
    
    numero_limpo = "".join([c for c in str(numero) if c.isdigit()])
    agora = datetime.now()
    janela_inicio = agora - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    
    # Limpa registros antigos
    if numero_limpo in _rate_limit_cache:
        _rate_limit_cache[numero_limpo] = [
            (ts, tipo) for ts, tipo in _rate_limit_cache[numero_limpo]
            if ts > janela_inicio
        ]
    else:
        _rate_limit_cache[numero_limpo] = []
    
    # Verifica limite
    envios_recentes = len(_rate_limit_cache[numero_limpo])
    if envios_recentes >= RATE_LIMIT_MAX_PER_HOUR:
        logger.warning(
            f"🚫 RATE LIMIT: Número {numero_limpo[-4:].rjust(len(numero_limpo), '*')} "
            f"já recebeu {envios_recentes} mensagens na última hora (limite: {RATE_LIMIT_MAX_PER_HOUR})"
        )
        return False
    
    return True


def register_rate_limit(numero, tipo="mensagem"):
    """Registra um envio no rate limit."""
    if not numero:
        return
    
    numero_limpo = "".join([c for c in str(numero) if c.isdigit()])
    if numero_limpo not in _rate_limit_cache:
        _rate_limit_cache[numero_limpo] = []
    
    _rate_limit_cache[numero_limpo].append((datetime.now(), tipo))


def _check_circuit_breaker():
    """
    Verifica estado do circuit breaker.
    
    Raises:
        RuntimeError: Se o circuit breaker estiver aberto
    """
    global _circuit_breaker
    
    if _circuit_breaker["is_open"]:
        if datetime.now() < _circuit_breaker["open_until"]:
            raise RuntimeError(
                f"🔴 CIRCUIT BREAKER ABERTO: Sistema pausado até "
                f"{_circuit_breaker['open_until'].strftime('%H:%M:%S')} "
                f"devido a {_circuit_breaker['failures']} falhas consecutivas no banco"
            )
        else:
            # Timeout expirou, tenta novamente
            logger.info("🟡 Circuit breaker: tentando reconectar ao banco...")
            _circuit_breaker["is_open"] = False


def _record_db_failure():
    """Registra uma falha de banco de dados."""
    global _circuit_breaker
    
    _circuit_breaker["failures"] += 1
    _circuit_breaker["last_failure"] = datetime.now()
    
    if _circuit_breaker["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
        _circuit_breaker["is_open"] = True
        _circuit_breaker["open_until"] = datetime.now() + timedelta(seconds=CIRCUIT_BREAKER_TIMEOUT)
        logger.error(
            f"🔴 CIRCUIT BREAKER ATIVADO: {_circuit_breaker['failures']} falhas consecutivas. "
            f"Sistema pausado por {CIRCUIT_BREAKER_TIMEOUT} segundos."
        )


def _record_db_success():
    """Registra sucesso na conexão com banco de dados."""
    global _circuit_breaker
    if _circuit_breaker["failures"] > 0:
        logger.info(f"🟢 Conexão com banco restabelecida após {_circuit_breaker['failures']} falhas")
    _circuit_breaker["failures"] = 0
    _circuit_breaker["is_open"] = False


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
                        data_agenda DATE,
                        hora_agenda TIME,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

                # Adiciona colunas de data/hora e id_tipo_consulta se não existirem (migração)
                cur.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='processed' AND column_name='data_agenda') THEN
                            ALTER TABLE processed ADD COLUMN data_agenda DATE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='processed' AND column_name='hora_agenda') THEN
                            ALTER TABLE processed ADD COLUMN hora_agenda TIME;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                      WHERE table_name='processed' AND column_name='id_tipo_consulta') THEN
                            ALTER TABLE processed ADD COLUMN id_tipo_consulta INTEGER;
                        END IF;
                    END $$;
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
        
    Raises:
        Exception: Se houver erro de conexão com o banco (NÃO retorna False!)
                   Isso evita que o sistema envie mensagens duplicadas em caso de falha do DB.
    """
    # PROTEÇÃO 1: Verifica cache do ciclo atual (mais rápido, sem DB)
    if tipo and is_processed_this_cycle(item_id, tipo):
        return True
    
    # PROTEÇÃO 2: Verifica circuit breaker
    _check_circuit_breaker()
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL não configurada")
        raise ValueError("DATABASE_URL não configurada - não é seguro assumir que não foi processado")
    
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
                result = cur.fetchone() is not None
                _record_db_success()
                return result
        finally:
            return_connection(conn)
    except Exception as e:
        # CRÍTICO: NÃO retornar False aqui! Isso causaria envio de mensagens duplicadas.
        # Em caso de erro de DB, é mais seguro PARAR o processamento do que arriscar spam.
        _record_db_failure()
        logger.error(f"Erro CRÍTICO ao verificar processamento do ID {item_id}: {e}")
        raise  # Propaga o erro para que o ciclo seja interrompido


def mark_processed(item_id, tipo='agendamento', data_agenda=None, hora_agenda=None, id_tipo_consulta=None):
    """
    Marca um ID como processado.
    
    Args:
        item_id: ID do agendamento
        tipo: Tipo do registro (padrão: 'agendamento')
        data_agenda: Data do agendamento (DATE ou string YYYY-MM-DD) - opcional
        hora_agenda: Hora do agendamento (TIME ou string HH:MM:SS) - opcional
        id_tipo_consulta: ID do tipo de consulta (INTEGER) - opcional, usado para detectar mudanças
    """
    # PROTEÇÃO: Verifica circuit breaker
    _check_circuit_breaker()
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não configurada")
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO processed (id, tipo, data_agenda, hora_agenda, id_tipo_consulta) 
                       VALUES (%s, %s, %s, %s, %s) 
                       ON CONFLICT (id, tipo) 
                       DO UPDATE SET data_agenda = EXCLUDED.data_agenda, 
                                     hora_agenda = EXCLUDED.hora_agenda,
                                     id_tipo_consulta = EXCLUDED.id_tipo_consulta""",
                    (item_id, tipo, data_agenda, hora_agenda, id_tipo_consulta)
                )
                conn.commit()
                _record_db_success()
                
                # PROTEÇÃO: Marca também no cache do ciclo
                mark_processed_this_cycle(item_id, tipo)
                
                logger.debug(f"ID {item_id} marcado como processado (tipo: {tipo}, data: {data_agenda}, hora: {hora_agenda}, id_tipo_consulta: {id_tipo_consulta})")
        finally:
            return_connection(conn)
    except psycopg2.IntegrityError:
        # ID já existe (tratado pelo ON CONFLICT, mas mantido para logs)
        logger.debug(f"ID {item_id} já estava marcado como processado")
    except Exception as e:
        _record_db_failure()
        logger.error(f"Erro ao marcar ID {item_id} como processado: {e}")
        raise


def clear_processed(item_id, tipo=None):
    """
    Remove marcações de processamento para um ID.
    
    Args:
        item_id: ID do agendamento
        tipo: Tipo específico a ser removido. Se None, remove todos os tipos.
        
    Returns:
        Número de registros removidos.
    """
    if not DATABASE_URL:
        logger.error("DATABASE_URL não configurada")
        return 0
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if tipo:
                    cur.execute("DELETE FROM processed WHERE id = %s AND tipo = %s", (item_id, tipo))
                else:
                    cur.execute("DELETE FROM processed WHERE id = %s", (item_id,))
                removidos = cur.rowcount
                conn.commit()
                if removidos:
                    logger.debug(f"ID {item_id} removido da tabela processed (tipo: {tipo or 'todos'})")
                return removidos
        finally:
            return_connection(conn)
    except Exception as e:
        logger.error(f"Erro ao remover processamento do ID {item_id}: {e}")
        return 0


def get_processed_data(item_id, tipo='agendamento'):
    """
    Obtém os dados armazenados de um agendamento processado.
    
    Args:
        item_id: ID do agendamento
        tipo: Tipo do registro (padrão: 'agendamento')
        
    Returns:
        Tupla (data_agenda, hora_agenda, id_tipo_consulta) ou (None, None, None) se não encontrado
    """
    if not DATABASE_URL:
        logger.error("DATABASE_URL não configurada")
        return (None, None, None)
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data_agenda, hora_agenda, id_tipo_consulta FROM processed WHERE id = %s AND tipo = %s",
                    (item_id, tipo)
                )
                result = cur.fetchone()
                if result:
                    return (result[0], result[1], result[2])
                return (None, None, None)
        finally:
            return_connection(conn)
    except Exception as e:
        logger.error(f"Erro ao buscar dados do ID {item_id}: {e}")
        return (None, None, None)

