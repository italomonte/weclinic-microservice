"""
Script para contar todos os agendamentos de hoje até fim de 2026.

Percorre todas as páginas (começando em 0) até retornar lista vazia.
"""

import datetime
import logging
from api_client import fetch_agendamentos
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def contar_agendamentos(data_inicial, data_final):
    """
    Conta todos os agendamentos no intervalo especificado.
    
    Args:
        data_inicial: Data inicial (YYYY-MM-DD)
        data_final: Data final (YYYY-MM-DD)
        
    Returns:
        Total de agendamentos encontrados
    """
    logger.info("=" * 70)
    logger.info(f"🔍 CONTAGEM DE AGENDAMENTOS")
    logger.info("=" * 70)
    logger.info(f"   Período: {data_inicial} até {data_final}")
    logger.info(f"   Página inicial: 0")
    logger.info("=" * 70)
    logger.info("")
    
    pagina = 0
    total_agendamentos = 0
    total_paginas = 0
    
    while True:
        try:
            resp = fetch_agendamentos(data_inicial, data_final, pagina=pagina)
            
            if not resp:
                logger.info(f"📄 Página {pagina}: sem resposta")
                break
            
            # Trata diferentes formatos de resposta
            if isinstance(resp, list):
                lista_paginas = resp
            else:
                lista_paginas = [resp] if resp else []
            
            agendamentos_na_pagina = 0
            agendamentos_encontrados = False
            
            for page_obj in lista_paginas:
                lista = page_obj.get("lista", [])
                
                if not lista:
                    continue
                
                agendamentos_encontrados = True
                agendamentos_na_pagina += len(lista)
            
            if not agendamentos_encontrados:
                logger.info(f"📄 Página {pagina}: lista vazia ✓")
                break
            
            total_agendamentos += agendamentos_na_pagina
            total_paginas += 1
            
            logger.info(f"📄 Página {pagina}: {agendamentos_na_pagina} agendamentos encontrados")
            
            # Continua para próxima página (sempre até encontrar lista vazia)
            pagina += 1
            
            # Log de progresso a cada 10 páginas
            if total_paginas % 10 == 0:
                logger.info(f"   📊 Progresso: {total_paginas} páginas processadas, {total_agendamentos} agendamentos até agora...")
        
        except Exception as e:
            logger.error(f"❌ Erro ao processar página {pagina}: {e}")
            pagina += 1
            if pagina > 1000:  # Limite de segurança
                logger.error("Limite de páginas excedido (1000), abortando")
                break
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("📊 RESULTADO FINAL")
    logger.info("=" * 70)
    logger.info(f"   📅 Período: {data_inicial} até {data_final}")
    logger.info(f"   📄 Total de páginas processadas: {total_paginas + 1}")  # +1 porque começa em 0
    logger.info(f"   📋 Total de agendamentos encontrados: {total_agendamentos}")
    logger.info("=" * 70)
    
    return total_agendamentos


if __name__ == "__main__":
    # Define período: hoje até fim de 2026
    hoje = datetime.date.today().isoformat()
    fim_2026 = "2026-12-31"
    
    total = contar_agendamentos(hoje, fim_2026)
    
    print(f"\n✅ Contagem concluída: {total} agendamentos encontrados\n")

