"""
Script de inicialização do banco de dados.

Este script busca TODOS os agendamentos existentes na API e marca como processados
SEM enviar mensagens. Marca agendamentos, cancelamentos e reagendamentos de acordo
com o status atual. Use quando iniciar o sistema pela primeira vez ou quiser
resetar apenas os agendamentos que já existiam.

Útil quando:
- Sistema já existia e quer evitar enviar mensagens para agendamentos antigos
- Resetar o banco mantendo apenas os novos agendamentos
- Desenvolvimento: marcar tudo que aconteceu enquanto estava desenvolvendo
"""

import datetime
import logging
import os
from api_client import fetch_agendamentos
from storage import init_db, is_processed, mark_processed, get_processed_data
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Palavras-chave para detecção de status (mesmas do main.py)
CANCELAMENTO_KEYWORD = "CANCELADO"
CONFIRMADO_KEYWORD = "CONFIRMADO"


def obter_status_agendamento(agendamento):
    """Extrai o status do agendamento usando apenas o campo 'status'."""
    status = agendamento.get("status")
    if status:
        return str(status).strip()
    return ""


def inicializar_banco(data_inicial=None, data_final=None):
    """
    Busca todos os agendamentos no intervalo e marca como processados SEM enviar mensagem.
    Marca agendamentos confirmados e cancelamentos de acordo com o status atual.
    
    Args:
        data_inicial: Data inicial (YYYY-MM-DD). Se None, usa 60 dias atrás
        data_final: Data final (YYYY-MM-DD). Se None, usa hoje
    """
    init_db()
    
    # Define intervalo padrão: 60 dias atrás até hoje
    if data_inicial is None:
        data_inicial = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    if data_final is None:
        data_final = datetime.date.today().isoformat()
    
    logger.info(f"Inicializando banco: marcando agendamentos de {data_inicial} a {data_final} como processados")
    logger.info("ATENÇÃO: Nenhuma mensagem será enviada. Apenas marcando IDs como processados.")
    logger.info("Marcará agendamentos confirmados e cancelamentos de acordo com o status atual.")
    
    pagina = 0  # API começa a paginação em 0, não em 1
    total_marcados_agendamentos = 0
    total_marcados_cancelamentos = 0
    total_ja_existentes = 0
    total_reagendamentos_atualizados = 0
    
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
                    
                    # Extrai status e dados do agendamento
                    status_texto = obter_status_agendamento(ag)
                    status_upper = status_texto.upper() if status_texto else ""
                    
                    # BLOQUEIO GLOBAL: Ignora TUDO para este executor específico
                    id_executor = ag.get("idPessoaExecutor")
                    if id_executor == 21430526:
                        logger.debug(f"ID {ag_id} ignorado (Bloqueio Global Profissional 21430526)")
                        continue

                    cancelamento_detectado = CANCELAMENTO_KEYWORD in status_upper
                    confirmado_detectado = CONFIRMADO_KEYWORD in status_upper
                    
                    # Extrai data e hora do agendamento para armazenar
                    data_agenda = ag.get("data") or ag.get("dataAgenda")
                    hora_agenda = ag.get("horaInicio") or ag.get("hora") or ag.get("hora_inicio")
                    
                    # Determina o tipo baseado no status
                    tipo_processamento = None
                    if cancelamento_detectado:
                        tipo_processamento = 'cancelamento'
                    elif confirmado_detectado:
                        tipo_processamento = 'agendamento'
                    else:
                        # Se não é cancelado nem confirmado, marca como agendamento por padrão
                        tipo_processamento = 'agendamento'
                    
                    id_tipo_consulta = ag.get("idTipoConsulta")
                    
                    # Verifica se já foi processado para este tipo
                    if is_processed(ag_id, tipo=tipo_processamento):
                        # Se já foi processado, verifica se é um reagendamento (data/hora diferente)
                        if tipo_processamento == 'agendamento' and data_agenda and hora_agenda:
                            data_anterior, hora_anterior, id_tipo_consulta_anterior = get_processed_data(ag_id, tipo='agendamento')
                            
                            # Normaliza data e hora atual para comparação
                            data_atual_str = str(data_agenda).strip() if data_agenda else ""
                            hora_atual_str = str(hora_agenda).strip() if hora_agenda else ""
                            
                            # Verifica se houve reagendamento (data ou hora diferentes)
                            eh_reagendamento = False
                            if data_anterior and hora_anterior:
                                data_anterior_str = str(data_anterior)
                                hora_anterior_str = str(hora_anterior)[:5]  # Apenas HH:MM para comparação
                                hora_atual_comparacao = hora_atual_str[:5] if len(hora_atual_str) >= 5 else hora_atual_str
                                
                                if data_atual_str != data_anterior_str or hora_atual_comparacao != hora_anterior_str:
                                    eh_reagendamento = True
                            elif data_anterior is None or hora_anterior is None:
                                # Se não tinha data/hora anterior salva, atualiza para garantir que fique salva
                                mark_processed(ag_id, tipo=tipo_processamento, data_agenda=data_agenda, hora_agenda=hora_agenda, id_tipo_consulta=id_tipo_consulta)
                                logger.debug(f"ID {ag_id} atualizado com data/hora (não havia data/hora anterior salva)")
                            
                            if eh_reagendamento:
                                # Atualiza data/hora para a mais recente, assim o sistema não detecta como reagendamento novo
                                mark_processed(ag_id, tipo=tipo_processamento, data_agenda=data_agenda, hora_agenda=hora_agenda, id_tipo_consulta=id_tipo_consulta)
                                total_reagendamentos_atualizados += 1
                                logger.info(f"🔄 Reagendamento detectado e atualizado - ID {ag_id} (data anterior: {data_anterior} {hora_anterior}, nova: {data_agenda} {hora_agenda})")
                            else:
                                total_ja_existentes += 1
                                logger.debug(f"ID {ag_id} (tipo: {tipo_processamento}) já estava marcado como processado")
                        else:
                            total_ja_existentes += 1
                            logger.debug(f"ID {ag_id} (tipo: {tipo_processamento}) já estava marcado como processado")
                    else:
                        # Marca como processado SEM enviar mensagem, mas salvando data/hora e id_tipo_consulta
                        mark_processed(ag_id, tipo=tipo_processamento, data_agenda=data_agenda, hora_agenda=hora_agenda, id_tipo_consulta=id_tipo_consulta)
                        if tipo_processamento == 'cancelamento':
                            total_marcados_cancelamentos += 1
                        else:
                            total_marcados_agendamentos += 1
                        logger.debug(f"ID {ag_id} marcado como {tipo_processamento} (status: {status_texto}, data: {data_agenda}, hora: {hora_agenda})")
            
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
                total_novos = total_marcados_agendamentos + total_marcados_cancelamentos
                logger.info(f"Progresso: página {pagina}, {total_novos} novos marcados ({total_marcados_agendamentos} agendamentos, {total_marcados_cancelamentos} cancelamentos), {total_reagendamentos_atualizados} reagendamentos atualizados, {total_ja_existentes} já existentes")
        
        except Exception as e:
            logger.error(f"Erro ao processar página {pagina}: {e}", exc_info=True)
            pagina += 1
            if pagina > 100:
                logger.error("Limite de páginas excedido, abortando")
                break
    
    total_novos = total_marcados_agendamentos + total_marcados_cancelamentos
    logger.info("=" * 60)
    logger.info(f"Inicialização concluída!")
    logger.info(f"  - Agendamentos marcados: {total_marcados_agendamentos}")
    logger.info(f"  - Cancelamentos marcados: {total_marcados_cancelamentos}")
    logger.info(f"  - Reagendamentos atualizados: {total_reagendamentos_atualizados}")
    logger.info(f"  - Total novos marcados: {total_novos}")
    logger.info(f"  - IDs já existentes (sem mudanças): {total_ja_existentes}")
    logger.info(f"  - Total processado: {total_novos + total_ja_existentes + total_reagendamentos_atualizados}")
    logger.info("=" * 60)
    logger.info("Agora o sistema só enviará mensagens para agendamentos, cancelamentos e reagendamentos NOVOS criados após esta inicialização.")


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

