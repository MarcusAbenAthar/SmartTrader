# Definição do Banco de Dados - Smart Trader

## Visão Geral

O sistema utiliza **PostgreSQL** como banco de dados principal para armazenar:
- Dados históricos de velas (OHLCV) por timeframe
- Dados de indicadores técnicos (futuro)
- Análises e padrões detectados (futuro)
- Estatísticas de trading (futuro)

---

## Configuração de Conexão

### Variáveis de Ambiente (.env)

O acesso ao banco é feito através das seguintes variáveis no arquivo `.env`:

```env
DB_HOST=localhost          # Host do PostgreSQL
DB_NAME=smarttrader       # Nome do banco de dados
DB_USER=seu_usuario        # Usuário do PostgreSQL
DB_PASSWORD=sua_senha      # Senha do PostgreSQL
DB_PORT=5432               # Porta do PostgreSQL (padrão: 5432)
```

### Acesso via Config

As credenciais são acessadas através do `ConfigManager` em `utils/main_config.py`:

```python
config = carregar_config()
db_config = config.get("db", {})
# db_config["host"], db_config["database"], db_config["user"], etc.
```

---

## Estrutura de Conexão

### PluginBancoDados

O plugin `PluginBancoDados` gerencia toda a conexão e operações com PostgreSQL:

- **Localização**: `plugins/plugin_banco_dados.py`
- **Pool de Conexões**: ThreadedConnectionPool (psycopg2)
  - Mínimo: 1 conexão
  - Máximo: 5 conexões
  - Timeout: 10 segundos

### Características

1. **Pool de Conexões**: Gerenciamento eficiente de conexões
2. **Upsert Inteligente**: Evita duplicatas usando `ON CONFLICT DO UPDATE`
3. **Criação Automática**: Cria tabelas automaticamente se não existirem
4. **Transações**: Gerencia commits e rollbacks automaticamente
5. **CRUD Completo**: Métodos para INSERT, UPDATE, SELECT, DELETE
6. **Logs Padronizados**: Formato `[BancoDados][OPERACAO]` para depuração
7. **Retorno Padronizado**: Dicionário padronizado para todas as operações
8. **Segurança**: Uso de `sql.Identifier` para prevenir SQL injection

---

## Tabela: `velas`

### Estrutura

Conforme especificação em `instrucao-velas.md`:

```sql
CREATE TABLE velas (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(20) DEFAULT 'bybit',  -- Campo exchange para suporte multi-exchange
    ativo VARCHAR(20) NOT NULL,           -- 'BTCUSDT', 'ETHUSDT', etc.
    timeframe VARCHAR(5) NOT NULL,        -- '15m', '1h', '4h'
    open_time TIMESTAMP NOT NULL,         -- Início da vela (UTC)
    close_time TIMESTAMP NOT NULL,        -- Fim da vela (UTC)
    open NUMERIC(20,8) NOT NULL,
    high NUMERIC(20,8) NOT NULL,
    low NUMERIC(20,8) NOT NULL,
    close NUMERIC(20,8) NOT NULL,
    volume NUMERIC(20,8) NOT NULL,
    fechada BOOLEAN DEFAULT TRUE,         -- Se vela foi fechada
    testnet BOOLEAN DEFAULT FALSE,        -- Campo para distinguir testnet/mainnet
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    
    -- Chave única para evitar duplicatas (inclui exchange e testnet)
    CONSTRAINT unique_vela UNIQUE (exchange, ativo, timeframe, open_time, testnet)
);
```
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
read_file

### Índices

Índices criados automaticamente para otimizar consultas:

```sql
-- Índice composto para consultas rápidas
CREATE INDEX idx_vela_lookup ON velas(ativo, timeframe, open_time);

-- Índice para consultas por ativo
CREATE INDEX idx_vela_ativo ON velas(ativo);

-- Índice para consultas por timeframe
CREATE INDEX idx_vela_timeframe ON velas(timeframe);

-- Índice para consultas por data
CREATE INDEX idx_vela_open_time ON velas(open_time);

-- Índice para consultas por exchange
CREATE INDEX idx_vela_exchange ON velas(exchange);

-- Índice para consultas por testnet (filtrar testnet/mainnet)
CREATE INDEX idx_vela_testnet ON velas(testnet);
```
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
grep

