import os
import requests
from dotenv import load_dotenv
import logging
import time

load_dotenv()

logger = logging.getLogger(__name__)

SENDER_API_URL = os.getenv("SENDER_API_URL")
SENDER_AUTH = os.getenv("SENDER_AUTH")
SENDER_PROVIDER = os.getenv("SENDER_PROVIDER", "generic").lower()  # generic, evolution, whatsapp_cloud
MAX_RETRIES = int(os.getenv("SENDER_MAX_RETRIES", "3"))  # Número de tentativas em caso de erro
RETRY_DELAY = float(os.getenv("SENDER_RETRY_DELAY", "2"))  # Segundos entre tentativas


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


def enviar_mensagem(numero, texto):
    """
    Envia uma mensagem via provedor configurável.
    
    Suporta:
    - Evolution API (provider="evolution")
    - WhatsApp Cloud API (provider="whatsapp_cloud")
    - Provedor genérico (provider="generic" ou não especificado)
    
    Configure SENDER_PROVIDER no .env para escolher o provedor.
    
    Args:
        numero: Número de telefone do destinatário
        texto: Texto da mensagem a ser enviada
        
    Returns:
        True se enviado com sucesso, False caso contrário
    """
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

