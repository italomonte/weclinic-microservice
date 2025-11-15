import os
import requests
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

SENDER_API_URL = os.getenv("SENDER_API_URL")
SENDER_AUTH = os.getenv("SENDER_AUTH")
SENDER_PROVIDER = os.getenv("SENDER_PROVIDER", "generic").lower()  # generic, evolution, whatsapp_cloud


def _formatar_numero_evolution(numero):
    """
    Formata número para Evolution API.
    Evolution API espera número com código do país sem caracteres especiais.
    Exemplo: 5511999999999
    """
    # Remove todos os caracteres não numéricos
    numero_limpo = "".join([c for c in str(numero) if c.isdigit()])
    
    # Se não começa com código do país, adiciona 55 (Brasil) se tiver 11 dígitos
    if len(numero_limpo) == 11 and not numero_limpo.startswith("55"):
        numero_limpo = "55" + numero_limpo
    
    return numero_limpo


def _montar_payload_evolution(numero, texto):
    """
    Monta payload para Evolution API.
    """
    numero_formatado = _formatar_numero_evolution(numero)
    return {
        "number": numero_formatado,
        "textMessage": {
            "text": texto
        }
    }


def _montar_headers_evolution():
    """
    Monta headers para Evolution API.
    """
    if SENDER_AUTH:
        # Evolution pode usar apikey ou Bearer
        if SENDER_AUTH.startswith("Bearer "):
            return {
                "Authorization": SENDER_AUTH,
                "Content-Type": "application/json"
            }
        else:
            return {
                "apikey": SENDER_AUTH,
                "Content-Type": "application/json"
            }
    return {
        "Content-Type": "application/json"
    }


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
    
    try:
        logger.debug(f"Enviando mensagem para {numero} via {SENDER_PROVIDER}")
        resp = requests.post(
            SENDER_API_URL,
            json=payload,
            headers=headers,
            timeout=15
        )
        
        if resp.status_code in (200, 201, 202):
            logger.info(f"Mensagem enviada com sucesso para {numero}")
            return True
        else:
            logger.error(f"Erro ao enviar mensagem para {numero}: status {resp.status_code}, resposta: {resp.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Exceção ao enviar mensagem para {numero}: {e}")
        return False

