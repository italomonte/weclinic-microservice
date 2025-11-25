import os
import requests
from dotenv import load_dotenv
import logging
import time
import json
import shlex

load_dotenv()

logger = logging.getLogger(__name__)

SENDER_API_URL = os.getenv("SENDER_API_URL")
SENDER_AUTH = os.getenv("SENDER_AUTH")
SENDER_PROVIDER = os.getenv("SENDER_PROVIDER", "generic").lower()  # generic, evolution, whatsapp_cloud, aspa
MAX_RETRIES = int(os.getenv("SENDER_MAX_RETRIES", "3"))  # Número de tentativas em caso de erro
RETRY_DELAY = float(os.getenv("SENDER_RETRY_DELAY", "2"))  # Segundos entre tentativas

# ASPA_KEY é usado na URL após /template/
ASPA_KEY = os.getenv("ASPA_KEY")
# ASPA_TOKEN é o token de autenticação para Aspa API
ASPA_TOKEN = os.getenv("ASPA_TOKEN")


def _formatar_numero_evolution(numero):
    """
    Formata número para Evolution API.
    Evolution API espera número com código do país sem caracteres especiais.
    Exemplo: 5511999999999
    
    Formato esperado:
    - Brasil: 55 + DDD (2 dígitos) + número (9 dígitos para celular, 8 para fixo)
    - Total: 13 dígitos (celular) ou 12 dígitos (fixo)
    """
    # Remove todos os caracteres não numéricos
    numero_limpo = "".join([c for c in str(numero) if c.isdigit()])
    
    # Se já começa com 55, retorna como está (já está formatado)
    if numero_limpo.startswith("55"):
        return numero_limpo
    
    # Se não começa com código do país
    # Números brasileiros podem ter:
    # - 11 dígitos: DDD (2) + celular com 9 (9xxxxxxxxx)
    # - 10 dígitos: DDD (2) + celular antigo com 8 (8xxxxxxx) ou fixo (3xxxxxxx)
    
    if len(numero_limpo) in (10, 11):
        # Adiciona código do país Brasil (55)
        numero_limpo = "55" + numero_limpo
    elif len(numero_limpo) < 10:
        # Número muito curto, pode estar incompleto
        logger.warning(f"Número muito curto após limpeza: {numero_limpo}, original: {numero}")
        # Tenta adicionar 55 mesmo assim se tiver pelo menos 8 dígitos
        if len(numero_limpo) >= 8:
            numero_limpo = "55" + numero_limpo
    
    return numero_limpo


def _montar_payload_evolution(numero, texto):
    """
    Monta payload para Evolution API.
    Evolution API espera 'text' diretamente no nível raiz, não aninhado.
    
    Formato esperado:
    {
        "number": "5511999999999",
        "text": "mensagem"
    }
    """
    numero_formatado = _formatar_numero_evolution(numero)
    
    # Validação do número formatado
    if not numero_formatado or len(numero_formatado) < 10:
        logger.warning(f"Número formatado inválido para Evolution API: {numero_formatado} (original: {numero})")
    
    # Validação do texto
    if not texto or not texto.strip():
        logger.warning(f"Texto vazio ou inválido para Evolution API")
        texto = ""
    
    return {
        "number": numero_formatado,
        "text": texto
    }


def _montar_headers_evolution():
    """
    Monta headers para Evolution API.
    Evolution API pode usar apikey, Bearer, ou ambas.
    """
    headers = {
        "Content-Type": "application/json"
    }
    
    if SENDER_AUTH:
        # Evolution pode usar apikey ou Bearer
        if SENDER_AUTH.startswith("Bearer "):
            headers["Authorization"] = SENDER_AUTH
        else:
            # Se não começa com Bearer, assume que é a API key
            # Tenta com apikey primeiro, mas também pode precisar de Bearer
            headers["apikey"] = SENDER_AUTH
            # Algumas versões da Evolution também aceitam Bearer com a mesma key
            headers["Authorization"] = f"Bearer {SENDER_AUTH}"
    
    return headers


def _montar_payload_whatsapp_cloud(numero, texto):
    """
    Monta payload para WhatsApp Cloud API.
    """
    numero_formatado = "".join([c for c in str(numero) if c.isdigit()])
    return {
        "messaging_product": "whatsapp",
        "to": numero_formatado,
        "type": "text",
        "text": {
            "body": texto
        }
    }


def _montar_headers_whatsapp_cloud():
    """
    Monta headers para WhatsApp Cloud API.
    """
    return {
        "Authorization": SENDER_AUTH,
        "Content-Type": "application/json"
    }


