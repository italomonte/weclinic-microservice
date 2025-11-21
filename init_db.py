"""
Script de inicialização do banco de dados.

Este script busca TODOS os agendamentos existentes na API e marca como processados
SEM enviar mensagens. Use quando iniciar o sistema pela primeira vez ou quiser
resetar apenas os agendamentos que já existiam.

Útil quando:
- Sistema já existia e quer evitar enviar mensagens para agendamentos antigos
- Resetar o banco mantendo apenas os novos agendamentos
"""

import datetime
import logging
import os
from api_client import fetch_agendamentos
from storage import init_db, is_processed, mark_processed
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def inicializar_banco(data_inicial=None, data_final=None):
    """
    Busca todos os agendamentos no intervalo e marca como processados SEM enviar mensagem.
    
    Args:
        data_inicial: Data inicial (YYYY-MM-DD). Se None, usa 60 dias atrás
        data_final: Data final (YYYY-MM-DD). Se None, usa hoje
    """
    init_db()
    
    # Define intervalo padrão: 60 dias atrás até hoje (ou use DAYS_AHEAD se configurado)
    if data_inicial is None:
        data_inicial = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    if data_final is None:
        data_final = datetime.date.today().isoformat()
    
    logger.info(f"Inicializando banco: marcando agendamentos de {data_inicial} a {data_final} como processados")
    logger.info("ATENÇÃO: Nenhuma mensagem será enviada. Apenas marcando IDs como processados.")
    
    pagina = 0  # API começa a paginação em 0, não em 1
    total_marcados = 0
    total_ja_existentes = 0
    
    while True:
        try:
            resp = fetch_agendamentos(data_inicial, data_final, pagina=pagina)
            
            if not resp:
                break
            
            # Trata diferentes formatos de resposta
            if isinstance(resp, list):
                lista_paginas = resp
            else:
                lista_paginas = [resp] if resp else []
            
            agendamentos_encontrados = False
            
            for page_obj in lista_paginas:
                lista = page_obj.get("lista", [])
                
                if not lista:
                    continue
                
                agendamentos_encontrados = True
                
                for ag in lista:
                    ag_id = ag.get("id")
                    if ag_id is None:
                        continue
                    
                    # Extrai data e hora do agendamento para armazenar
                    data_agenda = ag.get("data") or ag.get("dataAgenda")
                    hora_agenda = ag.get("horaInicio") or ag.get("hora") or ag.get("hora_inicio")
                    
                    # Verifica se já foi processado
                    if is_processed(ag_id):
                        total_ja_existentes += 1
                        logger.debug(f"ID {ag_id} já estava marcado como processado")
                    else:
                        # Marca como processado SEM enviar mensagem, mas salvando data/hora
                        mark_processed(ag_id, tipo='agendamento', data_agenda=data_agenda, hora_agenda=hora_agenda)
                        total_marcados += 1
                        logger.debug(f"ID {ag_id} marcado como processado (inicialização, data: {data_agenda}, hora: {hora_agenda})")
            
            # Determina se deve continuar paginando
            first = lista_paginas[0] if lista_paginas else {}
            total_paginas = first.get("totalPaginas")
            
            if total_paginas is not None:
                if pagina >= total_paginas:
                    break
                pagina += 1
            else:
                if not agendamentos_encontrados:
                    break
                pagina += 1
            
            # Log de progresso a cada 10 páginas
            if pagina % 10 == 0:
                logger.info(f"Progresso: página {pagina}, {total_marcados} novos marcados, {total_ja_existentes} já existentes")
        
        except Exception as e:
            logger.error(f"Erro ao processar página {pagina}: {e}", exc_info=True)
            pagina += 1
            if pagina > 100:
                logger.error("Limite de páginas excedido, abortando")
                break
    
    logger.info("=" * 60)
    logger.info(f"Inicialização concluída!")
    logger.info(f"  - Novos IDs marcados: {total_marcados}")
    logger.info(f"  - IDs já existentes: {total_ja_existentes}")
    logger.info(f"  - Total processado: {total_marcados + total_ja_existentes}")
    logger.info("=" * 60)
    logger.info("Agora o sistema só enviará mensagens para agendamentos NOVOS criados após esta inicialização.")


if __name__ == "__main__":
    import sys
    
    # Permite passar datas como argumentos opcionais
    # Exemplo: python3 init_db.py 2025-01-01 2025-12-31
    if len(sys.argv) == 3:
        data_inicial = sys.argv[1]
        data_final = sys.argv[2]
        inicializar_banco(data_inicial, data_final)
    elif len(sys.argv) == 2:
        # Se passar apenas uma data, usa ela como final e 60 dias antes como inicial
        data_final = sys.argv[1]
        data_inicial = (datetime.datetime.strptime(data_final, "%Y-%m-%d").date() - datetime.timedelta(days=60)).isoformat()
        inicializar_banco(data_inicial, data_final)
    else:
        # Usa padrão: 60 dias atrás até hoje
        inicializar_banco()

