import datetime
import logging
from api_client import fetch_agendamentos
from storage import init_db, is_processed, mark_processed
from sender import enviar_mensagem
from templates import CONFIRMACAO, CANCELAMENTO

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Palavras-chave para detecção de status
CANCELAMENTO_KEYWORD = "CANCELADO"
CONFIRMADO_KEYWORD = "CONFIRMADO"

# TESTE: Número permitido para envio de mensagens (apenas para testes)
NUMERO_TESTE = "92984532273"  # Remove ou comente esta linha para permitir todos os números


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


def formatar_data_brasileira(data_str):
    """
    Formata data de YYYY-MM-DD para DD/MM/YYYY.
    
    Args:
        data_str: Data no formato YYYY-MM-DD
        
    Returns:
        Data formatada como DD/MM/YYYY ou string original se inválida
    """
    if not data_str or data_str == "N/A":
        return data_str
    
    try:
        # Tenta parsear como YYYY-MM-DD
        data_obj = datetime.datetime.strptime(data_str, "%Y-%m-%d")
        return data_obj.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        # Se não conseguir parsear, retorna como está
        return data_str


def obter_status_agendamento(agendamento):
    """
    Extrai o status do agendamento usando apenas o campo 'status'.
    """
    status = agendamento.get("status")
    if status:
        return str(status).strip()
    return ""


def obter_procedimentos_texto(agendamento):
    """
    Retorna descrição textual dos procedimentos do agendamento.
    """
    procedimentos = (
        agendamento.get("procedimentos") or
        agendamento.get("procedimentos_com_obs") or
        agendamento.get("procedimentosLista") or
        []
    )

    if isinstance(procedimentos, list):
        nomes = []
        for proc in procedimentos:
            if isinstance(proc, dict):
                nome = proc.get("nome") or proc.get("nomeProcedimento") or str(proc)
                if nome:
                    nomes.append(nome)
            elif proc:
                nomes.append(str(proc))
        texto = ", ".join(nomes) if nomes else ""
    else:
        texto = str(procedimentos) if procedimentos else ""

    return texto if texto else "—"


def obter_numero_paciente(agendamento):
    """
    Extrai e sanitiza o telefone do paciente.
    """
    numero = (
        agendamento.get("telefoneCelularPaciente") or
        agendamento.get("telefone") or
        agendamento.get("telefone_celular_paciente") or
        agendamento.get("telefonePaciente") or
        ""
    )
    return "".join([c for c in str(numero) if c.isdigit()])


