"""
Script para verificar agendamentos que não estão no banco de dados.

Busca todos os agendamentos no período especificado e verifica quais não foram
marcados como processados (qualquer tipo).
"""

import datetime
import logging
import os
import sys
from api_client import fetch_agendamentos
from storage import init_db, is_processed
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def verificar_faltantes(data_inicial=None, data_final=None):
    """
    Busca todos os agendamentos no intervalo e verifica quais não estão no banco.
    
    Args:
        data_inicial: Data inicial (YYYY-MM-DD). Se None, usa hoje
        data_final: Data final (YYYY-MM-DD). Se None, usa fim de 2026
    """
    init_db()
    
    if data_inicial is None:
        data_inicial = datetime.date.today().isoformat()
    if data_final is None:
        data_final = "2026-12-31"
    
    logger.info("=" * 70)
    logger.info(f"🔍 VERIFICANDO AGENDAMENTOS FALTANTES")
    logger.info("=" * 70)
    logger.info(f"   Período: {data_inicial} até {data_final}")
    logger.info("=" * 70)
    logger.info("")
    
    pagina = 0
    total_encontrados = 0
    total_no_banco = 0
    total_faltantes = 0
    faltantes_ids = []
    
    while True:
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
                    
                    total_encontrados += 1
                    
                    # Verifica se está no banco (qualquer tipo)
                    # Precisamos verificar todos os tipos possíveis
                    no_banco = (
                        is_processed(ag_id, tipo='inicializacao') or
                        is_processed(ag_id, tipo='agendamento') or
                        is_processed(ag_id, tipo='cancelamento')
                    )
                    
                    if no_banco:
                        total_no_banco += 1
                    else:
                        total_faltantes += 1
                        faltantes_ids.append(ag_id)
                        
                        # Log dos faltantes
                        nome_paciente = (
                            ag.get("paciente_nome") or
                            ag.get("nomePaciente") or
                            ag.get("pacienteNome") or
                            "N/A"
                        )
                        status = ag.get("status") or "N/A"
                        data_agenda = ag.get("data") or "N/A"
                        hora_agenda = ag.get("horaInicio") or "N/A"
                        
                        logger.warning(
                            f"❌ FALTANTE - ID: {ag_id}\n"
                            f"   Paciente: {nome_paciente}\n"
                            f"   Status: {status}\n"
                            f"   Data/Hora: {data_agenda} às {hora_agenda}"
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
            
            if pagina % 10 == 0:
                logger.info(
                    f"📄 Progresso: página {pagina}, "
                    f"{total_encontrados} encontrados, "
                    f"{total_no_banco} no banco, "
                    f"{total_faltantes} faltantes..."
                )
        
        except Exception as e:
            logger.error(f"Erro ao processar página {pagina}: {e}", exc_info=True)
            pagina += 1
            if pagina > 1000:
                logger.error("Limite de páginas excedido, abortando")
                break
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("📊 RESULTADO DA VERIFICAÇÃO")
    logger.info("=" * 70)
    logger.info(f"   📅 Período: {data_inicial} até {data_final}")
    logger.info(f"   📋 Total de agendamentos encontrados na API: {total_encontrados}")
    logger.info(f"   ✅ Agendamentos no banco: {total_no_banco}")
    logger.info(f"   ❌ Agendamentos FALTANTES: {total_faltantes}")
    logger.info("=" * 70)
    
    if total_faltantes > 0:
        logger.info("")
        logger.info("⚠️  ATENÇÃO: Existem agendamentos que não estão no banco!")
        logger.info(f"   IDs faltantes: {', '.join(map(str, faltantes_ids[:20]))}")
        if len(faltantes_ids) > 20:
            logger.info(f"   ... e mais {len(faltantes_ids) - 20} IDs")
        logger.info("")
        logger.info("💡 Para marcar os faltantes como inicializados, execute:")
        logger.info("   python3 init_db.py (para recriar tudo)")
    else:
        logger.info("")
        logger.info("✅ SUCESSO: Todos os agendamentos estão no banco!")
    
    logger.info("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        data_inicial = sys.argv[1]
        data_final = sys.argv[2]
        verificar_faltantes(data_inicial, data_final)
    elif len(sys.argv) == 2:
        data_final = sys.argv[1]
        data_inicial = datetime.date.today().isoformat()
        verificar_faltantes(data_inicial, data_final)
    else:
        verificar_faltantes()

