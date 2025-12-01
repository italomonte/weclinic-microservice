import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

BASE = os.getenv("API_BASE", "").rstrip("/")
USER = os.getenv("API_USER")
PASS = os.getenv("API_PASS")
CLINICA_CID = os.getenv("CLINICA_CID")


def _build_auth_headers():
    """
    Monta headers básicos (incluindo CID) e autenticação para a API da clínica.
    """
    if not BASE or not USER or not PASS or not CLINICA_CID:
        raise ValueError("Variáveis de ambiente da API não configuradas corretamente")
    
    headers = {
        "clinicaNasNuvens-cid": CLINICA_CID,
        "Accept": "application/json"
    }
    auth = HTTPBasicAuth(USER, PASS)
    return headers, auth


def fetch_agendamentos(data_inicial, data_final, pagina=0):
    """
    Busca agendamentos da API da Clínica nas Nuvens.
    
    Args:
        data_inicial: Data inicial no formato YYYY-MM-DD
        data_final: Data final no formato YYYY-MM-DD
        pagina: Número da página (padrão: 0, pois a API começa em 0)
        
    Returns:
        JSON com a resposta da API
        
    Raises:
        requests.RequestException: Se houver erro na requisição HTTP
    """
    headers, auth = _build_auth_headers()
    url = f"{BASE}/lista"
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "pagina": pagina
    }
    
    try:
        logger.debug(f"Buscando agendamentos: {data_inicial} a {data_final}, página {pagina}")
        resp = requests.get(url, params=params, headers=headers, auth=auth, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar agendamentos na página {pagina}: {e}")
        raise


def fetch_paciente(id_paciente):
    """
    Busca dados de um paciente pelo ID.
    
    Args:
        id_paciente: ID do paciente (campo idPaciente vindo da agenda)
    
    Returns:
        JSON com os dados do paciente.
    """
    headers, auth = _build_auth_headers()
    # BASE geralmente aponta para .../agenda para o endpoint de lista.
    # Para o endpoint de paciente, removemos o sufixo '/agenda' (se existir).
    base_root = BASE
    if base_root.endswith("/agenda"):
        base_root = base_root[: -len("/agenda")]
    url = f"{base_root}/paciente/{id_paciente}"
    
    try:
        logger.debug(f"Buscando dados do paciente {id_paciente}")
        resp = requests.get(url, headers=headers, auth=auth, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar paciente {id_paciente}: {e}")
        raise