### Constraint de Unicidade

A constraint `unique_vela` garante que:
- Não há duplicatas de velas (mesmo exchange, ativo, timeframe, open_time, testnet)
- Suporta multi-exchange (se um dia o bot operar em múltiplas exchanges)
- Distingue dados de testnet e mainnet
- Evita milhões de linhas inúteis no banco
- Permite upsert eficiente

### Campo Exchange

O campo `exchange` foi adicionado para suporte futuro a múltiplas exchanges:
- **Padrão**: 'bybit' (configurável)
- **Benefício**: Permite operar em múltiplas exchanges sem conflitos
- **Constraint**: Incluído na chave única para evitar duplicatas entre exchanges

### Campo Testnet

O campo `testnet` foi adicionado para distinguir dados de testnet e mainnet:
- **Padrão**: FALSE (mainnet)
- **Benefício**: Permite manter dados de testnet e mainnet separados no mesmo banco
- **Constraint**: Incluído na chave única para evitar conflitos entre ambientes
- **Uso**: Quando `BYBIT_TESTNET=True` no `.env`, velas são salvas com `testnet=TRUE`

---

## Lógica de Upsert (Smart Upsert)

### Regra de Ouro

> **Só insere uma vela se ela for NOVA ou ATUALIZADA**

### Como Funciona

Conforme `instrucao-velas.md`:

1. **Vela Nova**: Se `open_time` não existe no banco → `INSERT`
2. **Vela em Formação**: Se existe, mas `close` ou `volume` mudou → `UPDATE`
3. **Vela Repetida**: Se existe e não mudou → **ignora**

### Query de Upsert

```sql
INSERT INTO velas (
    exchange, ativo, timeframe, open_time, close_time,
    open, high, low, close, volume, fechada, testnet
) VALUES %s
ON CONFLICT (exchange, ativo, timeframe, open_time, testnet) 
DO UPDATE SET
    close_time = EXCLUDED.close_time,
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    fechada = EXCLUDED.fechada,
    atualizado_em = NOW()
WHERE velas.close != EXCLUDED.close 
   OR velas.volume != EXCLUDED.volume;
```
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
grep

### Benefícios

- **Evita Duplicatas**: Máximo 1 linha por vela por timeframe
- **Atualiza Velas em Formação**: A última vela é atualizada a cada ciclo
- **Performance**: Consultas rápidas com índices otimizados
- **Dados Limpos**: Banco pronto para IA/ML

---

## Dados das Moedas (JSON)

### Localização

Arquivo JSON salvo em: `data/moedas_dados.json`

### Estrutura

O JSON contém dados das moedas **SEM velas completas**:

```json
{
  "timestamp": "2025-11-04T21:13:00.000Z",
  "moedas": {
    "BTCUSDT": {
      "par": "BTCUSDT",
      "timeframes": {
        "15m": {
          "quantidade_velas": 60,
          "ultima_vela": {
            "timestamp": 1733356800000,
            "datetime": "2025-11-04T21:13:00.000-03:00",
            "open": 68472.5,
            "high": 68500.0,
            "low": 68450.0,
            "close": 68490.0,
            "volume": 1234.567,
            "fechada": true
          }
        },
        "1h": { ... },
        "4h": { ... }
      }
    },
    "ETHUSDT": { ... },
    "SOLUSDT": { ... },
    "XRPUSDT": { ... }
  }
}
```

### Por que Separar?

- **Velas no Banco**: Dados históricos completos para IA/ML
- **Resumo no JSON**: Dados atuais e estatísticas rápidas
- **Performance**: JSON pequeno e rápido de ler
- **Flexibilidade**: Fácil de compartilhar e analisar

---

## Timeframes Suportados

