# Sistema de Validação de Velas - Smart Trader

> **Status:** Plugin de Dados implementado ✅  
> Este arquivo será atualizado com novas instruções conforme desenvolvimento.

---

## ✅ IMPLEMENTADO

### Plugin de Dados de Velas
- ✅ **PluginDadosVelas** criado e integrado
- ✅ Busca 60 velas 15m (15 horas)
- ✅ Busca 48 velas 1h (2 dias)  
- ✅ Busca 60 velas 4h (10 dias)
- ✅ Validação de vela fechada por timeframe
- ✅ Integração com PluginBybitConexao
- ✅ Integrado no ciclo principal de execução

---

## 🚧 PENDENTE - AGUARDANDO NOVAS INSTRUÇÕES

O arquivo será atualizado com instruções para:
- Plugin de Padrões de Velas
- Plugin de Confluência
- Integração com Sistema 6/8

---

**Última atualização:** 02/11/2025  
**Aguardando novas instruções para continuidade do desenvolvimento.**

--- 


## **PRÓXIMA TAREFA** ##

Vamos **acumular dados históricos** no PostgreSQL para **treinar IA no futuro**.

Vamos resolver **dois problemas ao mesmo tempo**:

1. **Evitar velas duplicadas** no banco  
2. **Estruturar os dados para IA futura** (ML, padrões, backtest)

---

## PROBLEMA: Velas repetidas a cada ciclo de 5s

> A cada 5 segundos, o bot roda → pega as últimas 60 velas de 15m → salva no PostgreSQL  
> → **55 velas são iguais às da execução anterior!**  
> → **55 duplicatas por minuto!**

### Resultado:  
- Tabela explode (milhões de linhas inúteis)  
- Consultas lentas  
- IA aprende lixo

---

## SOLUÇÃO: **"Salvamento Inteligente" (Smart Upsert)**

### Regra de Ouro:
> **Só insira uma vela se ela for NOVA ou ATUALIZADA**

---

### Como detectar vela nova?

| Timeframe | Vela nova quando... |
|----------|---------------------|
| 15m | `timestamp % 900 == 0` (múltiplo de 15min) |
| 1h  | `timestamp % 3600 == 0` |
| 4h  | `timestamp % 14400 == 0` |

> Use o `timestamp` da vela (em UTC) como chave.

---

## ESTRUTURA DA TABELA (PostgreSQL) — PRONTA PARA IA

```sql
CREATE TABLE velas (
    id SERIAL PRIMARY KEY,
    ativo VARCHAR(20) NOT NULL,           -- 'BTCUSDT'
    timeframe VARCHAR(5) NOT NULL,        -- '15m', '1h', '4h'
    open_time TIMESTAMP NOT NULL,         -- Início da vela (UTC)
    close_time TIMESTAMP NOT NULL,        -- Fim da vela
    open NUMERIC(20,8) NOT NULL,
    high NUMERIC(20,8) NOT NULL,
    low NUMERIC(20,8) NOT NULL,
    close NUMERIC(20,8) NOT NULL,
    volume NUMERIC(20,8) NOT NULL,
    
    -- Chave única para evitar duplicatas
    CONSTRAINT unique_vela UNIQUE (ativo, timeframe, open_time)
);
```

---

## LÓGICA DO BOT (A CADA CICLO)

```text
1. Pega últimas 60 velas do exchange (15m)
2. Para cada vela:
      → Se open_time NÃO existe no banco → INSERT
      → Se existe, mas close/volume mudou → UPDATE (vela em formação)
      → Senão → ignora
3. Repete para 1h e 4h
```

> **Só 1 INSERT por vela fechada**  
> **1 UPDATE por minuto** (para vela atual em formação)

---

## BENEFÍCIOS PARA A IA FUTURA

| Recurso | Como usar depois |
|-------|------------------|
| `open_time` | Sequência temporal (Time Series) |
| `volume` | Detectar manipulação, absorção |
| `close - open` | Tamanho do corpo |
| `high - low` | Volatilidade |
| `velas consecutivas` | Padrões de 2–3 velas |

### Ideias de IA:
- **Classificador**: "Esse padrão gerou alta de 2% em 4h?" → treinar com rótulos
- **Clustering**: agrupar padrões semelhantes
- **Previsão**: próximo fechamento com LSTM
- **Reforço**: aprender a filtrar confluências

---

## DICAS DE OTIMIZAÇÃO

| Dica | Por quê |
|----|--------|
| **Índice composto** | `CREATE INDEX idx_vela_lookup ON velas(ativo, timeframe, open_time);` |
| **Particionar por ativo** | `PARTITION BY LIST (ativo)` → consultas rápidas |
| **Limpar velas antigas** | `DELETE WHERE open_time < NOW() - INTERVAL '90 days'` |
| **Atualizar só vela atual** | Em 15m, só a última vela muda → `WHERE open_time >= NOW() - INTERVAL '15 min'` |

---

## FLUXO FINAL DO BOT (RESUMO)

```text
A cada 5s:
┌─ Pega velas do exchange (15m: 60, 1h: 48, 4h: 60)
│
├─ Para cada vela:
│   → Se nova → INSERT
│   → Se em formação → UPDATE
│   → Se repetida → ignora
│
├─ Detecta padrões (só com velas fechadas)
│
└─ Gera sinal (se confluência ≥ 3)
```