def processar_intervalo(data_inicial, data_final, ciclo_numero=None):
    """
    Processa todos os agendamentos entre as datas fornecidas.
    
    Faz paginação automática, filtra agendamentos novos, monta mensagens
    e envia confirmações.
    
    Args:
        data_inicial: Data inicial no formato YYYY-MM-DD
        data_final: Data final no formato YYYY-MM-DD
        ciclo_numero: Número do ciclo atual (opcional, para logs)
    """
    ciclo_prefix = f"[CICLO #{ciclo_numero}] " if ciclo_numero else ""
    
    logger.info("=" * 70)
    logger.info(f"{ciclo_prefix}🔍 INICIANDO BUSCA DE AGENDAMENTOS: {data_inicial} a {data_final}")
    logger.info("=" * 70)
    
    pagina = 0  # API começa a paginação em 0, não em 1
    total_processados = 0
    total_novos_encontrados = 0
    total_ja_processados = 0
    total_cancelamentos_encontrados = 0
    total_cancelamentos_notificados = 0
    total_cancelamentos_ja_processados = 0
    total_cancelamentos_sem_dados = 0
    total_cancelamentos_falha_envio = 0
    
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
                    
                    # Extrai informações básicas para log (antes de verificar processamento)
                    nome_paciente = (
                        ag.get("paciente_nome") or
                        ag.get("nomePaciente") or
                        ag.get("primeiro_nome_do_paciente") or
                        ag.get("pacienteNome") or
                        "N/A"
                    )
                    data_agenda = ag.get("data") or ag.get("dataAgenda") or "N/A"
                    hora_agenda = (
                        ag.get("horaInicio") or
                        ag.get("hora") or
                        ag.get("hora_inicio") or
                        "N/A"
                    )
                    nome_prof = (
                        ag.get("nome_profissional") or
                        ag.get("profissional") or
                        ag.get("nomeProfissional") or
                        "N/A"
                    )
                    
                    status_texto = obter_status_agendamento(ag)
                    status_upper = status_texto.upper() if status_texto else ""
                    cancelamento_detectado = CANCELAMENTO_KEYWORD in status_upper
                    confirmado_detectado = CONFIRMADO_KEYWORD in status_upper

                    if cancelamento_detectado:
                        if is_processed(ag_id, tipo='cancelamento'):
                            total_cancelamentos_ja_processados += 1
                            logger.info(
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"{ciclo_prefix}⏭️  CANCELAMENTO JÁ NOTIFICADO\n"
                                f"   ID: {ag_id}\n"
                                f"   Paciente: {nome_paciente}\n"
                                f"   Status: {status_texto or 'CANCELADO'}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            )
                            continue

                        total_cancelamentos_encontrados += 1
                        logger.info(
                            f"\n{'='*70}\n"
                            f"{ciclo_prefix}🛑 CANCELAMENTO IDENTIFICADO\n"
                            f"{'='*70}\n"
                            f"   ID: {ag_id}\n"
                            f"   Paciente: {nome_paciente}\n"
                            f"   Data/Hora: {data_agenda} às {hora_agenda}\n"
                            f"   Status informado pela API: {status_texto or 'CANCELADO'}\n"
                            f"{'-'*70}"
                        )

                        nome_completo = nome_paciente if nome_paciente != "N/A" else ""
                        primeiro_nome = extrair_primeiro_nome(nome_completo) or "Paciente"

                        if data_agenda == "N/A":
                            data_agenda = ag.get("data") or ag.get("dataAgenda") or ""
                        if hora_agenda == "N/A":
                            hora_agenda = (
                                ag.get("horaInicio") or
                                ag.get("hora") or
                                ag.get("hora_inicio") or
                                ""
                            )

                        numero = obter_numero_paciente(ag)
                        procedimentos_texto = obter_procedimentos_texto(ag)
                        tipo_consulta = procedimentos_texto if procedimentos_texto != "—" else "sua consulta"
                        data_formatada = formatar_data_brasileira(data_agenda)

                        if not numero or not data_agenda or not hora_agenda:
                            total_cancelamentos_sem_dados += 1
                            logger.warning(
                                f"{ciclo_prefix}⚠️  CANCELAMENTO SEM DADOS SUFICIENTES\n"
                                f"   ID: {ag_id}\n"
                                f"   Necessário telefone, data e hora para notificar.\n"
                                f"{'='*70}\n"
                            )
                            continue

                        texto_cancelamento = CANCELAMENTO.substitute(
                            primeiro_nome=primeiro_nome,
                            tipo_consulta=tipo_consulta,
                            data_agenda=data_formatada or data_agenda,
                            hora_agenda=hora_agenda
                        )

                        logger.info(
                            f"   📱 Telefone: {numero}\n"
                            f"   📋 Procedimentos: {procedimentos_texto}\n"
                            f"   📅 Data: {data_formatada or data_agenda} às {hora_agenda}\n"
                            f"{'-'*70}\n"
                            f"{ciclo_prefix}📤 Enviando notificação de cancelamento...\n"
                            f"{'-'*70}"
                        )

                        # TESTE: Verifica se é o número permitido para testes (só antes de enviar)
                        if numero != NUMERO_TESTE:
                            logger.info(
                                f"{ciclo_prefix}🧪 TESTE: Cancelamento não enviado (número {numero} não é o número de teste)\n"
                                f"   ID: {ag_id}\n"
                                f"   Número permitido apenas: {NUMERO_TESTE}\n"
                                f"   Mensagem montada mas não enviada\n"
                                f"{'='*70}\n"
                            )
                            continue

                        ok_cancel = enviar_mensagem(numero, texto_cancelamento)

                        if ok_cancel:
                            mark_processed(ag_id, tipo='cancelamento')
                            total_cancelamentos_notificados += 1
                            logger.info(
                                f"{ciclo_prefix}✅ CANCELAMENTO NOTIFICADO\n"
                                f"   📱 Destinatário: {numero}\n"
                                f"   ✅ Registro marcado como cancelamento\n"
                                f"{'='*70}\n"
                            )
                        else:
                            total_cancelamentos_falha_envio += 1
                            logger.warning(
                                f"{ciclo_prefix}❌ FALHA AO NOTIFICAR CANCELAMENTO\n"
                                f"   📱 Destinatário: {numero}\n"
                                f"   ⚠️  Será tentado novamente no próximo ciclo\n"
                                f"{'='*70}\n"
                            )
                        continue

                    # Verifica se é confirmação (deve conter "CONFIRMADO" no status)
                    if not confirmado_detectado:
                        # Se não é cancelamento nem confirmação, ignora
                        logger.debug(
                            f"{ciclo_prefix}⏭️  Agendamento ignorado (status: {status_texto or 'N/A'})\n"
                            f"   ID: {ag_id}\n"
                            f"   Status não é CANCELADO nem CONFIRMADO\n"
                        )
                        continue

                    # Verifica se já foi processado (confirmação)
                    if is_processed(ag_id):
                        total_ja_processados += 1
                        logger.info(
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ciclo_prefix}⏭️  AGENDAMENTO JÁ PROCESSADO\n"
                            f"   ID: {ag_id}\n"
                            f"   Paciente: {nome_paciente}\n"
                            f"   Data/Hora: {data_agenda} às {hora_agenda}\n"
                            f"   Status: {status_texto or 'N/A'}\n"
                            f"   Profissional: {nome_prof}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        )
                        continue
                    
                    total_novos_encontrados += 1
                    # Log do agendamento NOVO encontrado
                    logger.info(
                        f"\n{'='*70}\n"
                        f"{ciclo_prefix}📋 NOVO AGENDAMENTO ENCONTRADO\n"
                        f"{'='*70}\n"
                        f"   ID: {ag_id}\n"
                        f"   Paciente: {nome_paciente}\n"
                        f"   Data/Hora: {data_agenda} às {hora_agenda}\n"
                        f"   Profissional: {nome_prof}\n"
                        f"{'-'*70}"
                    )
                    
                    try:
                        # Extrai dados com fallbacks para diferentes nomes de campos
                        # (já extraímos acima para o log, mas mantemos aqui para consistência)
                        nome_completo = nome_paciente if nome_paciente != "N/A" else ""
                        primeiro_nome = extrair_primeiro_nome(nome_completo)
                        
                        # Usa os valores já extraídos acima (ou extrai novamente se necessário)
                        if data_agenda == "N/A":
                            data_agenda = ag.get("data") or ag.get("dataAgenda") or ""
                        if hora_agenda == "N/A":
                            hora_agenda = (
                                ag.get("horaInicio") or
                                ag.get("hora") or
                                ag.get("hora_inicio") or
                                ""
                            )
                        if nome_prof == "N/A":
                            nome_prof = (
                                ag.get("nome_profissional") or
                                ag.get("profissional") or
                                ag.get("nomeProfissional") or
                                ""
                            )
                        
                        procedimentos_texto = obter_procedimentos_texto(ag)
                        
                        endereco = (
                            ag.get("endereco_clinica") or
                            ag.get("endereco") or
                            ag.get("enderecoClinica") or
                            ""
                        )
                        
                        # Formata número de telefone (remove caracteres não numéricos)
                        numero = obter_numero_paciente(ag)
                        
                        if not numero:
                            logger.warning(
                                f"{ciclo_prefix}⚠️  AVISO: Sem número de telefone válido\n"
                                f"   ⏭️  Agendamento ignorado (não será processado)\n"
                                f"{'='*70}\n"
                            )
                            continue
                        
                        # Formata data para formato brasileiro (DD/MM/YYYY)
                        data_formatada = formatar_data_brasileira(data_agenda)
                        
                        # Monta mensagem usando template
                        try:
                            texto = CONFIRMACAO.substitute(
                                primeiro_nome=primeiro_nome or "Sou o Assistente da WeClinic",
                                data_agenda=data_formatada,
                                hora_agenda=hora_agenda,
                                procedimentos=procedimentos_texto
                            )
                        except KeyError as e:
                            logger.error(
                                f"{ciclo_prefix}❌ ERRO: Falha ao processar template da mensagem\n"
                                f"   🔍 Variável faltando: {e}\n"
                                f"   ⏭️  Agendamento ignorado\n"
                                f"{'='*70}\n"
                            )
                            continue
                        
                        # Log detalhes do agendamento antes de enviar
                        logger.info(
                            f"   📱 Telefone: {numero}\n"
                            f"   📋 Procedimentos: {procedimentos_texto}\n"
                            f"   📅 Data: {data_formatada} às {hora_agenda}\n"
                            f"{'-'*70}\n"
                            f"{ciclo_prefix}📤 Enviando mensagem de confirmação...\n"
                            f"{'-'*70}"
                        )

                        # TESTE: Verifica se é o número permitido para testes (só antes de enviar)
                        if numero != NUMERO_TESTE:
                            logger.info(
                                f"{ciclo_prefix}🧪 TESTE: Confirmação não enviada (número {numero} não é o número de teste)\n"
                                f"   ID: {ag_id}\n"
                                f"   Número permitido apenas: {NUMERO_TESTE}\n"
                                f"   Mensagem montada mas não enviada\n"
                                f"{'='*70}\n"
                            )
                            continue
                        
                        # Envia mensagem
                        ok = enviar_mensagem(numero, texto)
                        
                        if ok:
                            mark_processed(ag_id)
                            total_processados += 1
                            logger.info(
                                f"{ciclo_prefix}✅ SUCESSO: Mensagem enviada com sucesso!\n"
                                f"   📱 Destinatário: {numero}\n"
                                f"   ✅ Agendamento marcado como processado\n"
                                f"{'='*70}\n"
                            )
                        else:
                            logger.warning(
                                f"{ciclo_prefix}❌ FALHA: Erro ao enviar mensagem\n"
                                f"   📱 Destinatário: {numero}\n"
                                f"   ⚠️  Agendamento NÃO marcado como processado\n"
                                f"   🔄 Será tentado novamente no próximo ciclo\n"
                                f"{'='*70}\n"
                            )
                    
                    except Exception as e:
                        logger.error(
                            f"{ciclo_prefix}❌ ERRO CRÍTICO ao processar agendamento {ag_id}\n"
                            f"   🔍 Erro: {e}\n"
                            f"   ⏭️  Continuando com próximo agendamento\n"
                            f"{'='*70}\n",
                            exc_info=True
                        )
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
    
    logger.info("\n" + "=" * 70)
    logger.info(f"{ciclo_prefix}📊 RESUMO DO PROCESSAMENTO")
    logger.info("=" * 70)
    logger.info(f"{ciclo_prefix}📋 Novos agendamentos encontrados: {total_novos_encontrados}")
    logger.info(f"{ciclo_prefix}⏭️  Agendamentos já processados: {total_ja_processados}")
    logger.info(f"{ciclo_prefix}✅ Confirmações enviadas com sucesso: {total_processados}")
    logger.info(f"{ciclo_prefix}❌ Falhas no envio (confirmações): {max(total_novos_encontrados - total_processados, 0)}")
    logger.info("-" * 70)
    logger.info(f"{ciclo_prefix}🛑 Cancelamentos identificados: {total_cancelamentos_encontrados}")
    logger.info(f"{ciclo_prefix}⏭️  Cancelamentos já notificados: {total_cancelamentos_ja_processados}")
    logger.info(f"{ciclo_prefix}✅ Cancelamentos notificados nesta execução: {total_cancelamentos_notificados}")
    logger.info(f"{ciclo_prefix}⚠️ Cancelamentos ignorados por falta de dados: {total_cancelamentos_sem_dados}")
    logger.info(f"{ciclo_prefix}❌ Falhas ao enviar cancelamentos: {total_cancelamentos_falha_envio}")
    logger.info("=" * 70 + "\n")


if __name__ == "__main__":
    init_db()
    # Por padrão processa hoje
    hoje = datetime.date.today().isoformat()
    processar_intervalo(hoje, hoje)