| Timeframe | Duração | Velas Buscadas | Histórico |
|-----------|---------|----------------|-----------|
| 15m       | 15 min  | 60 velas       | 15 horas  |
| 1h        | 1 hora  | 48 velas       | 2 dias    |
| 4h        | 4 horas | 60 velas       | 10 dias   |

### Cálculo de close_time

O `close_time` é calculado automaticamente:

```python
open_time = datetime.utcfromtimestamp(timestamp / 1000)
timeframe_minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
close_time = open_time + timedelta(minutes=timeframe_minutes)
```

---

## Otimizações Implementadas

### 1. Índices Compostos

- `idx_vela_lookup`: (ativo, timeframe, open_time)
- Consultas rápidas por par e timeframe

### 2. Upsert em Lote

- `execute_values()` do psycopg2
- Inserção de até 100 velas por vez
- Performance otimizada

### 3. Pool de Conexões

- Reutilização de conexões
- Menos overhead de conexão/desconexão
- Thread-safe

### 4. Validação de Dados

- Verificação de tipos antes de inserir
- Conversão automática de timestamps
- Tratamento de erros robusto

---

## Dicas de Uso

### Consultas Rápidas

```sql
-- Últimas 60 velas de BTCUSDT 15m
SELECT * FROM velas 
WHERE ativo = 'BTCUSDT' AND timeframe = '15m'
ORDER BY open_time DESC 
LIMIT 60;

-- Velas fechadas de hoje
SELECT * FROM velas 
WHERE fechada = TRUE 
  AND open_time >= CURRENT_DATE
ORDER BY open_time DESC;

-- Estatísticas por ativo
SELECT 
    ativo,
    COUNT(*) as total_velas,
    MIN(open_time) as primeira_vela,
    MAX(open_time) as ultima_vela
FROM velas
GROUP BY ativo;
```

### Limpeza de Dados Antigos

```sql
-- Remove velas com mais de 90 dias
DELETE FROM velas 
WHERE open_time < NOW() - INTERVAL '90 days';
```

### Backup

```bash
# Backup do banco
pg_dump -h localhost -U seu_usuario -d smarttrader > backup.sql

# Restauração
psql -h localhost -U seu_usuario -d smarttrader < backup.sql
```

---

## Tabelas Implementadas

### Tabela: `telemetria_plugins`

Armazena telemetria de execução de plugins para estatísticas de aprendizado para IA.

```sql
CREATE TABLE telemetria_plugins (
    id SERIAL PRIMARY KEY,
    plugin VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    total_execucoes INTEGER DEFAULT 0,
    execucoes_sucesso INTEGER DEFAULT 0,
    execucoes_erro INTEGER DEFAULT 0,
    falhas_consecutivas INTEGER DEFAULT 0,
    tempo_medio NUMERIC(10,6) DEFAULT 0.0,
    tempo_minimo NUMERIC(10,6) DEFAULT 0.0,
    tempo_maximo NUMERIC(10,6) DEFAULT 0.0,
    taxa_sucesso NUMERIC(5,4) DEFAULT 0.0,
    ultima_execucao TIMESTAMP,
    ultimo_status VARCHAR(20),
    nivel_gravidade VARCHAR(20) DEFAULT 'info',
    criado_em TIMESTAMP DEFAULT NOW()
);
```

**Índices:**
- `idx_telemetria_plugin`: (plugin, timestamp) - Consultas rápidas por plugin

**Uso:**
- Gera estatísticas de aprendizado para IA analisar padrões de execução
- Armazenado automaticamente após cada execução de plugin
- Permite análise de performance e estabilidade ao longo do tempo

### Tabela: `schema_versoes`

Histórico de versões de schema (útil quando migrar tabelas).

```sql
CREATE TABLE schema_versoes (
    id SERIAL PRIMARY KEY,
    tabela VARCHAR(100) NOT NULL,
    versao VARCHAR(20) NOT NULL,
    descricao TEXT,
    migracao_sql TEXT,
    aplicado_em TIMESTAMP DEFAULT NOW(),
    aplicado_por VARCHAR(100),
    CONSTRAINT unique_schema_versao UNIQUE (tabela, versao)
);
```

