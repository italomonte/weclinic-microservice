import datetime
import logging
from api_client import fetch_agendamentos
from storage import init_db, is_processed, mark_processed
from sender import enviar_mensagem
from templates import CONFIRMACAO

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extrair_primeiro_nome(fullname):
    """
    Extrai o primeiro nome de um nome completo.
    
    Args:
        fullname: Nome completo
        
    Returns:
        Primeiro nome ou string vazia se inválido
    """
    if not fullname:
        return ""
    partes = fullname.split()
    return partes[0] if partes else ""


def processar_intervalo(data_inicial, data_final):
    """
    Processa todos os agendamentos entre as datas fornecidas.
    
    Faz paginação automática, filtra agendamentos novos, monta mensagens
    e envia confirmações.
    
    Args:
        data_inicial: Data inicial no formato YYYY-MM-DD
        data_final: Data final no formato YYYY-MM-DD
    """
    logger.info(f"Iniciando processamento de agendamentos: {data_inicial} a {data_final}")
    
    pagina = 1
    total_processados = 0
    
    while True:
        try:
            resp = fetch_agendamentos(data_inicial, data_final, pagina=pagina)
            
            # Verifica se resposta está vazia
            if not resp:
                logger.debug(f"Resposta vazia na página {pagina}, finalizando paginação")
                break
            
            # Trata diferentes formatos de resposta
            # Pode ser uma lista de páginas ou um objeto único
            if isinstance(resp, list):
                lista_paginas = resp
            else:
                # Se for um objeto único com lista, trata como lista de uma página
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
                        logger.warning("Agendamento sem ID encontrado, ignorando")
                        continue
                    
                    # Verifica se já foi processado
                    if is_processed(ag_id):
                        logger.debug(f"Agendamento {ag_id} já foi processado, ignorando")
                        continue
                    
                    try:
                        # Extrai dados com fallbacks para diferentes nomes de campos
                        nome_completo = (
                            ag.get("paciente_nome") or
                            ag.get("nomePaciente") or
                            ag.get("primeiro_nome_do_paciente") or
                            ag.get("pacienteNome") or
                            ""
                        )
                        primeiro_nome = extrair_primeiro_nome(nome_completo)
                        
                        data_agenda = ag.get("data") or ag.get("dataAgenda") or ""
                        hora_agenda = (
                            ag.get("horaInicio") or
                            ag.get("hora") or
                            ag.get("hora_inicio") or
                            ""
                        )
                        nome_prof = (
                            ag.get("nome_profissional") or
                            ag.get("profissional") or
                            ag.get("nomeProfissional") or
                            ""
                        )
                        
                        # Processa procedimentos
                        procedimentos = (
                            ag.get("procedimentos") or
                            ag.get("procedimentos_com_obs") or
                            ag.get("procedimentosLista") or
                            []
                        )
                        if isinstance(procedimentos, list):
                            procedimentos_texto = ", ".join([str(p) for p in procedimentos if p])
                        else:
                            procedimentos_texto = str(procedimentos) if procedimentos else ""
                        
                        if not procedimentos_texto:
                            procedimentos_texto = "—"
                        
                        endereco = (
                            ag.get("endereco_clinica") or
                            ag.get("endereco") or
                            ag.get("enderecoClinica") or
                            ""
                        )
                        
                        # Formata número de telefone (remove caracteres não numéricos)
                        numero = (
                            ag.get("telefoneCelularPaciente") or
                            ag.get("telefone") or
                            ag.get("telefone_celular_paciente") or
                            ""
                        )
                        numero = "".join([c for c in str(numero) if c.isdigit()])
                        
                        if not numero:
                            logger.warning(f"Agendamento {ag_id} sem número de telefone válido, ignorando")
                            continue
                        
                        # Monta mensagem usando template
                        try:
                            texto = CONFIRMACAO.substitute(
                                primeiro_nome=primeiro_nome or "Olá",
                                data_agenda=data_agenda,
                                hora_agenda=hora_agenda,
                                nome_profissional=nome_prof or "o profissional",
                                procedimentos=procedimentos_texto,
                                endereco_clinica=endereco or "não informado"
                            )
                        except KeyError as e:
                            logger.error(f"Erro ao substituir variável no template: {e}")
                            continue
                        
                        # Envia mensagem
                        ok = enviar_mensagem(numero, texto)
                        
                        if ok:
                            mark_processed(ag_id)
                            total_processados += 1
                            logger.info(f"Agendamento {ag_id} processado e mensagem enviada para {numero}")
                        else:
                            logger.warning(f"Falha ao enviar mensagem para agendamento {ag_id}, não marcando como processado")
                    
                    except Exception as e:
                        logger.error(f"Erro ao processar agendamento {ag_id}: {e}", exc_info=True)
                        continue
            
            # Determina se deve continuar paginando
            # Verifica totalPaginas no primeiro objeto da resposta
            first = lista_paginas[0] if lista_paginas else {}
            total_paginas = first.get("totalPaginas") or first.get("totalPaginas")
            
            if total_paginas is not None:
                # API informou total de páginas
                if pagina >= total_paginas:
                    logger.debug(f"Todas as páginas processadas (total: {total_paginas})")
                    break
                pagina += 1
            else:
                # Sem informação de total, verifica se encontrou agendamentos
                if not agendamentos_encontrados:
                    logger.debug(f"Nenhum agendamento na página {pagina}, finalizando paginação")
                    break
                pagina += 1
        
        except Exception as e:
            logger.error(f"Erro ao processar página {pagina}: {e}", exc_info=True)
            # Continua para próxima página mesmo em caso de erro
            pagina += 1
            # Limita número de tentativas para evitar loop infinito
            if pagina > 100:
                logger.error("Limite de páginas excedido, abortando")
                break
    
    logger.info(f"Processamento concluído. Total de agendamentos processados: {total_processados}")


if __name__ == "__main__":
    init_db()
    # Por padrão processa hoje
    hoje = datetime.date.today().isoformat()
    processar_intervalo(hoje, hoje)

