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
    if not BASE or not USER or not PASS or not CLINICA_CID:
        raise ValueError("Variáveis de ambiente da API não configuradas corretamente")
    
    url = f"{BASE}/lista"
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "pagina": pagina
    }
    headers = {
        "clinicaNasNuvens-cid": CLINICA_CID,
        "Accept": "application/json"
    }
    
    try:
        logger.debug(f"Buscando agendamentos: {data_inicial} a {data_final}, página {pagina}")
        resp = requests.get(
            url,
            params=params,
            headers=headers,
            auth=HTTPBasicAuth(USER, PASS),
            timeout=20
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar agendamentos na página {pagina}: {e}")
        raise

