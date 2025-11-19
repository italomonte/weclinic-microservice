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
                    
                    # Verifica se já foi processado
                    if is_processed(ag_id):
                        total_ja_processados += 1
                        logger.info(
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{ciclo_prefix}⏭️  AGENDAMENTO JÁ PROCESSADO\n"
                            f"   ID: {ag_id}\n"
                            f"   Paciente: {nome_paciente}\n"
                            f"   Data/Hora: {data_agenda} às {hora_agenda}\n"
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
                        
                        # Processa procedimentos
                        procedimentos = (
                            ag.get("procedimentos") or
                            ag.get("procedimentos_com_obs") or
                            ag.get("procedimentosLista") or
                            []
                        )
                        if isinstance(procedimentos, list):
                            # Procedimentos podem ser strings ou objetos com campo "nome"
                            nomes_procedimentos = []
                            for p in procedimentos:
                                if isinstance(p, dict):
                                    # Se é um objeto, pega o campo "nome"
                                    nome = p.get("nome") or p.get("nomeProcedimento") or str(p)
                                    if nome:
                                        nomes_procedimentos.append(nome)
                                elif p:
                                    # Se é uma string ou outro tipo
                                    nomes_procedimentos.append(str(p))
                            procedimentos_texto = ", ".join(nomes_procedimentos) if nomes_procedimentos else ""
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
    logger.info(f"{ciclo_prefix}✅ Mensagens enviadas com sucesso: {total_processados}")
    logger.info(f"{ciclo_prefix}❌ Falhas no envio: {total_novos_encontrados - total_processados}")
    logger.info("=" * 70 + "\n")


if __name__ == "__main__":
    init_db()
    # Por padrão processa hoje
    hoje = datetime.date.today().isoformat()
    processar_intervalo(hoje, hoje)

