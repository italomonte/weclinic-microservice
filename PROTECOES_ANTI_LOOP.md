# 🛡️ Proteções Anti-Loop Implementadas

## Contexto do Problema

Durante a virada do ano de 2025 para 2026, foi detectado um bug onde o mesmo cliente recebia mensagens repetidamente, gerando mais de 1000 requisições para a API em um único dia.

## Causas Potenciais Identificadas

1. **`is_processed()` retornando `False` em caso de erro de banco**
2. **Loop infinito na paginação** quando `totalPaginas` não é retornado pela API
3. **Detecção falsa de reagendamento** devido a comparações de data incorretas
4. **API retornando dados duplicados** em páginas diferentes
5. **Falta de rate limiting** por número de telefone

## Proteções Implementadas

### 1. Rate Limiting por Número de Telefone (`storage.py`)

```python
RATE_LIMIT_MAX_PER_HOUR = int(os.getenv("RATE_LIMIT_MAX_PER_HOUR", "5"))
```

- **Limite padrão**: 5 mensagens por número por hora
- **Janela de tempo**: 1 hora (3600 segundos)
- **Funções**: `check_rate_limit(numero)`, `register_rate_limit(numero)`

### 2. Circuit Breaker para Banco de Dados (`storage.py`)

```python
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"))
```

- **Threshold**: 5 falhas consecutivas para ativar
- **Timeout**: 60 segundos de pausa antes de tentar novamente
- Se `is_processed()` ou `mark_processed()` falharem muito, o sistema para

### 3. Limite de Mensagens por Ciclo (`storage.py`)

```python
MAX_MESSAGES_PER_CYCLE = int(os.getenv("MAX_MESSAGES_PER_CYCLE", "100"))
```

- **Limite padrão**: 100 mensagens por ciclo de processamento
- Evita que um único ciclo envie milhares de mensagens

### 4. Limite de Paginação (`main.py`)

```python
MAX_PAGINAS = int(os.getenv("MAX_PAGINAS", "50"))
```

- **Limite padrão**: 50 páginas por processamento
- Evita loop infinito se a API não retornar `totalPaginas`

### 5. Detecção de IDs Duplicados no Ciclo (`main.py`)

```python
ids_processados_neste_ciclo = set()
# ...
if ag_id in ids_processados_neste_ciclo:
    continue
ids_processados_neste_ciclo.add(ag_id)
```

- Mantém um conjunto de IDs já processados no ciclo atual
- Evita processar o mesmo agendamento duas vezes se a API retornar duplicatas

### 6. `is_processed()` Lança Exceção em Vez de Retornar `False` (`storage.py`)

**Antes (BUG):**
```python
except Exception as e:
    logger.error(f"Erro ao verificar processamento: {e}")
    return False  # ❌ BUG: Retornava False, causando reprocessamento
```

**Depois (CORRIGIDO):**
```python
except Exception as e:
    _record_db_failure()
    raise RuntimeError(f"Falha ao verificar processamento: {e}")  # ✅ Lança exceção
```

### 7. Validação de Ano nos Agendamentos (`main.py`)

```python
if data_ag_obj.year < ano_atual - 1:
    logger.debug(f"Agendamento {ag_id} ignorado (ano muito antigo)")
    continue
```

- Ignora agendamentos de anos muito anteriores
- Proteção extra para evitar processar dados incorretos

### 8. Validação de Reagendamentos no Passado (`main.py`)

```python
if data_atual_obj < hoje_validacao:
    logger.warning(f"Reagendamento ignorado (data no passado)")
    continue
```

- Ignora detecção de reagendamento se a nova data estiver no passado

## Variáveis de Ambiente Configuráveis

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `RATE_LIMIT_MAX_PER_HOUR` | 5 | Máximo de mensagens por número por hora |
| `CIRCUIT_BREAKER_THRESHOLD` | 5 | Falhas de DB para ativar circuit breaker |
| `CIRCUIT_BREAKER_TIMEOUT` | 60 | Segundos de pausa quando circuit breaker ativado |
| `MAX_MESSAGES_PER_CYCLE` | 100 | Máximo de mensagens por ciclo |
| `MAX_PAGINAS` | 50 | Máximo de páginas por processamento |

## Logs de Proteção

O sistema agora registra nos logs quando as proteções são ativadas:

```
⚠️ RATE LIMIT ATINGIDO para 5592981234
⚠️ LIMITE DE MENSAGENS POR CICLO ATINGIDO
⚠️ LIMITE DE PAGINAÇÃO ATINGIDO (50 páginas)
🔴 CIRCUIT BREAKER ATIVADO: 5 falhas consecutivas
```

## Resumo do Processamento

Ao final de cada ciclo, o resumo inclui métricas de proteção:

```
🛡️ PROTEÇÕES ATIVADAS:
   └─ Bloqueados por rate limit: 3
   └─ IDs processados neste ciclo: 45
   └─ Páginas processadas: 12
```

## Recomendações

1. **Monitore os logs** para ver se as proteções estão sendo ativadas
2. **Ajuste os limites** via variáveis de ambiente conforme necessidade
3. **Em produção**, considere aumentar `MAX_MESSAGES_PER_CYCLE` gradualmente
4. **Mantenha logs históricos** para análise de incidentes futuros

---

*Documentação criada em: 2025*
*Última atualização: Implementação de proteções anti-loop*
