"""
Script de teste que simula a resposta da API sem chamar o endpoint real.

Útil para testar:
- Processamento de agendamentos
- Templates de mensagem
- Lógica de paginação
- Filtro de IDs processados
"""

import datetime
import logging
from storage import init_db, is_processed, mark_processed
from sender import enviar_mensagem
from templates import CONFIRMACAO
from main import extrair_primeiro_nome

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def mock_fetch_agendamentos(data_inicial, data_final, pagina=1):
    """
    Simula a resposta da API com dados de exemplo.
    
    Retorna estrutura similar à API real para testar processamento.
    """
    logger.info(f"Mock: Buscando agendamentos {data_inicial} a {data_final}, página {pagina}")
    
    # Dados de exemplo - ajuste conforme necessário
    agendamentos_pagina_1 = [
        {
            "id": 101,
            "data": "2024-12-20",
            "horaInicio": "09:00",
            "telefoneCelularPaciente": "+55 11 98765-4321",
            "paciente_nome": "João Silva Santos",
            "nome_profissional": "Dr. Carlos Mendes",
            "procedimentos": ["Consulta", "Exame de sangue"],
            "endereco_clinica": "Rua das Flores, 123 - São Paulo, SP"
        },
        {
            "id": 102,
            "data": "2024-12-20",
            "horaInicio": "10:30",
            "telefoneCelularPaciente": "(11) 91234-5678",
            "paciente_nome": "Maria Oliveira",
            "nome_profissional": "Dra. Ana Paula",
            "procedimentos": ["Consulta"],
            "endereco_clinica": "Rua das Flores, 123 - São Paulo, SP"
        }
    ]
    
    agendamentos_pagina_2 = [
        {
            "id": 103,
            "data": "2024-12-20",
            "horaInicio": "14:00",
            "telefoneCelularPaciente": "11987654321",
            "paciente_nome": "Pedro Costa",
            "nome_profissional": "Dr. Roberto Lima",
            "procedimentos": ["Consulta", "Ultrassom"],
            "endereco_clinica": "Rua das Flores, 123 - São Paulo, SP"
        }
    ]
    
    # Simula paginação
    if pagina == 1:
        return [
            {
                "lista": agendamentos_pagina_1,
                "totalPaginas": 2
            }
        ]
    elif pagina == 2:
        return [
            {
                "lista": agendamentos_pagina_2,
                "totalPaginas": 2
            }
        ]
    else:
        # Páginas vazias após a última
        return [
            {
                "lista": [],
                "totalPaginas": 2
            }
        ]


def test_processamento():
    """Testa o processamento completo com dados mockados."""
    logger.info("=== Iniciando teste com dados mockados ===")
    
    # Inicializa banco de dados
    init_db()
    
    # Simula processamento
    data_inicial = datetime.date.today().isoformat()
    data_final = datetime.date.today().isoformat()
    
    pagina = 1
    total_processados = 0
    
    while True:
        try:
            resp = mock_fetch_agendamentos(data_inicial, data_final, pagina=pagina)
            
            if not resp:
                break
            
            lista_paginas = resp if isinstance(resp, list) else [resp]
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
                    
                    # Verifica se já foi processado
                    if is_processed(ag_id):
                        logger.info(f"Agendamento {ag_id} já foi processado, ignorando")
                        continue
                    
                    # Extrai dados
                    primeiro_nome = extrair_primeiro_nome(
                        ag.get("paciente_nome") or ""
                    )
                    data_agenda = ag.get("data", "")
                    hora_agenda = ag.get("horaInicio", "")
                    nome_prof = ag.get("nome_profissional", "")
                    procedimentos = ag.get("procedimentos", [])
                    procedimentos_texto = ", ".join(procedimentos) if procedimentos else "—"
                    endereco = ag.get("endereco_clinica", "")
                    
                    # Formata número
                    numero = ag.get("telefoneCelularPaciente", "")
                    numero = "".join([c for c in str(numero) if c.isdigit()])
                    
                    if not numero:
                        logger.warning(f"Agendamento {ag_id} sem número válido")
                        continue
                    
                    # Monta mensagem
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
                        logger.error(f"Erro no template: {e}")
                        continue
                    
                    logger.info(f"\n=== Mensagem para agendamento {ag_id} ===\n{texto}\n")
                    
                    # Em modo de teste, não envia mensagem real (a menos que SENDER_API_URL esteja configurado)
                    # Mas marca como processado para testar a lógica
                    logger.info(f"SIMULAÇÃO: Mensagem seria enviada para {numero}")
                    mark_processed(ag_id)
                    total_processados += 1
            
            # Verifica paginação
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
            logger.error(f"Erro no teste: {e}", exc_info=True)
            break
    
    logger.info(f"\n=== Teste concluído. Total processado: {total_processados} ===")


def test_template():
    """Testa apenas o template de mensagem."""
    logger.info("\n=== Teste de Template ===")
    texto = CONFIRMACAO.substitute(
        primeiro_nome="João",
        data_agenda="2024-12-20",
        hora_agenda="09:00",
        nome_profissional="Dr. Carlos Mendes",
        procedimentos="Consulta, Exame de sangue",
        endereco_clinica="Rua das Flores, 123 - São Paulo, SP"
    )
    logger.info(f"\n{texto}\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "template":
        test_template()
    else:
        test_processamento()