**Índices:**
- `idx_schema_versoes_tabela`: (tabela, versao) - Consultas rápidas de histórico

**Uso:**
- Rastreia mudanças de schema automaticamente
- Registra quando cada versão foi aplicada
- Permite auditoria completa de migrações

### View Materializada: `mv_velas_agregadas`

View materializada para médias e indicadores agregados - acelera análises da IA sem recalcular tudo.

```sql
CREATE MATERIALIZED VIEW mv_velas_agregadas AS
SELECT 
    exchange,
    ativo,
    timeframe,
    testnet,
    DATE_TRUNC('hour', open_time) as hora,
    COUNT(*) as total_velas,
    AVG(close) as media_close,
    AVG(high) as media_high,
    AVG(low) as media_low,
    AVG(volume) as media_volume,
    MAX(high) as max_high,
    MIN(low) as min_low,
    SUM(volume) as volume_total,
    STDDEV(close) as desvio_close,
    AVG(high - low) as media_range
FROM velas
WHERE fechada = TRUE
GROUP BY exchange, ativo, timeframe, testnet, DATE_TRUNC('hour', open_time);
```

**Índice:**
- `idx_mv_velas_agregadas`: (exchange, ativo, timeframe, testnet, hora) - Consultas rápidas

**Uso:**
- Acelera análises da IA sem recalcular tudo
- Atualizada periodicamente com `REFRESH MATERIALIZED VIEW CONCURRENTLY`
- Agregações por hora para análise de tendências