def _montar_payload_generic(numero, texto):
    """
    Monta payload genérico.
    """
    return {
        "to": numero,
        "text": texto
    }


def _montar_headers_generic():
    """
    Monta headers genérico.
    """
    headers = {
        "Content-Type": "application/json"
    }
    if SENDER_AUTH:
        headers["Authorization"] = SENDER_AUTH
    return headers


def _formatar_numero_aspa(numero):
    """
    Formata número para Aspa API.
    Aspa espera número no formato internacional sem caracteres especiais.
    Exemplo: 5592984532273 (55 + DDD + número)
    
    Formato esperado:
    - Brasil: 55 + DDD (2 dígitos) + número (9 dígitos para celular, 8 para fixo)
    - Total: 13 dígitos (celular) ou 12 dígitos (fixo)
    """
    # Remove todos os caracteres não numéricos
    numero_limpo = "".join([c for c in str(numero) if c.isdigit()])
    
    # Se já começa com 55, retorna como está
    if numero_limpo.startswith("55"):
        return numero_limpo
    
    # Se não começa com código do país
    # Números brasileiros podem ter:
    # - 11 dígitos: DDD (2) + celular com 9 (9xxxxxxxxx)
    # - 10 dígitos: DDD (2) + celular antigo com 8 (8xxxxxxx) ou fixo (3xxxxxxx)
    
    if len(numero_limpo) in (10, 11):
        # Adiciona código do país Brasil (55)
        numero_limpo = "55" + numero_limpo
    elif len(numero_limpo) < 10:
        # Número muito curto, pode estar incompleto
        logger.warning(f"Número muito curto para Aspa: {numero_limpo}, original: {numero}")
        # Tenta adicionar 55 mesmo assim se tiver pelo menos 8 dígitos
        if len(numero_limpo) >= 8:
            numero_limpo = "55" + numero_limpo
    
    return numero_limpo


def _montar_payload_aspa(contact, params, channel_id, template_key):
    """
    Monta payload para Aspa API.
    
    Args:
        contact: Objeto com alias, phone, update
        params: Dicionário com estrutura {content: {...}} ou {header: {}, content: {}, buttons: {}}
        channel_id: ID do canal da empresa na Aspa
        template_key: Chave do template/modelo cadastrado na Aspa
    
    Returns:
        Payload formatado para a API da Aspa
    """
    # Simplifica params se tiver apenas content (remove header e buttons vazios)
    params_simplificado = params.copy()
    if "header" in params_simplificado and not params_simplificado.get("header"):
        params_simplificado.pop("header", None)
    if "buttons" in params_simplificado and not params_simplificado.get("buttons"):
        params_simplificado.pop("buttons", None)
    
    payload = {
        "contact": contact,
        "channel": channel_id,  # Aspa usa "channel", não "channel_id"
        "template": template_key,  # Template também vai no body
        "params": params_simplificado
    }
    
    return payload


