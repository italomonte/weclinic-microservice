import datetime
import logging
import os
from dotenv import load_dotenv
from api_client import fetch_agendamentos, fetch_paciente
from storage import (
    init_db, is_processed, mark_processed, get_processed_data, clear_processed,
    check_rate_limit, register_rate_limit, check_cycle_limit, increment_cycle_count,
    reset_cycle_protection, is_processed_this_cycle, mark_processed_this_cycle
)
from sender import enviar_mensagem
from templates import CONFIRMACAO, CANCELAMENTO, REAGENDAMENTO

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Palavras-chave para detecção de status
CANCELAMENTO_KEYWORD = "CANCELADO"
CONFIRMADO_KEYWORD = "CONFIRMADO"

# TESTE: Número permitido para envio de mensagens (apenas para testes)
# Quando None, o envio é liberado para todos os números.
NUMERO_TESTE = None

# Template names para Aspa API
ASPA_TEMPLATE_CONFIRMACAO = os.getenv("AGENDAMENTO_MODEL_NAME")
ASPA_TEMPLATE_EXC_CONS = os.getenv("AGENDAMENTO_EXC_CONS_MODEL_NAME")  # Para agendamentos que não são consulta
ASPA_TEMPLATE_REAGENDAMENTO = os.getenv("REAGENDAMENTO_MODEL_NAME")
ASPA_TEMPLATE_CANCELAMENTO = os.getenv("CANCELAMENTO_MODEL_NAME")

# Lembretes (24h antes)
ASPA_TEMPLATE_LEMBRETE_PADRAO = os.getenv("LEMBRETE_PADRAO_MODEL_NAME")
ASPA_TEMPLATE_LEMBRETE_DEPILACAO = os.getenv("LEMBRETE_DEPILACAO_MODEL_NAME")
ASPA_TEMPLATE_LEMBRETE_USG = os.getenv("LEMBRETE_USG_MODEL_NAME")
ASPA_TEMPLATE_LEMBRETE_DUOGLIDE = os.getenv("LEMBRETE_DUOGLIDE_MODEL_NAME")

ASPA_CHANNEL_ID = os.getenv("ASPA_CHANNEL")

# ID do tipo consulta (113784) - se idTipoConsulta for diferente, usa AGENDAMENTO_EXC_CONS_MODEL_NAME
ID_TIPO_CONSULTA = 113784

# Endereço padrão usado nas mensagens quando a API não enviar um endereço específico
ENDERECO_PADRAO = "R. Das Ametistas, 74 - Nossa Sra. das Graças, Manaus - AM, 69053-590"

# PROTEÇÃO: Limite máximo de páginas para evitar loop infinito na paginação
MAX_PAGINAS = int(os.getenv("MAX_PAGINAS", "50"))


def normalizar_numero_para_comparacao(numero):
    """
    Normaliza número de telefone para comparação, removendo prefixo 55 se existir.
    
    Args:
        numero: Número de telefone (pode ter prefixo 55 ou não)
        
    Returns:
        Número normalizado (apenas dígitos, sem prefixo 55)
    """
    if not numero:
        return ""
    # Remove todos os caracteres não numéricos
    numero_limpo = "".join([c for c in str(numero) if c.isdigit()])
    # Remove prefixo 55 se existir
    if numero_limpo.startswith("55") and len(numero_limpo) > 11:
        numero_limpo = numero_limpo[2:]
    return numero_limpo


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


def extrair_dois_primeiros_nomes(fullname):
    """
    Extrai até dois primeiros nomes de um nome completo.
    """
    if not fullname:
        return ""
    partes = [p for p in str(fullname).split() if p]
    if not partes:
        return ""
    return " ".join(partes[:2])


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


def eh_depilacao_laser(agendamento):
    """
    Retorna True se algum procedimento do agendamento for de Depilação a Laser.
    
    Critério: campo 'nome' do procedimento contém 'Depilação a Laser' (case-insensitive).
    """
    procedimentos = (
        agendamento.get("procedimentos") or
        agendamento.get("procedimentos_com_obs") or
        agendamento.get("procedimentosLista") or
        []
    )
    if not isinstance(procedimentos, list):
        return False
    for proc in procedimentos:
        if isinstance(proc, dict):
            nome = proc.get("nome") or proc.get("nomeProcedimento") or ""
        else:
            nome = str(proc or "")
        if "depilação a laser" in nome.lower():
            return True
    return False


def eh_usg_abdomen(agendamento):
    """
    Retorna True se algum procedimento for USG de abdômen.
    """
    procedimentos = (
        agendamento.get("procedimentos") or
        agendamento.get("procedimentos_com_obs") or
        agendamento.get("procedimentosLista") or
        []
    )
    if not isinstance(procedimentos, list):
        return False
    for proc in procedimentos:
        if isinstance(proc, dict):
            nome = proc.get("nome") or proc.get("nomeProcedimento") or ""
        else:
            nome = str(proc or "")
        nome_lower = nome.lower()
        if "usg" in nome_lower and ("abdomen" in nome_lower or "abdômen" in nome_lower):
            return True
    return False


def eh_duoglide(agendamento):
    """
    Retorna True se algum procedimento mencionar Laser Duoglide.
    """
    procedimentos = (
        agendamento.get("procedimentos") or
        agendamento.get("procedimentos_com_obs") or
        agendamento.get("procedimentosLista") or
        []
    )
    if not isinstance(procedimentos, list):
        return False
    for proc in procedimentos:
        if isinstance(proc, dict):
            nome = proc.get("nome") or proc.get("nomeProcedimento") or ""
        else:
            nome = str(proc or "")
        if "duoglide" in nome.lower():
            return True
    return False