**Atualização:**
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_velas_agregadas;
```

---

## Tabelas de Padrões de Trading (v1.3.0)

### Tabela: `padroes_detectados`

Armazena padrões técnicos detectados com telemetria completa.

```sql
CREATE TABLE padroes_detectados (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    open_time TIMESTAMP NOT NULL,
    tipo_padrao VARCHAR(50) NOT NULL,
    direcao VARCHAR(10) NOT NULL,  -- LONG, SHORT
    score NUMERIC(5,4) NOT NULL,  -- 0.0 a 1.0
    confidence NUMERIC(5,4) NOT NULL,  -- 0.0 a 1.0
    regime VARCHAR(20) NOT NULL,  -- trending, range, indefinido
    suggested_sl NUMERIC(20,8),
    suggested_tp NUMERIC(20,8),
    final_score NUMERIC(5,4) NOT NULL,  -- technical_score * 0.6 + confidence * 0.4
    meta JSONB,  -- Metadados adicionais
    criado_em TIMESTAMP DEFAULT NOW()
);
```

**Índices:**
- `idx_padroes_symbol_timeframe`: (symbol, timeframe, open_time) - Consultas rápidas por par
- `idx_padroes_tipo`: (tipo_padrao) - Consultas por tipo de padrão
- `idx_padroes_final_score`: (final_score) - Filtros por score

**Uso:**
- Armazena todos os padrões detectados pelo PluginPadroes
- Campo `meta` (JSONB) contém informações específicas de cada padrão
- Campo `regime` obrigatório conforme proxima_atualizacao.md

### Tabela: `padroes_metricas`

Armazena métricas de performance por padrão para validação temporal.

```sql
CREATE TABLE padroes_metricas (
    id SERIAL PRIMARY KEY,
    tipo_padrao VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    timeframe VARCHAR(5),
    periodo_inicio TIMESTAMP NOT NULL,
    periodo_fim TIMESTAMP NOT NULL,
    frequency NUMERIC(10,4) NOT NULL,  -- Ocorrências por 1000 velas
    precision NUMERIC(5,4),  -- % de setups que atingiram target
    recall NUMERIC(5,4),
    expectancy NUMERIC(10,4),  -- EV por trade
    sharpe_condicional NUMERIC(10,4),  -- Retorno médio / desvio por padrão
    drawdown_condicional NUMERIC(10,4),  -- Max perda por padrão
    winrate NUMERIC(5,4),
    avg_rr NUMERIC(5,4),  -- Risk:Reward médio
    total_trades INTEGER DEFAULT 0,
    trades_win INTEGER DEFAULT 0,
    trades_loss INTEGER DEFAULT 0,
    tipo_validacao VARCHAR(20),  -- in_sample, out_of_sample, walk_forward, rolling
    criado_em TIMESTAMP DEFAULT NOW()
);
```

**Índices:**
- `idx_padroes_metricas_tipo`: (tipo_padrao, periodo_inicio, periodo_fim) - Consultas por padrão e período
- `idx_padroes_metricas_validacao`: (tipo_validacao) - Filtros por tipo de validação

**Uso:**
- Métricas calculadas durante validação temporal (Walk-Forward, Rolling Window, OOS)
- Permite rankear padrões por performance real
- Conforme proxima_atualizacao.md: OOS ≥ 30% e Expectancy OOS > 70% in-sample

### Tabela: `padroes_confidence`

Armazena histórico de confidence decay por padrão.

```sql
CREATE TABLE padroes_confidence (
    id SERIAL PRIMARY KEY,
    tipo_padrao VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    timeframe VARCHAR(5),
    data_ultimo_win TIMESTAMP,
    days_since_last_win INTEGER,
    base_score NUMERIC(5,4) NOT NULL,
    confidence_score NUMERIC(5,4) NOT NULL,
    em_quarentena BOOLEAN DEFAULT FALSE,  -- confidence < 0.5
    criado_em TIMESTAMP DEFAULT NOW()
);
```

**Índices:**
- `idx_padroes_confidence_tipo`: (tipo_padrao, symbol, timeframe) - Consultas por padrão
- `idx_padroes_confidence_quarentena`: (em_quarentena) - Filtros de padrões em quarentena

**Uso:**
- Rastreia confidence decay: `confidence_score = base_score * exp(-0.01 * days_since_last_win)`
- Quarentena automática se `confidence_score < 0.5`
- Peso maior no ensemble se `confidence_score > 0.8`

---

## Próximas Tabelas (Futuro)

### Indicadores Técnicos

- `ichimoku`: Dados do Ichimoku Cloud
- `supertrend`: Dados do Supertrend
- `bollinger`: Dados das Bollinger Bands
- `ema`: Dados de EMA Crossover
- `macd`: Dados do MACD
- `rsi`: Dados do RSI
- `vwap`: Dados do VWAP

### Padrões e Análises

- ✅ `padroes_detectados`: Padrões técnicos detectados com telemetria completa (v1.3.0)
- ✅ `padroes_metricas`: Métricas de performance por padrão (v1.3.0)
- ✅ `padroes_confidence`: Histórico de confidence decay por padrão (v1.3.0)
- ⏳ `confluencias`: Confluências detectadas
- ⏳ `sinais`: Sinais de trading gerados

---

## Considerações Importantes

### 1. Timezone

- **Todos os timestamps são UTC**
- Conversão para timezone local deve ser feita na aplicação
- `open_time` e `close_time` são sempre em UTC

### 2. Precisão

- **NUMERIC(20,8)**: 20 dígitos totais, 8 decimais
- Suporta valores muito grandes e precisão alta
- Ideal para criptomoedas

### 3. Performance

- **Índices**: Consultas otimizadas por ativo, timeframe e data
- **Upsert**: Evita duplicatas eficientemente
- **Pool**: Reutilização de conexões

### 4. Escalabilidade

- **Particionamento Futuro**: Por ativo ou data
- **Limpeza Automática**: Remover dados antigos periodicamente
- **Backup Regular**: Para recuperação em caso de falha

### 5. Segurança

- **Credenciais no .env**: Nunca commitadas no git
- **Pool de Conexões**: Isolamento de transações
- **Validação de Dados**: Prevenção de SQL injection

---

## Manutenção

### Verificação de Integridade

```sql
-- Verifica duplicatas (não deve retornar nenhuma linha)
SELECT ativo, timeframe, open_time, COUNT(*) 
FROM velas 
GROUP BY ativo, timeframe, open_time 
HAVING COUNT(*) > 1;