def _montar_headers_aspa():
    """
    Monta headers para Aspa API.
    Aspa usa Bearer token na autenticação (ASPA_TOKEN).
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    if ASPA_TOKEN:
        # Aspa sempre usa ASPA_TOKEN como Bearer token
        if ASPA_TOKEN.startswith("Bearer "):
            headers["Authorization"] = ASPA_TOKEN
        else:
            headers["Authorization"] = f"Bearer {ASPA_TOKEN}"
    
    return headers


def _gerar_curl_comando(url, headers, payload):
    """
    Gera comando curl equivalente à requisição feita com dados reais.
    
    Args:
        url: URL completa da requisição
        headers: Dicionário com headers
        payload: Dicionário com payload JSON
    
    Returns:
        String com comando curl formatado e pronto para copiar/colar
    """
    # Monta comando curl
    curl_parts = ["curl", "-X", "POST"]
    
    # Adiciona URL
    curl_parts.append(shlex.quote(url))
    
    # Adiciona headers
    for key, value in headers.items():
        curl_parts.append("-H")
        curl_parts.append(shlex.quote(f"{key}: {value}"))
    
    # Adiciona body JSON (formata com indentação para legibilidade)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    curl_parts.append("-d")
    curl_parts.append(shlex.quote(payload_json))
    
    # Formata com quebras de linha para melhor legibilidade
    curl_cmd = " \\\n  ".join(curl_parts)
    
    return curl_cmd


def enviar_mensagem_aspa(contact, params, channel_id, template_key):
    """
    Envia mensagem via Aspa API usando templates.
    
    Args:
        contact: Objeto com alias, phone, update
        params: Dicionário com estrutura {header: {}, content: {}, buttons: {}}
        channel_id: ID do canal da empresa na Aspa
        template_key: Chave do template/modelo cadastrado na Aspa
    
    Returns:
        True se enviado com sucesso, False caso contrário
    """
    if not SENDER_API_URL:
        logger.error("SENDER_API_URL não configurado")
        raise RuntimeError("SENDER_API_URL não configurado")
    
    if not template_key:
        logger.error("template_key é obrigatório para Aspa API")
        return False
    
    if not channel_id:
        logger.error("channel_id é obrigatório para Aspa API")
        return False
    
    if not ASPA_KEY:
        logger.error("ASPA_KEY é obrigatório para Aspa API (usado na URL)")
        return False
    
    if not ASPA_TOKEN:
        logger.error("ASPA_TOKEN é obrigatório para Aspa API (usado no Bearer token)")
        return False
    
    if not contact or not contact.get("phone"):
        logger.warning(f"Tentativa de enviar mensagem sem número válido")
        return False
    
    # Formata número do contact se necessário
    if contact.get("phone"):
        contact["phone"] = _formatar_numero_aspa(contact["phone"])
    
    payload = _montar_payload_aspa(contact, params, channel_id, template_key)
    headers = _montar_headers_aspa()
    
    # URL da Aspa: https://api.aspa.app/v2.0/message/template/{ASPA_KEY}
    # SENDER_API_URL deve ser apenas a base: https://api.aspa.app/v2.0
    # ASPA_KEY vai na URL, template_key vai no body como "template"
    url = f"{SENDER_API_URL.rstrip('/')}/message/template/{ASPA_KEY}"
    
    logger.debug(f"Payload Aspa: {payload}")
    logger.debug(f"Headers Aspa: {headers}")
    logger.debug(f"URL Aspa: {url}")
    
    RETRYABLE_STATUS_CODES = (500, 502, 503, 504, 429)
    
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            logger.debug(f"Enviando mensagem via Aspa para {contact.get('phone')} (tentativa {tentativa}/{MAX_RETRIES})")
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=20
            )
            
            if resp.status_code in (200, 201, 202):
                logger.info(f"Mensagem enviada com sucesso via Aspa para {contact.get('phone')}")
                return True
            elif resp.status_code in RETRYABLE_STATUS_CODES:
                if tentativa < MAX_RETRIES:
                    logger.warning(
                        f"Erro temporário ao enviar via Aspa para {contact.get('phone')}: status {resp.status_code}, "
                        f"tentando novamente em {RETRY_DELAY}s (tentativa {tentativa}/{MAX_RETRIES})"
                    )
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    curl_cmd = _gerar_curl_comando(url, headers, payload)
                    logger.error(
                        f"❌ Erro ao enviar mensagem via Aspa para {contact.get('phone')} após {MAX_RETRIES} tentativas:\n"
                        f"   Status: {resp.status_code}\n"
                        f"   Resposta: {resp.text[:200]}\n"
                        f"\n📋 Comando cURL para testar:\n{curl_cmd}"
                    )
                    return False
            elif resp.status_code == 400:
                try:
                    resposta_json = resp.json()
                except:
                    resposta_json = resp.text
                
                curl_cmd = _gerar_curl_comando(url, headers, payload)
                logger.error(
                    f"❌ ERRO 400 (Bad Request) ao enviar via Aspa para {contact.get('phone')}:\n"
                    f"   URL: {url}\n"
                    f"   Template Key: {template_key}\n"
                    f"   Resposta da API: {json.dumps(resposta_json, indent=2, ensure_ascii=False) if isinstance(resposta_json, dict) else resposta_json}\n"
                    f"\n📋 Comando cURL para testar (com dados reais):\n{curl_cmd}\n"
                    f"\n⚠️  Verifique:\n"
                    f"      - Template key está correto?\n"
                    f"      - Parâmetros do template estão corretos?\n"
                    f"      - Channel ID está correto?\n"
                    f"      - Número está formatado corretamente?\n"
                    f"      - Autenticação está válida?"
                )
                return False
            else:
                curl_cmd = _gerar_curl_comando(url, headers, payload)
                try:
                    resposta_json = resp.json()
                    resposta_str = json.dumps(resposta_json, indent=2, ensure_ascii=False)
                except:
                    resposta_str = resp.text[:500]
                
                logger.error(
                    f"❌ Erro ao enviar mensagem via Aspa para {contact.get('phone')}:\n"
                    f"   Status: {resp.status_code}\n"
                    f"   Resposta: {resposta_str}\n"
                    f"\n📋 Comando cURL para testar (com dados reais):\n{curl_cmd}"
                )
                return False
                
        except requests.exceptions.Timeout:
            if tentativa < MAX_RETRIES:
                logger.warning(
                    f"Timeout ao enviar via Aspa para {contact.get('phone')}, tentando novamente em {RETRY_DELAY}s "
                    f"(tentativa {tentativa}/{MAX_RETRIES})"
                )
                time.sleep(RETRY_DELAY)
                continue
            else:
                curl_cmd = _gerar_curl_comando(url, headers, payload)
                logger.error(
                    f"❌ Timeout ao enviar mensagem via Aspa para {contact.get('phone')} após {MAX_RETRIES} tentativas\n"
                    f"\n📋 Comando cURL para testar (com dados reais):\n{curl_cmd}"
                )
                return False
                
        except requests.exceptions.ConnectionError as e:
            if tentativa < MAX_RETRIES:
                logger.warning(
                    f"Erro de conexão ao enviar via Aspa para {contact.get('phone')}, tentando novamente em {RETRY_DELAY}s "
                    f"(tentativa {tentativa}/{MAX_RETRIES}): {str(e)[:100]}"
                )
                time.sleep(RETRY_DELAY)
                continue
            else:
                curl_cmd = _gerar_curl_comando(url, headers, payload)
                logger.error(
                    f"❌ Erro de conexão ao enviar mensagem via Aspa para {contact.get('phone')} após {MAX_RETRIES} tentativas: {e}\n"
                    f"\n📋 Comando cURL para testar (com dados reais):\n{curl_cmd}"
                )
                return False
                
        except requests.exceptions.RequestException as e:
            curl_cmd = _gerar_curl_comando(url, headers, payload)
            logger.error(
                f"❌ Exceção ao enviar mensagem via Aspa para {contact.get('phone')}: {e}\n"
                f"\n📋 Comando cURL para testar (com dados reais):\n{curl_cmd}"
            )
            return False
    
    return False


def enviar_mensagem(numero, texto, template_key=None, params=None, contact=None, channel_id=None):
    """
    Envia uma mensagem via provedor configurável.
    
    Suporta:
    - Aspa API (provider="aspa") - usa templates com parâmetros dinâmicos
    - Evolution API (provider="evolution")
    - WhatsApp Cloud API (provider="whatsapp_cloud")
    - Provedor genérico (provider="generic" ou não especificado)
    
    Configure SENDER_PROVIDER no .env para escolher o provedor.
    
    Args:
        numero: Número de telefone do destinatário
        texto: Texto da mensagem a ser enviada (não usado para Aspa, apenas para outros providers)
        template_key: (Opcional, apenas Aspa) Chave do template/modelo cadastrado na Aspa
        params: (Opcional, apenas Aspa) Dicionário com estrutura {header: {}, content: {}, buttons: {}}
        contact: (Opcional, apenas Aspa) Objeto com alias, phone, update
        channel_id: (Opcional, apenas Aspa) ID do canal da empresa na Aspa
        
    Returns:
        True se enviado com sucesso, False caso contrário
    """
    # Se for Aspa, usa função específica
    if SENDER_PROVIDER == "aspa":
        # Obtém channel_id do .env se não foi passado
        if not channel_id:
            channel_id = os.getenv("ASPA_CHANNEL")
        
        # Se não tem contact, cria um básico com o número fornecido
        if not contact:
            contact = {
                "alias": "Italo",
                "phone": numero,
                "update": True
            }
        
        # Se não tem params, cria estrutura vazia (apenas content)
        if not params:
            params = {
                "content": {}
            }
        
        if not template_key:
            logger.error("template_key é obrigatório para Aspa API")
            return False
        
        if not channel_id:
            logger.error("channel_id (ASPA_CHANNEL) é obrigatório para Aspa API")
            return False
        
        return enviar_mensagem_aspa(contact, params, channel_id, template_key)
    
    # Para outros provedores, mantém lógica existente
    if not SENDER_API_URL:
        logger.error("SENDER_API_URL não configurado")
        raise RuntimeError("SENDER_API_URL não configurado")
    
    if not numero or not texto:
        logger.warning(f"Tentativa de enviar mensagem com dados inválidos: numero={numero}, texto={texto[:50] if texto else None}")
        return False
    
    # Monta payload e headers conforme o provedor
    if SENDER_PROVIDER == "evolution":
        payload = _montar_payload_evolution(numero, texto)
        headers = _montar_headers_evolution()
    elif SENDER_PROVIDER == "whatsapp_cloud":
        payload = _montar_payload_whatsapp_cloud(numero, texto)
        headers = _montar_headers_whatsapp_cloud()
    else:  # generic
        payload = _montar_payload_generic(numero, texto)
        headers = _montar_headers_generic()
    
    # Log detalhado do que será enviado
    logger.debug(f"Payload: {payload}")
    logger.debug(f"Headers: {headers}")
    logger.debug(f"URL: {SENDER_API_URL}")
    
    # Códigos HTTP que devem ser tentados novamente (erros temporários)
    RETRYABLE_STATUS_CODES = (500, 502, 503, 504, 429)
    
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            logger.debug(f"Enviando mensagem para {numero} via {SENDER_PROVIDER} (tentativa {tentativa}/{MAX_RETRIES})")
            resp = requests.post(
                SENDER_API_URL,
                json=payload,
                headers=headers,
                timeout=20  # Aumentado para 20 segundos
            )
            
            if resp.status_code in (200, 201, 202):
                logger.info(f"Mensagem enviada com sucesso para {numero}")
                return True
            elif resp.status_code in RETRYABLE_STATUS_CODES:
                # Erro temporário - tenta novamente
                if tentativa < MAX_RETRIES:
                    logger.warning(
                        f"Erro temporário ao enviar para {numero}: status {resp.status_code}, "
                        f"tentando novamente em {RETRY_DELAY}s (tentativa {tentativa}/{MAX_RETRIES})"
                    )
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    # Última tentativa falhou
                    logger.error(
                        f"Erro ao enviar mensagem para {numero} após {MAX_RETRIES} tentativas: "
                        f"status {resp.status_code}, resposta: {resp.text[:200]}"
                    )
                    return False
            elif resp.status_code == 400:
                # Bad Request - log detalhado para debug
                import json
                try:
                    resposta_json = resp.json()
                except:
                    resposta_json = resp.text
                
                logger.error(
                    f"❌ ERRO 400 (Bad Request) ao enviar mensagem para {numero}:\n"
                    f"   URL: {SENDER_API_URL}\n"
                    f"   Provider: {SENDER_PROVIDER}\n"
                    f"   Payload enviado: {json.dumps(payload, indent=2, ensure_ascii=False)}\n"
                    f"   Headers enviados: {json.dumps(headers, indent=2)}\n"
                    f"   Resposta da API: {json.dumps(resposta_json, indent=2, ensure_ascii=False) if isinstance(resposta_json, dict) else resposta_json}\n"
                    f"   ⚠️  Verifique:\n"
                    f"      - Formato do payload está correto?\n"
                    f"      - Número está formatado corretamente? ({payload.get('number', 'N/A')})\n"
                    f"      - Instância está conectada no Evolution API?\n"
                    f"      - URL está correta? (deve incluir nome da instância)\n"
                    f"      - Autenticação está válida?"
                )
                return False
            else:
                # Erro permanente (4xx, outros 5xx)
                logger.error(
                    f"Erro ao enviar mensagem para {numero}: status {resp.status_code}, "
                    f"resposta: {resp.text[:200]}"
                )
                return False
                
        except requests.exceptions.Timeout:
            if tentativa < MAX_RETRIES:
                logger.warning(
                    f"Timeout ao enviar para {numero}, tentando novamente em {RETRY_DELAY}s "
                    f"(tentativa {tentativa}/{MAX_RETRIES})"
                )
                time.sleep(RETRY_DELAY)
                continue
            else:
                logger.error(f"Timeout ao enviar mensagem para {numero} após {MAX_RETRIES} tentativas")
                return False
                
        except requests.exceptions.ConnectionError as e:
            if tentativa < MAX_RETRIES:
                logger.warning(
                    f"Erro de conexão ao enviar para {numero}, tentando novamente em {RETRY_DELAY}s "
                    f"(tentativa {tentativa}/{MAX_RETRIES}): {str(e)[:100]}"
                )
                time.sleep(RETRY_DELAY)
                continue
            else:
                logger.error(f"Erro de conexão ao enviar mensagem para {numero} após {MAX_RETRIES} tentativas: {e}")
                return False
                
        except requests.exceptions.RequestException as e:
            # Outros erros - não tenta novamente
            logger.error(f"Exceção ao enviar mensagem para {numero}: {e}")
            return False
    
    return False