def obter_dados_paciente_para_contato(agendamento):
    """
    Busca dados do paciente (quando possível) para montar alias.
    
    - Usa idPaciente da agenda para chamar /paciente/{id}
    - Alias: dois primeiros nomes do campo 'nome' do paciente
    - Telefone SEMPRE vem do agendamento (não do cadastro do paciente)
    """
    id_paciente = agendamento.get("idPaciente") or agendamento.get("id_paciente")
    alias = None
    numero = obter_numero_paciente(agendamento)
    
    if not id_paciente:
        # Sem idPaciente, tenta montar alias a partir do nome da agenda
        nome_paciente = (
            agendamento.get("paciente_nome") or
            agendamento.get("nomePaciente") or
            agendamento.get("primeiro_nome_do_paciente") or
            agendamento.get("pacienteNome") or
            ""
        )
        alias = extrair_dois_primeiros_nomes(nome_paciente) or extrair_primeiro_nome(nome_paciente)
        return alias, numero
    
    try:
        paciente = fetch_paciente(id_paciente)
    except Exception as e:
        logger.warning(f"Não foi possível buscar dados do paciente {id_paciente}: {e}")
        # Fallback para nome da agenda
        nome_paciente = (
            agendamento.get("paciente_nome") or
            agendamento.get("nomePaciente") or
            agendamento.get("primeiro_nome_do_paciente") or
            agendamento.get("pacienteNome") or
            ""
        )
        alias = extrair_dois_primeiros_nomes(nome_paciente) or extrair_primeiro_nome(nome_paciente)
        return alias, numero
    
    nome_completo = paciente.get("nome") or ""
    alias = extrair_dois_primeiros_nomes(nome_completo) or extrair_primeiro_nome(nome_completo)
    
    # Telefone permanece o que veio do agendamento
    return alias, numero


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


def montar_contact_object(alias, numero):
    """
    Monta objeto contact para Aspa API.
    
    Args:
        alias: Nome que será exibido no contato da Aspa (ex.: primeiros nomes do paciente)
        numero: Número de telefone (será formatado pela Aspa API)
    
    Returns:
        Objeto contact com alias, phone, update
    """
    alias_sanitizado = (alias or "").strip() or "Paciente"
    return {
        "alias": alias_sanitizado,
        "phone": numero,
        "update": False
    }


def montar_params_aspa_confirmacao(data_formatada, hora_agenda, procedimentos_texto, endereco):
    """
    Monta params para template de confirmação (AGENDAMENTO_MODEL_NAME).
    
    Template espera:
    - {{1}} = data (DD/MM/YYYY)
    - {{2}} = hora (HH:MM)
    - {{3}} = procedimentos
    - {{4}} = endereço
    
    Args:
        data_formatada: Data no formato DD/MM/YYYY
        hora_agenda: Hora no formato HH:MM ou HH:MM:SS
        procedimentos_texto: Texto dos procedimentos
        endereco: Endereço da clínica
    
    Returns:
        Dicionário com estrutura params para Aspa API (apenas content)
    """
    # Remove segundos da hora se houver
    hora_formatada = hora_agenda[:5] if len(hora_agenda) >= 5 else hora_agenda
    
    return {
        "content": {
            "1": data_formatada,
            "2": hora_formatada,
            "3": procedimentos_texto,
            "4": endereco or "—"
        }
    }


def montar_params_aspa_cancelamento(procedimentos_texto, data_formatada, hora_agenda):
    """
    Monta params para template de cancelamento (CANCELAMENTO_MODEL_NAME).
    
    Template espera:
    - {{1}} = tipo de atendimento (procedimentos)
    - {{2}} = data (DD/MM/YYYY)
    - {{3}} = hora (HH:MM)
    
    Args:
        procedimentos_texto: Texto dos procedimentos (tipo de atendimento)
        data_formatada: Data no formato DD/MM/YYYY
        hora_agenda: Hora no formato HH:MM ou HH:MM:SS
    
    Returns:
        Dicionário com estrutura params para Aspa API (apenas content)
    """
    # Remove segundos da hora se houver
    hora_formatada = hora_agenda[:5] if len(hora_agenda) >= 5 else hora_agenda
    
    return {
        "content": {
            "1": procedimentos_texto,
            "2": data_formatada,
            "3": hora_formatada
        }
    }


def montar_params_aspa_reagendamento(procedimentos_texto, data_formatada, hora_agenda, status, numero):
    """
    Monta params para template de reagendamento (REAGENDAMENTO_MODEL_NAME).
    
    Template espera:
    - {{1}} = tipo de atendimento (procedimentos)
    - {{2}} = data (DD/MM/YYYY)
    - {{3}} = hora (HH:MM)
    - {{4}} = status
    - {{5}} = telefone
    
    Args:
        procedimentos_texto: Texto dos procedimentos (tipo de atendimento)
        data_formatada: Data no formato DD/MM/YYYY
        hora_agenda: Hora no formato HH:MM ou HH:MM:SS
        status: Status do agendamento (ex: "REAGENDADO")
        numero: Número de telefone formatado
    
    Returns:
        Dicionário com estrutura params para Aspa API (apenas content)
    """
    # Remove segundos da hora se houver
    hora_formatada = hora_agenda[:5] if len(hora_agenda) >= 5 else hora_agenda
    
    return {
        "content": {
            "1": procedimentos_texto,
            "2": data_formatada,
            "3": hora_formatada,
            "4": status or "REAGENDADO",
            "5": numero
        }
    }


def montar_params_aspa_lembrete_padrao(data_formatada, hora_agenda, procedimentos_texto):
    """
    Monta params para template de lembrete padrão (LEMBRETE_PADRAO_MODEL_NAME).
    
    Template espera:
    - {{1}} = procedimentos
    - {{2}} = data (DD/MM/YYYY)
    - {{3}} = hora (HH:MM)
    """
    hora_formatada = hora_agenda[:5] if hora_agenda and len(hora_agenda) >= 5 else (hora_agenda or "")
    return {
        "content": {
            "1": procedimentos_texto,
            "2": data_formatada,
            "3": hora_formatada,
        }
    }