-- Verifica velas sem fechar
SELECT ativo, timeframe, COUNT(*) 
FROM velas 
WHERE fechada = FALSE 
GROUP BY ativo, timeframe;
```

### Estatísticas do Banco

```sql
-- Tamanho da tabela
SELECT pg_size_pretty(pg_total_relation_size('velas')) as tamanho;

-- Número de velas por ativo
SELECT ativo, COUNT(*) as total 
FROM velas 
GROUP BY ativo 
ORDER BY total DESC;

-- Número de velas por timeframe
SELECT timeframe, COUNT(*) as total 
FROM velas 
GROUP BY timeframe 
ORDER BY total DESC;
```

---

## Erros Comuns

### 1. Erro de Conexão

```
psycopg2.OperationalError: could not connect to server
```

**Solução**: Verificar se PostgreSQL está rodando e credenciais corretas no `.env`

### 2. Erro de Tabela Não Encontrada

```
psycopg2.errors.UndefinedTable: relation "velas" does not exist
```

**Solução**: O plugin cria a tabela automaticamente. Verificar logs para erros.

### 3. Erro de Duplicata

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint
```

**Solução**: Não deve ocorrer com upsert. Verificar se constraint está correta.

---

**Última Atualização**: 08/11/2025  
**Versão**: v1.3.0

### Changelog v1.3.0 (08/11/2025)

#### Sistema de Padrões de Trading
- ✅ Tabela `padroes_detectados` criada - Padrões técnicos detectados com telemetria completa
- ✅ Tabela `padroes_metricas` criada - Métricas de performance por padrão
- ✅ Tabela `padroes_confidence` criada - Histórico de confidence decay
- ✅ Campo `testnet` adicionado na tabela `velas` - Distingue dados de testnet/mainnet
- ✅ Constraint `unique_vela` atualizada para incluir `testnet`
- ✅ View materializada `mv_velas_agregadas` atualizada para incluir `testnet`
- ✅ Índice `idx_vela_testnet` criado para consultas por ambiente
- ✅ Validação Temporal implementada (Walk-Forward, Rolling Window, OOS)
- ✅ Métricas básicas calculadas e persistidas automaticamente

### Changelog v1.2.0 (05/11/2025)

#### PluginBancoDados - Refatoração Completa
- ✅ CRUD completo implementado (INSERT, UPDATE, SELECT, DELETE)
- ✅ Métodos internos com underscore (_inserir, _consultar, etc.)
- ✅ Métodos públicos sem underscore (inserir, consultar, atualizar, deletar)
- ✅ Logs padronizados: [BancoDados][INSERT], [UPDATE], [SELECT], [DELETE]
- ✅ Retorno padronizado em dicionário para facilitar integração com IA
- ✅ Uso de sql.Identifier para prevenir SQL injection
- ✅ Validação de filtros obrigatórios em UPDATE e DELETE
- ✅ Documentação completa com exemplos de uso

### Changelog v1.1.0 (05/11/2025)

- ✅ Adicionado campo `exchange` na tabela `velas` para suporte multi-exchange
- ✅ Criada tabela `telemetria_plugins` para estatísticas de aprendizado para IA
- ✅ Criada tabela `schema_versoes` para histórico de versões de schema
- ✅ Criada view materializada `mv_velas_agregadas` para análises aceleradas
- ✅ Atualizada constraint `unique_vela` para incluir `exchange`
- ✅ Adicionados índices para consultas por `exchange`

---

## Operações CRUD Disponíveis

### Inserir Dados

