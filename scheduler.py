import time
import os
import datetime
from datetime import datetime as dt
from dotenv import load_dotenv
import logging
from storage import init_db, reset_cycle_protection
from main import processar_intervalo, processar_lembretes

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

INTERVAL_MIN = int(os.getenv("INTERVAL_MIN", "5"))
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "60"))  # Quantos dias à frente buscar (0 = só hoje)


def run_forever():
    """
    Loop infinito que executa processar_intervalo periodicamente.
    
    Intervalo é configurável via variável de ambiente INTERVAL_MIN (em minutos).
    Por padrão processa agendamentos do dia atual, mas pode buscar dias futuros
    configurando DAYS_AHEAD no .env.
    """
    logger.info(f"Iniciando scheduler com intervalo de {INTERVAL_MIN} minutos")
    if DAYS_AHEAD > 0:
        logger.info(f"Buscando agendamentos para hoje + {DAYS_AHEAD} dias à frente")
    else:
        logger.info("Buscando agendamentos apenas para hoje")
    init_db()
    
    ciclo_numero = 0
    
    while True:
        try:
            ciclo_numero += 1
            
            # PROTEÇÃO: Reset de proteções de ciclo ANTES de processar
            reset_cycle_protection()
            
            hoje = datetime.date.today()
            data_inicial = hoje.isoformat()
            data_final = (hoje + datetime.timedelta(days=DAYS_AHEAD)).isoformat()
            
            logger.info("")
            logger.info("🔄" + "=" * 68)
            logger.info(f"🔄 CICLO #{ciclo_numero} - {dt.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"🔄 Período: {data_inicial} a {data_final} (Ano: {hoje.year})")
            logger.info("🔄" + "=" * 68)
            
            processar_intervalo(data_inicial, data_final, ciclo_numero)
            # Lembretes 24h antes
            processar_lembretes(ciclo_numero)
            
            logger.info("")
            logger.info(f"⏳ Próximo ciclo em {INTERVAL_MIN} minutos...")
            logger.info("")
        
        except KeyboardInterrupt:
            logger.info("Scheduler interrompido pelo usuário")
            break
        except Exception as e:
            logger.error(f"Erro no processamento: {e}", exc_info=True)
            logger.info(f"Aguardando {INTERVAL_MIN} minutos antes da próxima tentativa")
        
        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    run_forever()

