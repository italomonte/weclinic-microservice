import time
import os
import datetime
from dotenv import load_dotenv
import logging
from storage import init_db
from main import processar_intervalo

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

INTERVAL_MIN = int(os.getenv("INTERVAL_MIN", "5"))


def run_forever():
    """
    Loop infinito que executa processar_intervalo periodicamente.
    
    Intervalo é configurável via variável de ambiente INTERVAL_MIN (em minutos).
    Por padrão processa agendamentos do dia atual.
    """
    logger.info(f"Iniciando scheduler com intervalo de {INTERVAL_MIN} minutos")
    init_db()
    
    while True:
        try:
            hoje = datetime.date.today().isoformat()
            logger.info(f"Iniciando ciclo de processamento para {hoje}")
            
            # Por padrão processa hoje, mas pode ser ajustado para
            # processar próximos N dias se necessário
            processar_intervalo(hoje, hoje)
            
            logger.info(f"Ciclo concluído. Aguardando {INTERVAL_MIN} minutos para próximo ciclo")
        
        except KeyboardInterrupt:
            logger.info("Scheduler interrompido pelo usuário")
            break
        except Exception as e:
            logger.error(f"Erro no processamento: {e}", exc_info=True)
            logger.info(f"Aguardando {INTERVAL_MIN} minutos antes da próxima tentativa")
        
        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    run_forever()