def montar_params_aspa_lembrete_depilacao():
    """
    Monta params para template de lembrete de depilação (LEMBRETE_DEPILACAO_MODEL_NAME).
    
    Este modelo não possui parâmetros.
    """
    return {
        "content": {}
    }


def montar_params_aspa_lembrete_dia_hora(data_formatada, hora_agenda):
    """
    Monta params simples que usam apenas dia e horário.
    """
    hora_formatada = hora_agenda[:5] if hora_agenda and len(hora_agenda) >= 5 else (hora_agenda or "")
    return {
        "content": {
            "1": data_formatada,
            "2": hora_formatada
        }
    }


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
    
    # PROTEÇÃO: Reset do controle de ciclo no início de cada processamento
    reset_cycle_protection()
    
    logger.info("=" * 70)
    logger.info(f"{ciclo_prefix}🔍 INICIANDO BUSCA DE AGENDAMENTOS: {data_inicial} a {data_final}")
    logger.info("=" * 70)
    
    pagina = 0  # API começa a paginação em 0, não em 1
    total_processados = 0
    total_novos_encontrados = 0
    total_reagendamentos_detectados = 0
    total_reagendamentos_enviados = 0
    total_ja_processados = 0
    total_cancelamentos_encontrados = 0
    total_cancelamentos_notificados = 0
    total_cancelamentos_ja_processados = 0
    total_cancelamentos_sem_dados = 0
    total_cancelamentos_falha_envio = 0
    total_bloqueado_rate_limit = 0
    total_bloqueado_ciclo = 0
    
    # PROTEÇÃO: Conjunto de IDs já processados neste ciclo para evitar duplicatas
    ids_processados_neste_ciclo = set()
    
    while True:
        # PROTEÇÃO: Limite de paginação para evitar loop infinito
        if pagina >= MAX_PAGINAS:
            logger.warning(f"{ciclo_prefix}⚠️ LIMITE DE PAGINAÇÃO ATINGIDO ({MAX_PAGINAS} páginas)")
            break
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
                    
                    # PROTEÇÃO: Evita processar o mesmo ID duas vezes no mesmo ciclo
                    if ag_id in ids_processados_neste_ciclo:
                        logger.debug(f"{ciclo_prefix}⏭️ ID {ag_id} já processado neste ciclo, ignorando duplicata")
                        continue
                    ids_processados_neste_ciclo.add(ag_id)
                    
                    # PROTEÇÃO: Verifica se atingiu o limite de mensagens por ciclo
                    if not check_cycle_limit():
                        logger.warning(f"{ciclo_prefix}⚠️ LIMITE DE MENSAGENS POR CICLO ATINGIDO - Finalizando processamento")
                        break
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
                    
                    # PROTEÇÃO: Valida ano do agendamento para evitar processar datas antigas na virada do ano
                    if data_agenda != "N/A":
                        try:
                            data_ag_obj = datetime.datetime.strptime(data_agenda, "%Y-%m-%d").date()
                            ano_atual = datetime.date.today().year
                            # Ignora agendamentos de anos anteriores (exceto dezembro/janeiro na transição)
                            if data_ag_obj.year < ano_atual - 1:
                                logger.debug(f"{ciclo_prefix}🚫 Agendamento {ag_id} ignorado (ano muito antigo: {data_ag_obj.year})")
                                continue
                        except (ValueError, TypeError):
                            pass  # Se não conseguir parsear, continua normal
                    
                    status_texto = obter_status_agendamento(ag)
                    status_upper = status_texto.upper() if status_texto else ""
                    
                    # BLOQUEIO GLOBAL: Ignora TUDO para este executor específico
                    id_executor = ag.get("idPessoaExecutor")
                    if id_executor == 21430526:
                        logger.debug(f"{ciclo_prefix}🚫 Agendamento {ag_id} ignorado (Bloqueio Global Profissional 21430526)")
                        continue

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

                        # PROTEÇÃO: Verifica rate limit antes de enviar
                        if not check_rate_limit(numero):
                            total_bloqueado_rate_limit += 1
                            logger.warning(
                                f"{ciclo_prefix}⚠️ RATE LIMIT ATINGIDO para {numero}\n"
                                f"   ID: {ag_id}\n"
                                f"   Cancelamento não enviado (muitas mensagens em 1h)\n"
                                f"{'='*70}\n"
                            )
                            continue

                        logger.info(
                            f"   📱 Telefone: {numero}\n"
                            f"   📋 Procedimentos: {procedimentos_texto}\n"
                            f"   📅 Data: {data_formatada or data_agenda} às {hora_agenda}\n"
                            f"{'-'*70}\n"
                            f"{ciclo_prefix}📤 Enviando notificação de cancelamento...\n"
                            f"{'-'*70}"
                        )

                        # TESTE: Verifica se é o número permitido para testes (só antes de enviar)
                        if NUMERO_TESTE:
                            numero_normalizado = normalizar_numero_para_comparacao(numero)
                            numero_teste_normalizado = normalizar_numero_para_comparacao(NUMERO_TESTE)
                            
                            if numero_normalizado != numero_teste_normalizado:
                                logger.info(
                                    f"{ciclo_prefix}🧪 TESTE: Cancelamento não enviado (número {numero} não é o número de teste)\n"
                                    f"   ID: {ag_id}\n"
                                    f"   Número recebido (normalizado): {numero_normalizado}\n"
                                    f"   Número de teste (normalizado): {numero_teste_normalizado}\n"
                                    f"   Mensagem montada mas não enviada\n"
                                    f"{'='*70}\n"
                                )
                                continue

                        # Monta dados para Aspa API
                        contact = montar_contact_object(primeiro_nome, numero)
                        params = montar_params_aspa_cancelamento(
                            procedimentos_texto,
                            data_formatada or data_agenda,
                            hora_agenda
                        )
                        
                        ok_cancel = enviar_mensagem(
                            numero=numero,
                            texto="",  # Não usado para Aspa
                            template_key=ASPA_TEMPLATE_CANCELAMENTO,
                            params=params,
                            contact=contact,
                            channel_id=ASPA_CHANNEL_ID
                        )

                        if ok_cancel:
                            mark_processed(ag_id, tipo='cancelamento')
                            register_rate_limit(numero)
                            increment_cycle_count()
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

                    # Inicializa variáveis de estado
                    eh_reagendamento = False
                    mudou_tipo_consulta = False
                    data_anterior = None
                    hora_anterior = None
                    id_tipo_consulta_anterior = None
                    cancelamento_previo = is_processed(ag_id, tipo='cancelamento')
                    ja_processado_agendamento = is_processed(ag_id, tipo='agendamento')
                    reativar_pos_cancelamento = False
                    
                    # Obtém idTipoConsulta atual do agendamento (sempre necessário)
                    id_tipo_consulta_atual = ag.get("idTipoConsulta")
                    
                    # Verifica se já foi processado e se houve reagendamento ou mudança de tipo
                    if ja_processado_agendamento:
                        # Busca a data/hora e tipo de consulta armazenados anteriormente
                        data_anterior, hora_anterior, id_tipo_consulta_anterior = get_processed_data(ag_id, tipo='agendamento')
                        
                        # Normaliza data e hora atual para comparação
                        data_atual_str = str(data_agenda).strip() if data_agenda != "N/A" else ""
                        hora_atual_str = str(hora_agenda).strip() if hora_agenda != "N/A" else ""
                        
                        # Verifica se houve reagendamento (data ou hora diferentes)
                        if data_anterior and hora_anterior:
                            data_anterior_str = str(data_anterior)
                            hora_anterior_str = str(hora_anterior)[:5]  # Apenas HH:MM para comparação
                            hora_atual_comparacao = hora_atual_str[:5] if len(hora_atual_str) >= 5 else hora_atual_str
                            
                            # PROTEÇÃO CRÍTICA: Verifica se as datas são realmente diferentes
                            # e se a mudança é válida (não é apenas diferença de ano sem mudança real)
                            if data_atual_str != data_anterior_str or hora_atual_comparacao != hora_anterior_str:
                                # Valida se a data atual não é muito antiga (proteção contra bugs)
                                try:
                                    data_atual_obj = datetime.datetime.strptime(data_atual_str, "%Y-%m-%d").date()
                                    hoje_validacao = datetime.date.today()
                                    
                                    # Ignora reagendamentos para o passado (possível erro de dados)
                                    if data_atual_obj < hoje_validacao:
                                        logger.warning(
                                            f"{ciclo_prefix}⚠️ Reagendamento ignorado (data no passado)\n"
                                            f"   ID: {ag_id}\n"
                                            f"   Data atual: {data_atual_str}\n"
                                            f"   Data anterior: {data_anterior_str}\n"
                                        )
                                        continue
                                    
                                    eh_reagendamento = True
                                except (ValueError, TypeError):
                                    # Se não conseguir validar, assume que é reagendamento
                                    eh_reagendamento = True
                        
                        # Verifica se mudou o tipo de consulta (apenas quando já existia um valor salvo)
                        # Isso evita tratar registros antigos (sem tipo salvo) como mudanças
                        tipo_anterior_int = None
                        tipo_atual_int = None
                        
                        if id_tipo_consulta_anterior is not None:
                            try:
                                tipo_anterior_int = int(str(id_tipo_consulta_anterior).strip())
                            except (ValueError, TypeError, AttributeError):
                                tipo_anterior_int = None
                        
                        if id_tipo_consulta_atual is not None:
                            try:
                                tipo_atual_int = int(str(id_tipo_consulta_atual).strip())
                            except (ValueError, TypeError, AttributeError):
                                tipo_atual_int = None
                        
                        if tipo_anterior_int is not None and tipo_atual_int is not None:
                            if tipo_anterior_int != tipo_atual_int:
                                mudou_tipo_consulta = True
                                logger.info(
                                    f"{ciclo_prefix}🔄 Mudança real de tipo de consulta detectada: "
                                    f"{tipo_anterior_int} → {tipo_atual_int}"
                                )

                        
                        if not eh_reagendamento and not mudou_tipo_consulta:
                            if cancelamento_previo:
                                reativar_pos_cancelamento = True
                                logger.info(
                                    f"\n{'='*70}\n"
                                    f"{ciclo_prefix}🔁 CONFIRMAÇÃO APÓS CANCELAMENTO\n"
                                    f"{'='*70}\n"
                                    f"   ID: {ag_id}\n"
                                    f"   Paciente: {nome_paciente}\n"
                                    f"   Situação: Cancelado anteriormente, reenviando confirmação\n"
                                    f"{'-'*70}"
                                )
                            else:
                                # Agendamento já processado sem mudanças
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
                        else:
                            # Detectou reagendamento ou mudança de tipo - log e continua processamento
                            if eh_reagendamento:
                                total_reagendamentos_detectados += 1
                                logger.info(
                                    f"\n{'='*70}\n"
                                    f"{ciclo_prefix}🔄 REAGENDAMENTO DETECTADO\n"
                                    f"{'='*70}\n"
                                    f"   ID: {ag_id}\n"
                                    f"   Paciente: {nome_paciente}\n"
                                    f"   Data/Hora anterior: {data_anterior} às {hora_anterior}\n"
                                    f"   Data/Hora nova: {data_agenda} às {hora_agenda}\n"
                                    f"{'-'*70}"
                                )
                            if mudou_tipo_consulta:
                                logger.info(
                                    f"\n{'='*70}\n"
                                    f"{ciclo_prefix}🔄 MUDANÇA DE TIPO DE CONSULTA DETECTADA\n"
                                    f"{'='*70}\n"
                                    f"   ID: {ag_id}\n"
                                    f"   Paciente: {nome_paciente}\n"
                                    f"   Tipo anterior: {id_tipo_consulta_anterior}\n"
                                    f"   Tipo atual: {id_tipo_consulta_atual}\n"
                                    f"   Ação: Reenviando confirmação com template apropriado\n"
                                    f"{'-'*70}"
                                )
                    
                    if not eh_reagendamento:
                        if reativar_pos_cancelamento:
                            logger.info(
                                f"\n{'='*70}\n"
                                f"{ciclo_prefix}📣 REATIVAÇÃO APÓS CANCELAMENTO\n"
                                f"{'='*70}\n"
                                f"   ID: {ag_id}\n"
                                f"   Paciente: {nome_paciente}\n"
                                f"   Data/Hora: {data_agenda} às {hora_agenda}\n"
                                f"   Ação: Enviando confirmação novamente para registro reconfirmado\n"
                                f"{'-'*70}"
                            )
                        else:
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
                            ENDERECO_PADRAO
                        )
                        
                        # Busca alias e telefone atualizados do paciente (via /paciente/{id})
                        alias_contato, numero = obter_dados_paciente_para_contato(ag)
                        
                        if not numero:
                            logger.warning(
                                f"{ciclo_prefix}⚠️  AVISO: Sem número de telefone válido\n"
                                f"   ⏭️  Agendamento ignorado (não será processado)\n"
                                f"{'='*70}\n"
                            )
                            continue
                        
                        # PROTEÇÃO: Verifica rate limit antes de enviar
                        if not check_rate_limit(numero):
                            total_bloqueado_rate_limit += 1
                            tipo_msg = "reagendamento" if eh_reagendamento else "confirmação"
                            logger.warning(
                                f"{ciclo_prefix}⚠️ RATE LIMIT ATINGIDO para {numero}\n"
                                f"   ID: {ag_id}\n"
                                f"   {tipo_msg.capitalize()} não enviada (muitas mensagens em 1h)\n"
                                f"{'='*70}\n"
                            )
                            continue
                        
                        # Formata data para formato brasileiro (DD/MM/YYYY)
                        data_formatada = formatar_data_brasileira(data_agenda)
                        
                        # Log detalhes do agendamento antes de enviar
                        tipo_msg = "reagendamento" if eh_reagendamento else "confirmação"
                        logger.info(
                            f"   📱 Telefone: {numero}\n"
                            f"   📋 Procedimentos: {procedimentos_texto}\n"
                            f"   📅 Data: {data_formatada} às {hora_agenda}\n"
                            f"{'-'*70}\n"
                            f"{ciclo_prefix}📤 Enviando mensagem de {tipo_msg}...\n"
                            f"{'-'*70}"
                        )

                        # TESTE: Verifica se é o número permitido para testes (só antes de enviar)
                        if NUMERO_TESTE:
                            numero_normalizado = normalizar_numero_para_comparacao(numero)
                            numero_teste_normalizado = normalizar_numero_para_comparacao(NUMERO_TESTE)
                            
                            if numero_normalizado != numero_teste_normalizado:
                                logger.info(
                                    f"{ciclo_prefix}🧪 TESTE: Confirmação não enviada (número {numero} não é o número de teste)\n"
                                    f"   ID: {ag_id}\n"
                                    f"   Número recebido (normalizado): {numero_normalizado}\n"
                                    f"   Número de teste (normalizado): {numero_teste_normalizado}\n"
                                    f"   Mensagem montada mas não enviada\n"
                                    f"{'='*70}\n"
                                )
                                continue
                        
                        # Monta dados para Aspa API
                        contact = montar_contact_object(alias_contato or primeiro_nome, numero)
                        
                        if eh_reagendamento:
                            # Reagendamento: procedimentos, data, hora, status, telefone
                            params = montar_params_aspa_reagendamento(
                                procedimentos_texto,
                                data_formatada,
                                hora_agenda,
                                status_texto or "REAGENDADO",
                                numero
                            )
                            template_key = ASPA_TEMPLATE_REAGENDAMENTO
                        else:
                            # Confirmação: data, hora, procedimentos, endereco
                            params = montar_params_aspa_confirmacao(
                                data_formatada,
                                hora_agenda,
                                procedimentos_texto,
                                endereco
                            )
                            # Verifica se é consulta ou outro tipo de agendamento
                            id_tipo_consulta = ag.get("idTipoConsulta")
                            # Se idTipoConsulta for igual a 113784, é consulta - usa template padrão
                            # Caso contrário (diferente ou None), usa template exclusivo
                            if id_tipo_consulta is not None and int(id_tipo_consulta) == ID_TIPO_CONSULTA:
                                # É consulta - usa template padrão
                                template_key = ASPA_TEMPLATE_CONFIRMACAO
                            else:
                                # Não é consulta - usa template exclusivo
                                template_key = ASPA_TEMPLATE_EXC_CONS
                                if not template_key:
                                    logger.warning(
                                        f"{ciclo_prefix}⚠️  AGENDAMENTO_EXC_CONS_MODEL_NAME não configurado, "
                                        f"usando AGENDAMENTO_MODEL_NAME como fallback\n"
                                        f"   ID: {ag_id}\n"
                                        f"   idTipoConsulta: {id_tipo_consulta}\n"
                                    )
                                    template_key = ASPA_TEMPLATE_CONFIRMACAO
                                else:
                                    logger.debug(
                                        f"{ciclo_prefix}📋 Usando template exclusivo (não-consulta) para agendamento\n"
                                        f"   ID: {ag_id}\n"
                                        f"   idTipoConsulta: {id_tipo_consulta}\n"
                                        f"   Template: {template_key}\n"
                                    )
                        
                        # Envia mensagem via Aspa API
                        ok = enviar_mensagem(
                            numero=numero,
                            texto="",  # Não usado para Aspa
                            template_key=template_key,
                            params=params,
                            contact=contact,
                            channel_id=ASPA_CHANNEL_ID
                        )
                        
                        if ok:
                            # Salva data/hora e tipo de consulta ao marcar como processado
                            tipo_processamento = 'agendamento'  # Sempre usa 'agendamento' para permitir detectar reagendamentos futuros
                            # id_tipo_consulta_atual já foi obtido anteriormente
                            mark_processed(ag_id, tipo=tipo_processamento, data_agenda=data_agenda, hora_agenda=hora_agenda, id_tipo_consulta=id_tipo_consulta_atual)
                            register_rate_limit(numero)
                            increment_cycle_count()
                            if cancelamento_previo:
                                removidos = clear_processed(ag_id, tipo='cancelamento')
                                if removidos:
                                    logger.info(
                                        f"{ciclo_prefix}♻️  Registro de cancelamento removido para permitir novas notificações futuras\n"
                                        f"   ID: {ag_id}\n"
                                        f"{'='*70}\n"
                                    )
                            total_processados += 1
                            if eh_reagendamento:
                                total_reagendamentos_enviados += 1
                            tipo_msg = "reagendamento" if eh_reagendamento else "confirmação"
                            logger.info(
                                f"{ciclo_prefix}✅ SUCESSO: Mensagem de {tipo_msg} enviada com sucesso!\n"
                                f"   📱 Destinatário: {numero}\n"
                                f"   ✅ Agendamento marcado como processado\n"
                                f"   📅 Data/Hora salva: {data_agenda} às {hora_agenda}\n"
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
            # PROTEÇÃO: Usa constante MAX_PAGINAS em vez de número hardcoded
            if pagina >= MAX_PAGINAS:
                logger.error(f"Limite de páginas excedido ({MAX_PAGINAS}), abortando")
                break
    
    logger.info("\n" + "=" * 70)
    logger.info(f"{ciclo_prefix}📊 RESUMO DO PROCESSAMENTO")
    logger.info("=" * 70)
    logger.info(f"{ciclo_prefix}📋 Novos agendamentos encontrados: {total_novos_encontrados}")
    logger.info(f"{ciclo_prefix}🔄 Reagendamentos detectados: {total_reagendamentos_detectados}")
    logger.info(f"{ciclo_prefix}⏭️  Agendamentos já processados: {total_ja_processados}")
    logger.info(f"{ciclo_prefix}✅ Confirmações/Reagendamentos enviados com sucesso: {total_processados}")
    logger.info(f"{ciclo_prefix}   └─ Reagendamentos enviados: {total_reagendamentos_enviados}")
    logger.info(f"{ciclo_prefix}❌ Falhas no envio (confirmações): {max(total_novos_encontrados + total_reagendamentos_detectados - total_processados, 0)}")
    logger.info("-" * 70)
    logger.info(f"{ciclo_prefix}🛑 Cancelamentos identificados: {total_cancelamentos_encontrados}")
    logger.info(f"{ciclo_prefix}⏭️  Cancelamentos já notificados: {total_cancelamentos_ja_processados}")
    logger.info(f"{ciclo_prefix}✅ Cancelamentos notificados nesta execução: {total_cancelamentos_notificados}")
    logger.info(f"{ciclo_prefix}⚠️ Cancelamentos ignorados por falta de dados: {total_cancelamentos_sem_dados}")
    logger.info(f"{ciclo_prefix}❌ Falhas ao enviar cancelamentos: {total_cancelamentos_falha_envio}")
    logger.info("-" * 70)
    logger.info(f"{ciclo_prefix}🛡️ PROTEÇÕES ATIVADAS:")
    logger.info(f"{ciclo_prefix}   └─ Bloqueados por rate limit: {total_bloqueado_rate_limit}")
    logger.info(f"{ciclo_prefix}   └─ IDs processados neste ciclo: {len(ids_processados_neste_ciclo)}")
    logger.info(f"{ciclo_prefix}   └─ Páginas processadas: {pagina + 1}")
    logger.info("=" * 70 + "\n")


def _obter_datetime_agendamento(ag):
    """
    Constrói um datetime do agendamento a partir de 'data' e 'horaInicio'/'hora'/'hora_inicio'.
    Retorna None se não for possível montar.
    """
    data_str = ag.get("data") or ag.get("dataAgenda")
    hora_str = (
        ag.get("horaInicio")
        or ag.get("hora")
        or ag.get("hora_inicio")
    )
    if not data_str or not hora_str:
        return None
    try:
        # Garante formato HH:MM
        hora_fmt = hora_str[:5] if len(hora_str) >= 5 else hora_str
        dt_str = f"{data_str} {hora_fmt}"
        return datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def processar_lembretes(ciclo_numero=None):
    """
    Processa e envia lembretes configurados (USG, Duoglide, Depilação e padrão).
    
    - Apenas status que contenham 'CONFIRMADO'
    - Lembretes são enviados apenas até às 10h da manhã do dia anterior ao agendamento
    - Cada configuração define quantos dias antes enviar (ex.: 1 dia para 24h, 3 dias para 72h)
    - Evita duplicidade por tipo de lembrete usando a tabela processed
    """
    if not any([
        ASPA_TEMPLATE_LEMBRETE_PADRAO,
        ASPA_TEMPLATE_LEMBRETE_DEPILACAO,
        ASPA_TEMPLATE_LEMBRETE_USG,
        ASPA_TEMPLATE_LEMBRETE_DUOGLIDE,
    ]):
        return
    
    ciclo_prefix = f"[CICLO #{ciclo_numero}] " if ciclo_numero else ""
    
    agora = datetime.datetime.now()
    hora_atual = agora.hour
    
    # Verifica se está antes das 10h da manhã
    if hora_atual >= 10:
        logger.info("=" * 70)
        logger.info(f"{ciclo_prefix}🔔 PROCESSAMENTO DE LEMBRETES PULADO")
        logger.info(f"{ciclo_prefix}Hora atual: {hora_atual:02d}:{agora.minute:02d}")
        logger.info(f"{ciclo_prefix}Lembretes só são enviados até às 10h da manhã")
        logger.info("=" * 70)
        return
    
    # Janela de busca cobre até 3 dias para alcançar lembretes de 72h (Duoglide)
    data_inicial = agora.date().isoformat()
    data_final = (agora.date() + datetime.timedelta(days=3)).isoformat()
    
    logger.info("=" * 70)
    logger.info(f"{ciclo_prefix}🔔 INICIANDO PROCESSAMENTO DE LEMBRETES")
    logger.info(f"{ciclo_prefix}Hora atual: {hora_atual:02d}:{agora.minute:02d} (antes das 10h - OK para enviar)")
    logger.info(f"{ciclo_prefix}Período de busca: {data_inicial} a {data_final}")
    logger.info("=" * 70)
    
    from api_client import fetch_agendamentos
    from storage import is_processed, mark_processed
    
    lembrete_configs = [
        {
            "nome": "lembrete_duoglide",
            "descricao": "Laser Duoglide (3 dias antes)",
            "template": ASPA_TEMPLATE_LEMBRETE_DUOGLIDE,
            "predicate": eh_duoglide,
            "dias_antes": 3,  # 3 dias antes = 72h antes
            "params_builder": lambda data_formatada, hora_agenda, procedimentos_texto: montar_params_aspa_lembrete_dia_hora(data_formatada, hora_agenda),
        },
        {
            "nome": "lembrete_usg",
            "descricao": "USG Abdômen (1 dia antes)",
            "template": ASPA_TEMPLATE_LEMBRETE_USG,
            "predicate": eh_usg_abdomen,
            "dias_antes": 1,  # 1 dia antes = 24h antes
            "params_builder": lambda data_formatada, hora_agenda, procedimentos_texto: montar_params_aspa_lembrete_dia_hora(data_formatada, hora_agenda),
        },
        {
            "nome": "lembrete_depilacao",
            "descricao": "Depilação a Laser (1 dia antes)",
            "template": ASPA_TEMPLATE_LEMBRETE_DEPILACAO,
            "predicate": eh_depilacao_laser,
            "dias_antes": 1,  # 1 dia antes = 24h antes
            "params_builder": lambda data_formatada, hora_agenda, procedimentos_texto: montar_params_aspa_lembrete_depilacao(),
        },
        {
            "nome": "lembrete_padrao",
            "descricao": "Padrão (1 dia antes)",
            "template": ASPA_TEMPLATE_LEMBRETE_PADRAO,
            "predicate": lambda ag: True,
            "dias_antes": 1,  # 1 dia antes = 24h antes
            "params_builder": montar_params_aspa_lembrete_padrao,
        },
    ]
    descricao_por_tipo = {cfg["nome"]: cfg["descricao"] for cfg in lembrete_configs}
    
    pagina = 0
    total_lembretes_enviados = 0
    total_ja_processados = 0
    total_ignorados = 0
    total_bloqueado_rate_limit = 0
    contagem_por_tipo = {}
    
    # PROTEÇÃO: Conjunto de IDs já processados neste ciclo para evitar duplicatas
    ids_processados_neste_ciclo = set()
    
    while True:
        # PROTEÇÃO: Limite de paginação para evitar loop infinito
        if pagina >= MAX_PAGINAS:
            logger.warning(f"{ciclo_prefix}⚠️ LIMITE DE PAGINAÇÃO ATINGIDO ({MAX_PAGINAS} páginas) para lembretes")
            break
        
        try:
            resp = fetch_agendamentos(data_inicial, data_final, pagina=pagina)
            if not resp:
                break
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
                    
                    # PROTEÇÃO: Evita processar o mesmo ID duas vezes no mesmo ciclo
                    if ag_id in ids_processados_neste_ciclo:
                        logger.debug(f"{ciclo_prefix}⏭️ ID {ag_id} já processado neste ciclo de lembretes")
                        continue
                    ids_processados_neste_ciclo.add(ag_id)
                    
                    status_texto = obter_status_agendamento(ag)
                    status_upper = status_texto.upper() if status_texto else ""
                    if "CONFIRMADO" not in status_upper:
                        total_ignorados += 1
                        continue
                    
                    # BLOQUEIO GLOBAL: Ignora TUDO para este executor específico
                    id_executor = ag.get("idPessoaExecutor")
                    if id_executor == 21430526:
                        total_ignorados += 1
                        logger.debug(f"{ciclo_prefix}🚫 Lembrete para agendamento {ag_id} ignorado (Bloqueio Global Profissional 21430526)")
                        continue
                    
                    dt_ag = _obter_datetime_agendamento(ag)
                    if not dt_ag:
                        total_ignorados += 1
                        continue
                    
                    # PROTEÇÃO CRÍTICA: Verifica se o agendamento está no futuro
                    # Essa verificação DEVE vir ANTES de qualquer outra para evitar loops infinitos
                    if dt_ag <= agora:
                        total_ignorados += 1
                        continue
                    
                    # PROTEÇÃO: Ignora agendamentos muito distantes (mais de 1 ano)
                    # Isso evita processar datas incorretas ou problemas de comparação
                    data_limite_futuro = agora + datetime.timedelta(days=365)
                    if dt_ag > data_limite_futuro:
                        total_ignorados += 1
                        logger.debug(f"{ciclo_prefix}Agendamento {ag_id} ignorado (data muito distante: {dt_ag})")
                        continue
                    
                    # PROTEÇÃO: Verifica se o agendamento é do ano atual ou futuro
                    # Isso evita processar agendamentos antigos na virada do ano
                    if dt_ag.year < agora.year:
                        total_ignorados += 1
                        logger.debug(f"{ciclo_prefix}Agendamento {ag_id} ignorado (ano anterior: {dt_ag.year})")
                        continue
                    
                    # Determina qual tipo de lembrete aplicar
                    config_selecionada = None
                    for cfg in lembrete_configs:
                        template_cfg = cfg.get("template")
                        if not template_cfg:
                            continue
                        predicate = cfg.get("predicate")
                        if predicate and not predicate(ag):
                            continue
                        
                        # Verifica se o agendamento está na data correta (hoje + dias_antes)
                        dias_antes = cfg.get("dias_antes", 1)
                        data_alvo_lembrete = agora.date() + datetime.timedelta(days=dias_antes)
                        
                        # CORREÇÃO CRÍTICA: Compara com ano explícito para evitar bugs na virada do ano
                        # Exemplo: 2024-01-02 != 2025-01-02 (anos diferentes)
                        if dt_ag.date() == data_alvo_lembrete and dt_ag.year == data_alvo_lembrete.year:
                            config_selecionada = cfg
                            break
                    
                    if not config_selecionada:
                        total_ignorados += 1
                        continue
                    
                    tipo_lembrete = config_selecionada["nome"]
                    template_key = config_selecionada["template"]
                    
                    if is_processed(ag_id, tipo=tipo_lembrete):
                        total_ja_processados += 1
                        continue
                    
                    nome_paciente = (
                        ag.get("paciente_nome") or
                        ag.get("nomePaciente") or
                        ag.get("primeiro_nome_do_paciente") or
                        ag.get("pacienteNome") or
                        "N/A"
                    )
                    nome_completo = nome_paciente if nome_paciente != "N/A" else ""
                    primeiro_nome = extrair_primeiro_nome(nome_completo) or "Paciente"
                    
                    data_agenda = ag.get("data") or ag.get("dataAgenda") or ""
                    hora_agenda = (
                        ag.get("horaInicio") or
                        ag.get("hora") or
                        ag.get("hora_inicio") or
                        ""
                    )
                    alias_contato, numero = obter_dados_paciente_para_contato(ag)
                    if not numero:
                        total_ignorados += 1
                        continue
                    
                    # PROTEÇÃO: Verifica rate limit antes de enviar
                    if not check_rate_limit(numero):
                        total_bloqueado_rate_limit += 1
                        logger.warning(
                            f"{ciclo_prefix}⚠️ RATE LIMIT ATINGIDO para {numero}\n"
                            f"   ID: {ag_id}\n"
                            f"   Lembrete não enviado (muitas mensagens em 1h)\n"
                        )
                        continue
                    
                    data_formatada = formatar_data_brasileira(data_agenda)
                    procedimentos_texto = obter_procedimentos_texto(ag)
                    
                    # TESTE: Verifica se é o número permitido para testes (só antes de enviar)
                    if NUMERO_TESTE:
                        numero_normalizado = normalizar_numero_para_comparacao(numero)
                        numero_teste_normalizado = normalizar_numero_para_comparacao(NUMERO_TESTE)
                        if numero_normalizado != numero_teste_normalizado:
                            total_ignorados += 1
                            continue
                    
                    contact = montar_contact_object(alias_contato or primeiro_nome, numero)
                    params = config_selecionada["params_builder"](data_formatada, hora_agenda, procedimentos_texto)
                    
                    logger.info(
                        f"{ciclo_prefix}🔔 Enviando lembrete ({descricao_por_tipo.get(tipo_lembrete, tipo_lembrete)}) para {numero}\n"
                        f"   ID: {ag_id}\n"
                        f"   Data/Hora: {data_formatada} às {hora_agenda}\n"
                        f"   Procedimentos: {procedimentos_texto}\n"
                    )
                    
                    ok = enviar_mensagem(
                        numero=numero,
                        texto="",
                        template_key=template_key,
                        params=params,
                        contact=contact,
                        channel_id=ASPA_CHANNEL_ID,
                    )
                    
                    if ok:
                        mark_processed(
                            ag_id,
                            tipo=tipo_lembrete,
                            data_agenda=data_agenda,
                            hora_agenda=hora_agenda,
                            id_tipo_consulta=ag.get("idTipoConsulta"),
                        )
                        register_rate_limit(numero)
                        increment_cycle_count()
                        total_lembretes_enviados += 1
                        contagem_por_tipo[tipo_lembrete] = contagem_por_tipo.get(tipo_lembrete, 0) + 1
                        logger.info(
                            f"{ciclo_prefix}✅ Lembrete enviado e marcado como processado ({tipo_lembrete})\n"
                            f"   ID: {ag_id}\n"
                        )
                    else:
                        logger.warning(
                            f"{ciclo_prefix}❌ Falha ao enviar lembrete ({tipo_lembrete}) para {numero} (ID {ag_id})"
                        )
            
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
        except Exception as e:
            logger.error(f"{ciclo_prefix}Erro ao processar lembretes na página {pagina}: {e}", exc_info=True)
            pagina += 1
            if pagina >= MAX_PAGINAS:
                logger.error(f"{ciclo_prefix}Limite de páginas excedido ({MAX_PAGINAS}) ao processar lembretes, abortando")
                break
    
    logger.info(f"{ciclo_prefix}🔔 LEMBRETES - enviados: {total_lembretes_enviados}, já processados: {total_ja_processados}, ignorados: {total_ignorados}")
    logger.info(f"{ciclo_prefix}   └─ Bloqueados por rate limit: {total_bloqueado_rate_limit}")
    if contagem_por_tipo:
        logger.info(f"{ciclo_prefix}   Detalhe por tipo:")
        for cfg in lembrete_configs:
            tipo = cfg["nome"]
            if tipo in contagem_por_tipo:
                logger.info(
                    f"{ciclo_prefix}     - {descricao_por_tipo.get(tipo, tipo)}: {contagem_por_tipo[tipo]}"
                )

if __name__ == "__main__":
    init_db()
    # Por padrão processa hoje
    hoje = datetime.date.today().isoformat()
    processar_intervalo(hoje, hoje)