---

## PRÓXIMOS PASSOS (PLUG AND PLAY)

Excelente pergunta — e **muito estratégica**.  
Você está pensando **além do trade**: quer **acumular dados históricos** no PostgreSQL para **treinar IA no futuro**.

Vamos resolver **dois problemas ao mesmo tempo**:

1. **Evitar velas duplicadas** no banco  
2. **Estruturar os dados para IA futura** (ML, padrões, backtest)

---

## PROBLEMA: Velas repetidas a cada ciclo de 5s

> A cada 5 segundos, o bot roda → pega as últimas 60 velas de 15m → salva no PostgreSQL  
> → **55 velas são iguais às da execução anterior!**  
> → **55 duplicatas por minuto!**

### Resultado:  
- Tabela explode (milhões de linhas inúteis)  
- Consultas lentas  
- IA aprende lixo

---

## SOLUÇÃO: **"Salvamento Inteligente" (Smart Upsert)**

### Regra de Ouro:
> **Só insira uma vela se ela for NOVA ou ATUALIZADA**

---

### Como detectar vela nova?

| Timeframe | Vela nova quando... |
|----------|---------------------|
| 15m | `timestamp % 900 == 0` (múltiplo de 15min) |
| 1h  | `timestamp % 3600 == 0` |
| 4h  | `timestamp % 14400 == 0` |

> Use o `timestamp` da vela (em UTC) como chave.

---

## ESTRUTURA DA TABELA (PostgreSQL) — PRONTA PARA IA

```sql
CREATE TABLE velas (
    id SERIAL PRIMARY KEY,
    ativo VARCHAR(20) NOT NULL,           -- 'BTCUSDT'
    timeframe VARCHAR(5) NOT NULL,        -- '15m', '1h', '4h'
    open_time TIMESTAMP NOT NULL,         -- Início da vela (UTC)
    close_time TIMESTAMP NOT NULL,        -- Fim da vela
    open NUMERIC(20,8) NOT NULL,
    high NUMERIC(20,8) NOT NULL,
    low NUMERIC(20,8) NOT NULL,
    close NUMERIC(20,8) NOT NULL,
    volume NUMERIC(20,8) NOT NULL,
    
    -- Chave única para evitar duplicatas
    CONSTRAINT unique_vela UNIQUE (ativo, timeframe, open_time)
);
```

---

## LÓGICA DO BOT (A CADA CICLO)

```text
1. Pega últimas 60 velas do exchange (15m)
2. Para cada vela:
      → Se open_time NÃO existe no banco → INSERT
      → Se existe, mas close/volume mudou → UPDATE (vela em formação)
      → Senão → ignora
3. Repete para 1h e 4h
```

> **Só 1 INSERT por vela fechada**  
> **1 UPDATE por minuto** (para vela atual em formação)

---

## BENEFÍCIOS PARA A IA FUTURA

| Recurso | Como usar depois |
|-------|------------------|
| `open_time` | Sequência temporal (Time Series) |
| `volume` | Detectar manipulação, absorção |
| `close - open` | Tamanho do corpo |
| `high - low` | Volatilidade |
| `velas consecutivas` | Padrões de 2–3 velas |

### Ideias de IA:
- **Classificador**: "Esse padrão gerou alta de 2% em 4h?" → treinar com rótulos
- **Clustering**: agrupar padrões semelhantes
- **Previsão**: próximo fechamento com LSTM
- **Reforço**: aprender a filtrar confluências

---

## DICAS DE OTIMIZAÇÃO

| Dica | Por quê |
|----|--------|
| **Índice composto** | `CREATE INDEX idx_vela_lookup ON velas(ativo, timeframe, open_time);` |
| **Particionar por ativo** | `PARTITION BY LIST (ativo)` → consultas rápidas |
| **Limpar velas antigas** | `DELETE WHERE open_time < NOW() - INTERVAL '90 days'` |
| **Atualizar só vela atual** | Em 15m, só a última vela muda → `WHERE open_time >= NOW() - INTERVAL '15 min'` |

---

## FLUXO FINAL DO BOT (RESUMO)

```text
A cada 5s:
┌─ Pega velas do exchange (15m: 60, 1h: 48, 4h: 60)
│
├─ Para cada vela:
│   → Se nova → INSERT
│   → Se em formação → UPDATE
│   → Se repetida → ignora
│
├─ Detecta padrões (só com velas fechadas)
│
└─ Gera sinal (se confluência ≥ 3)
```

---

## PRÓXIMOS PASSOS (PLUG AND PLAY)

1. **Crie a tabela no PostgreSQL** (código acima)
2. **No plugin de dados**:
   - Adicione função `salvar_velas(lista_velas, ativo, timeframe)`
   - Use `INSERT ... ON CONFLICT DO UPDATE`
3. **Marque velas fechadas** com `is_closed = True` (opcional, para IA)

---

## RESUMO ULTRA RÁPIDO

| Pergunta | Resposta |
|--------|--------|
| Velas repetidas? | **Evitadas com `UNIQUE(open_time)` + UPSERT** |
| Como salvar? | **Só INSERT se nova, UPDATE se em formação** |
| Banco explode? | **Não. Máximo 1 linha por vela por timeframe** |
| Pronto pra IA? | **100%. Dados limpos, temporais, indexados** |

---