```python
# Inserir velas (usa upsert automático)
resultado = plugin.inserir("velas", [
    {
        "ativo": "BTCUSDT",
        "timeframe": "15m",
        "timestamp": 1733356800000,
        "open": 68472.5,
        "high": 68500.0,
        "low": 68450.0,
        "close": 68490.0,
        "volume": 1234.567,
        "fechada": True
    }
])

# Inserir telemetria
resultado = plugin.inserir("telemetria_plugins", {
    "plugin": "PluginRSI",
    "total_execucoes": 100,
    "execucoes_sucesso": 95,
    ...
})

# Retorno padronizado:
# {
#     "sucesso": True,
#     "operacao": "INSERT",
#     "tabela": "velas",
#     "dados": [...],
#     "mensagem": "1 vela(s) inserida(s)/atualizada(s)",
#     "linhas_afetadas": 1,
#     "erro": None,
#     "timestamp": "2025-11-05T..."
# }
```

### Consultar Dados

```python
# Consultar velas com filtros
resultado = plugin.consultar(
    tabela="velas",
    filtros={"ativo": "BTCUSDT", "timeframe": "15m"},
    campos=["ativo", "open_time", "close", "volume"],
    limite=60,
    ordem="open_time DESC"
)

# Retorno padronizado:
# {
#     "sucesso": True,
#     "operacao": "SELECT",
#     "tabela": "velas",
#     "dados": [{"ativo": "BTCUSDT", ...}, ...],
#     "mensagem": "60 registro(s) encontrado(s)",
#     "linhas_afetadas": 60,
#     "erro": None,
#     "timestamp": "2025-11-05T..."
# }
```

### Atualizar Dados

```python
# Atualizar velas
resultado = plugin.atualizar(
    tabela="velas",
    filtros={"ativo": "BTCUSDT", "timeframe": "15m", "open_time": "2025-11-05..."},
    dados={"volume": 1500.0, "fechada": True}
)

# Retorno padronizado:
# {
#     "sucesso": True,
#     "operacao": "UPDATE",
#     "tabela": "velas",
#     "dados": {"volume": 1500.0, "fechada": True},
#     "mensagem": "1 registro(s) atualizado(s)",
#     "linhas_afetadas": 1,
#     "erro": None,
#     "timestamp": "2025-11-05T..."
# }
```

### Deletar Dados

```python
# Deletar velas (filtros obrigatórios para segurança)
resultado = plugin.deletar(
    tabela="velas",
    filtros={"ativo": "BTCUSDT", "open_time": "2025-11-05..."}
)

# Retorno padronizado:
# {
#     "sucesso": True,
#     "operacao": "DELETE",
#     "tabela": "velas",
#     "mensagem": "1 registro(s) deletado(s)",
#     "linhas_afetadas": 1,
#     "erro": None,
#     "timestamp": "2025-11-05T..."
# }
```

### Atualizar View Materializada

```python
# Atualizar view materializada
resultado = plugin.atualizar_view_materializada()

# Retorno padronizado:
# {
#     "sucesso": True,
#     "operacao": "REFRESH",
#     "tabela": "mv_velas_agregadas",
#     "mensagem": "View materializada atualizada com sucesso",
#     "linhas_afetadas": 0,
#     "erro": None,
#     "timestamp": "2025-11-05T..."
# }
```

---

## Logs Padronizados

Todas as operações geram logs padronizados para facilitar depuração e auditoria:

```
[BancoDados][INSERT] Inserindo dados na tabela 'velas'
[BancoDados][INSERT] 1 registro(s) inserido(s) na tabela 'velas'

[BancoDados][SELECT] Consultando tabela 'velas'
[BancoDados][SELECT] 60 registro(s) encontrado(s) na tabela 'velas'

[BancoDados][UPDATE] Atualizando tabela 'velas'
[BancoDados][UPDATE] 1 registro(s) atualizado(s) na tabela 'velas'

[BancoDados][DELETE] Deletando da tabela 'velas'
[BancoDados][DELETE] 1 registro(s) deletado(s) da tabela 'velas'
```

---

## Segurança

- **SQL Injection Prevention**: Uso de `sql.Identifier` para tabelas e colunas
- **Validação de Filtros**: UPDATE e DELETE requerem filtros obrigatórios
- **Validação de Dados**: Verificação de tipos e estrutura antes de inserção
- **Rollback Automático**: Transações com rollback em caso de erro

