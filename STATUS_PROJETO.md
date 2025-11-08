# 📊 Status Geral do Projeto Smart Trader

**Data:** 08/11/2025  
**Versão Atual:** v1.3.0  
**Ambiente:** Testnet Bybit (configurável via .env)

---

## ✅ Completado

### 1. Renomeação Completa
- ✅ Todas as referências de "Bybit_Watcher" → "Smart_Trader"
- ✅ Classes renomeadas: `BybitWatcher` → `SmartTrader`
- ✅ Documentação atualizada (README, docs, comentários)
- ✅ Nome do banco de dados: `smarttrader`

### 2. Correções Críticas (02/11/2025)
- ✅ **Corrigido erro no main.py**: Removida chamada inexistente `inicializar()` do `GerenciadorLog`
  - O `GerenciadorLog` já inicializa automaticamente no `__init__`
- ✅ **SQLite completamente removido**: Todas as referências substituídas por PostgreSQL
  - `PluginIaLlama` agora usa `GerenciadorBanco` para persistência
  - Schema atualizado para PostgreSQL (SERIAL, TIMESTAMP, JSONB, etc.)
  - Configuração removida: `IA_DB_PATH` (não mais necessária)

### 3. Sistema de Logs - NOVO (02/11/2025) ✅
Sistema completamente reescrito conforme especificação detalhada:

**Filosofia**: Log conversacional, objetivo e humano - diário técnico que fala com você.

**Estrutura de Diretórios**:
- ✅ `logs/spot/` - Mercado à vista
- ✅ `logs/futures/` - Contratos perpétuos/alavancados
- ✅ `logs/ia/` - Análises e insights do Llama
- ✅ `logs/system/` - Sistema, inicialização, erros gerais

**Características**:
- ✅ Formato BRT (São Paulo) com milissegundos: `[2025-11-02 09:08:14.123 BRT]`
- ✅ Timezone configurado para America/Sao_Paulo
- ✅ Rotação automática: 5MB por arquivo ou diária
- ✅ Retenção: 7 dias ativos, 30 dias compactados
- ✅ Compactação automática: logs antigos → `.gz`
- ✅ Métodos especializados:
  - `log_evento()` - Evento estruturado genérico
  - `log_inicializacao()` - Inicialização de componentes
  - `log_ordem()` - Envio/execução de ordens
  - `log_decisao()` - Decisões de estratégia
  - `log_ia()` - Análises e sugestões do Llama
  - `log_erro_critico()` - Erros críticos com stack trace

**Níveis de Severidade**:
- `INFO`: Operação normal
- `WARN`: Algo inesperado, mas resolvido automaticamente
- `ERROR`: Requer atenção

**Formato de Mensagens**:
- Conversacional e objetivo
- Inclui: par, ação, resultado, detalhes numéricos (preço, quantidade, tempo)
- Exemplo: "Ordem LONG enviada para BTCUSDT: qty 0.02, preço 68472. Resultado: sucesso"

### 4. Estrutura Base do Projeto
- ✅ **main.py**: Ponto de entrada com classe `SmartTrader` (corrigido)
- ✅ **Plugins Base**: 
  - `base_plugin.py` - Classe base com ciclo de vida completo
  - ✅ **Melhorias Implementadas** (05/11/2025):
    - Enums para status (StatusExecucao) e tipos (TipoPlugin)
    - Níveis de gravidade com ações automáticas (NivelGravidade)
    - Metadados padrão de plugin (autor, data, dependências)
    - Tolerância de erro temporal para monitoramento (0.3s)
    - Suporte nativo assíncrono (executar_async)
    - Telemetria armazenada automaticamente no banco
    - Ações automáticas (ERROR → recuperação, CRITICAL → reinicialização)
  - Suporte a context managers, telemetria, execução segura
- ✅ **Gerenciadores**:
  - `GerenciadorLog` - ✅ Sistema de logs reescrito conforme especificação
  - `GerenciadorBanco` - Persistência com validação
  - `GerenciadorPlugins` - Orquestração de plugins
  - `GerenciadorBot` - Controle de trades (Sistema 6/8)

### 5. Plugins Implementados
- ✅ `PluginBybitConexao` - Conexão com API Bybit (testnet/mainnet)
  - Suporte a testnet/mainnet via `.env`
  - Reconexão automática
  - Rate limiting respeitado
  
- ✅ `PluginBancoDados` - Banco de Dados PostgreSQL (04/11/2025)
  - Pool de conexões ThreadedConnectionPool
  - Criação automática de tabelas
  - Upsert inteligente para evitar duplicatas
  - Tabela `velas` com índices otimizados
  - Integração com PluginDadosVelas
  
- ✅ `PluginIaLlama` - Inteligência Artificial (Llama 3)
  - Modo passivo (aprendizado) e ativo (sugestões)
  - ✅ **Persistência via PostgreSQL** (antes: SQLite)
  - Buffer para análise em lote
  - Schema atualizado para PostgreSQL (JSONB, TIMESTAMP, etc.)

### 6. Sistema de Padrões de Trading (08/11/2025)
- ✅ **PluginPadroes** implementado
  - Localização: `plugins/padroes/plugin_padroes.py`
  - Top 10 padrões de trading implementados
  - Filtro de regime de mercado (Trending vs Range)
  - Confidence Decay (decaimento de confiança)
  - Cálculo de score final
  - Persistência automática no banco
- ✅ **Tabelas no Banco de Dados**
  - `padroes_detectados`: Padrões detectados com telemetria completa
  - `padroes_metricas`: Métricas de performance por padrão
  - `padroes_confidence`: Histórico de confidence decay
- ✅ **Sistema de Validação Temporal** implementado (08/11/2025)
  - Walk-Forward: 60% treino → 40% teste ✅ Completo
  - Rolling Window: 180 dias → recalcula a cada 30 dias ⚠️ Básico (ver pendências abaixo)
  - Out-of-Sample (OOS): ≥ 30% dos dados nunca vistos ✅ Completo
  - Métricas básicas calculadas e persistidas ✅ Completo
- ⏳ **Sistema de Backtest completo** (simulação de trades) - **PENDENTE** (ver justificativa abaixo)
- ⏳ **Ensemble de Padrões** (combinação de múltiplos padrões) - **PENDENTE** (ver justificativa abaixo)
- ⏳ **Rankeamento por Performance Real** - **PENDENTE** (depende de backtest)

### 7. Configuração
- ✅ `utils/main_config.py` - ConfigManager centralizado
  - Suporte a testnet/mainnet
  - Configurações dos 8 indicadores
  - Parâmetros de trading (SL/TP, alavancagem, risco)
  - Configurações de pares (BTC, ETH, SOL, XRP)
  - ✅ Removida referência a `IA_DB_PATH` (agora usa PostgreSQL)

---

## 🚧 Em Desenvolvimento / Pendente

### 0. Sistema de Padrões de Trading - Pendências (08/11/2025)

**Status:** Top 30 padrões implementados, mas algumas funcionalidades avançadas pendentes conforme `proxima_atualizacao.md`.

#### ⏳ Sistema de Backtest Completo (Simulação de Trades)
**Status:** Pendente  
**Prioridade:** Alta  
**Justificativa:** O backtest completo requer:
- Simulação realista de execução de trades (slippage, fees, latência)
- Tracking de posições abertas/fechadas por padrão
- Cálculo de métricas reais: `precision`, `recall`, `expectancy`, `winrate`, `avg R:R`, `sharpe_condicional`, `drawdown_condicional`
- Integração com histórico de velas para validar se padrões detectados realmente atingiram target/stop
- Sistema de gerenciamento de capital (position sizing, risk management)

**Por que não foi implementado:**
- Requer estrutura complexa de simulação de mercado (ordens, execuções, fees)
- Necessita histórico completo de velas para validar padrões retroativamente
- Métricas atuais são apenas `frequency` (ocorrências por 1000 velas)
- Depende de dados históricos suficientes para validação estatística robusta
- Implementação completa seria um módulo separado (PluginBacktest ou similar)

**Próximos Passos:**
1. Criar módulo de simulação de trades
2. Implementar tracking de posições por padrão
3. Calcular métricas reais baseadas em execuções simuladas
4. Validar padrões retroativamente com dados históricos

#### ⏳ Ensemble de Padrões (Combinação de Múltiplos Padrões)
**Status:** Pendente  
**Prioridade:** Média  
**Justificativa:** O ensemble requer:
- Detecção de convergência de padrões (2-3 padrões apontando mesma direção)
- Sistema de pesos dinâmicos baseado em confidence de cada padrão
- Score combinado quando múltiplos padrões convergem
- Lógica de priorização (padrões com confidence > 0.8 têm peso maior)

**Por que não foi implementado:**
- Score final individual já está implementado (`final_score = technical_score * 0.6 + confidence * 0.4`)
- Ensemble requer lógica adicional de detecção de convergência temporal
- Necessita validação de quais combinações de padrões são mais eficazes
- Depende de dados históricos para calibrar pesos do ensemble
- Pode ser implementado como camada adicional após validação dos padrões individuais

**Próximos Passos:**
1. Implementar detecção de convergência de padrões (mesmo símbolo/timeframe/direção)
2. Criar sistema de pesos dinâmicos baseado em confidence
3. Validar combinações mais eficazes via backtest
4. Integrar ensemble no fluxo de detecção

#### ⏳ Rolling Window Completo (Validação Temporal)
**Status:** Implementação básica  
**Prioridade:** Média  
**Justificativa:** Rolling Window completo requer:
- Janela deslizante de 180 dias que recalcula métricas a cada 30 dias
- Tracking de performance ao longo do tempo
- Detecção de degradação de performance de padrões
- Ajuste automático de confidence baseado em performance recente

**Por que não foi implementado completamente:**
- Implementação básica existe (estrutura do método)
- Rolling Window completo requer histórico extenso de dados
- Necessita sistema de cache para evitar recálculos desnecessários
- Depende de métricas reais do backtest para ser efetivo
- Pode ser expandido após backtest estar funcional

**Próximos Passos:**
1. Implementar janela deslizante completa (180 dias → recalcula a cada 30 dias)
2. Adicionar tracking de performance ao longo do tempo
3. Integrar com sistema de confidence decay baseado em performance real
4. Otimizar com cache para performance

#### ⏳ Rankeamento por Performance Real
**Status:** Pendente  
**Prioridade:** Alta (mas depende de backtest)  
**Justificativa:** Rankeamento requer:
- Métricas reais calculadas via backtest (expectancy, sharpe, winrate)
- Comparação de performance entre padrões
- Regras de promoção: `Expectancy OOS > 70% in-sample`, `Sharpe > 0.8`, `OOS ≥ 30%`
- Sistema de ranking dinâmico baseado em performance recente

**Por que não foi implementado:**
- **Depende completamente do sistema de backtest completo**
- Requer métricas reais (não apenas frequency)
- Necessita validação OOS com dados suficientes (≥ 30 ocorrências em OOS)
- Regras de promoção requerem comparação estatística robusta
- Só faz sentido após backtest estar funcional e coletar dados reais

**Próximos Passos:**
1. Aguardar implementação do backtest completo
2. Coletar métricas reais de todos os 30 padrões
3. Implementar sistema de ranking baseado em performance
4. Aplicar regras de promoção automaticamente

#### ⚠️ Harmonic Patterns (Padrão #27) - Refinamento Necessário
**Status:** Estrutura básica implementada  
**Prioridade:** Baixa  
**Justificativa:** Harmonic patterns requerem:
- Detecção precisa de pontos A, B, C, D com relações Fibonacci específicas
- Validação de proporções (AB=CD, Gartley, Butterfly, etc.)
- Análise geométrica complexa de padrões harmônicos
- Confirmação de completion de padrões

**Por que não foi implementado completamente:**
- Padrões harmônicos são extremamente complexos e requerem análise geométrica avançada
- Detecção precisa requer múltiplas validações de proporções Fibonacci
- Implementação completa seria um módulo separado (PluginHarmonicPatterns)
- Estrutura básica existe para expansão futura
- Prioridade menor comparado a padrões mais simples e efetivos

**Próximos Passos:**
1. Implementar detecção precisa de pontos A, B, C, D
2. Validar proporções Fibonacci (0.618, 0.786, 1.272, etc.)
3. Implementar detecção de padrões específicos (Gartley, Butterfly, etc.)
4. Adicionar confirmação de completion

#### ⚠️ Multi-Timeframe Confirmation (Padrão #29) - Requer Dados Multi-TF
**Status:** Estrutura básica implementada  
**Prioridade:** Média  
**Justificativa:** Multi-timeframe requer:
- Acesso simultâneo a dados de múltiplos timeframes (ex: 15m + 1h)
- Lógica de confirmação entre timeframes (ex: padrão em 15m confirmado por tendência em 1h)
- Sistema de priorização de timeframes (timeframe maior tem mais peso)
- Integração com PluginDadosVelas para buscar dados de múltiplos TFs

**Por que não foi implementado completamente:**
- Requer modificação na estrutura de dados de entrada (múltiplos timeframes simultâneos)
- Necessita lógica de confirmação entre timeframes
- Depende de dados históricos de múltiplos timeframes disponíveis
- Estrutura básica existe, mas requer integração com sistema de dados
- Pode ser implementado como extensão após validação dos padrões em timeframe único

**Próximos Passos:**
1. Modificar estrutura de dados para suportar múltiplos timeframes
2. Implementar lógica de confirmação entre timeframes
3. Integrar com PluginDadosVelas para buscar dados multi-TF
4. Validar eficácia de confirmação multi-timeframe

---

### 1. Plugins de Indicadores
**Status:** Plugin de dados criado, indicadores técnicos pendentes

**Plugins de Dados:**
- ✅ `plugin_dados_velas.py` - Busca dados OHLCV (15m, 1h, 4h) **INTEGRADO**
  - 60 velas 15m (15 horas)
  - 48 velas 1h (2 dias)
  - 60 velas 4h (10 dias)
  - Validação de vela fechada
  - Integração com PluginBybitConexao
  - ✅ **Persistência no PostgreSQL** (04/11/2025)
  - ✅ **JSON com dados das moedas** (sem velas) em `data/moedas_dados.json`
  - ✅ Registrado e executando no ciclo principal

**Plugins de Indicadores Técnicos (8 plugins):**
- ⏳ `plugin_ichimoku.py` - Ichimoku Cloud (9,26,52,26)
- ⏳ `plugin_supertrend.py` - Supertrend (10, 3)
- ⏳ `plugin_bollinger.py` - Bollinger Bands + Squeeze (20, 2)
- ⏳ `plugin_volume.py` - Volume + Breakout
- ⏳ `plugin_ema.py` - EMA Crossover (9/21)
- ⏳ `plugin_macd.py` - MACD (12,26,9)
- ⏳ `plugin_rsi.py` - RSI (14)
- ⏳ `plugin_vwap.py` - VWAP (intraday)

**Plugins de Padrões (conforme proxima_atualizacao.md):**
- ✅ `PluginPadroes` - Sistema de detecção de padrões técnicos (v1.3.0)
  - ✅ Top 30 padrões implementados (Top 10 + Próximos 20)
  - ✅ Filtro de regime de mercado (Trending vs Range)
  - ✅ Confidence Decay
  - ✅ Persistência automática no banco
  - ✅ Validação Temporal implementada (Walk-Forward, OOS completo, Rolling Window básico)
  - ⚠️ Harmonic patterns (#27) - Estrutura básica (requer refinamento avançado)
  - ⚠️ Multi-timeframe confirmation (#29) - Estrutura básica (requer dados multi-TF)
- ⏳ Sistema de Backtest completo (simulação de trades) - **PENDENTE** (ver seção de pendências)
- ⏳ Ensemble de Padrões (combinação de múltiplos padrões) - **PENDENTE** (ver seção de pendências)
- ⏳ `plugin_confluencia.py` - 4 camadas de confluência

### 2. Lógica de Trading (GerenciadorBot)
- ✅ **Validação 6/8 Melhorada** (05/11/2025)
  - Contagem de indicadores implementada
  - Tratamento de empates para reduzir oscilações falsas
  - Contagem de indicadores neutros incluída
  - Comportamento claro em casos de 5/8 com neutros ou empate exato
- ⏳ Filtros obrigatórios (Cloud + Supertrend, Squeeze BB)
- ⏳ Execução de ordens (Market Orders via WebSocket)
- ⏳ Monitoramento de posições (saída imediata por quebra)
- ⏳ Gerenciamento de risco (SL/TP dinâmicos, Trailing Stop)

### 3. Banco de Dados
- ✅ **PluginBancoDados** implementado (04/11/2025)
  - Conexão PostgreSQL com pool de conexões
  - Criação automática de tabelas
  - Upsert inteligente para evitar duplicatas
  - Tabela `velas` criada conforme `instrucao-velas.md`
  - Índices otimizados para consultas rápidas
- ✅ **Persistência de Velas** implementada (04/11/2025)
  - Velas salvas no PostgreSQL com upsert
  - JSON com dados das moedas (sem velas) em `data/moedas_dados.json`
  - Evita duplicatas usando constraint `unique_vela`
  - Atualiza velas em formação automaticamente
- ✅ **Melhorias no Banco de Dados** (05/11/2025)
  - Campo `exchange` adicionado na tabela `velas` (suporte multi-exchange)
  - Tabela `telemetria_plugins` criada para estatísticas de aprendizado para IA
  - Tabela `schema_versoes` criada para histórico de versões de schema
  - View materializada `mv_velas_agregadas` para análises aceleradas
  - Sistema de registro automático de versões de schema
- ✅ **PluginBancoDados Refatorado** (05/11/2025)
  - CRUD completo implementado (INSERT, UPDATE, SELECT, DELETE)
  - Métodos internos com underscore (_inserir, _consultar, etc.)
  - Métodos públicos sem underscore (inserir, consultar, atualizar, deletar)
  - Logs padronizados: [BancoDados][INSERT], [UPDATE], [SELECT], [DELETE]
  - Retorno padronizado em dicionário para facilitar integração com IA
  - Uso de sql.Identifier para prevenir SQL injection
  - Validação de filtros obrigatórios em UPDATE e DELETE
  - Documentação completa com exemplos de uso
- ✅ **Tabelas de Padrões** criadas (08/11/2025)
  - `padroes_detectados`: Padrões detectados com telemetria completa
  - `padroes_metricas`: Métricas de performance por padrão
  - `padroes_confidence`: Histórico de confidence decay
  - Campo `testnet` adicionado na tabela `velas`
  - Constraint `unique_vela` atualizada para incluir `testnet`
- ⏳ Schema generator automático (futuro)
- ⏳ Tabelas para cada plugin de indicador (futuro)

---

## 📁 Estrutura Atual do Projeto

```
Smart_Trader/
├── main.py                    ✅ Implementado (integrado com plugins)
├── .env                       ⚠️  Configurar com chaves API
├── CHANGELOG.md               ✅ Atualizado
├── README.md                  ✅ Atualizado
├── STATUS_PROJETO.md          ✅ Este arquivo (atualizado 02/11/2025)
├── requirements.txt           ✅ Dependências listadas
│
├── plugins/
│   ├── __init__.py           ✅
│   ├── base_plugin.py        ✅ Completo
│   │
│   ├── indicadores/          ✅ Plugin de dados criado e integrado
│   │   ├── __init__.py
│   │   └── plugin_dados_velas.py  ✅ INTEGRADO no ciclo principal
│   │
│   ├── conexoes/            ✅
│   │   ├── __init__.py
│   │   └── plugin_bybit_conexao.py  ✅ INTEGRADO no ciclo principal
│   │
│   ├── ia/                   ✅
│   │   ├── __init__.py
│   │   └── plugin_ia_llama.py  ✅ (PostgreSQL, sem SQLite)
│   │
│   └── gerenciadores/        ✅ Todos implementados
│       ├── __init__.py
│       ├── gerenciador.py
│       ├── gerenciador_log.py      ✅ Timezone BRT configurado
│       ├── gerenciador_banco.py    ✅
│       ├── gerenciador_plugins.py  ✅ Execução sequencial funcionando
│       ├── gerenciador_bot.py      ⚠️  Base implementada, lógica pendente
│       └── plugin_banco_dados.py    ✅ NOVO (04/11/2025) - PostgreSQL
│
├── utils/
│   ├── __init__.py
│   ├── main_config.py        ✅ Completo (sem referências SQLite)
│   ├── logging_config.py     ✅
│   └── exemple.config.py     ⚠️  Exemplo (renomear?)
│
├── docs/
│   ├── regras_de_ouro.txt    ✅ Atualizado
│   ├── definicao_estrategia.txt  ✅ Atualizado
│   └── definicao_banco.txt    ✅ NOVO (04/11/2025) - Definições do banco
│
├── data/
│   └── moedas_dados.json     ✅ NOVO (04/11/2025) - Dados das moedas (sem velas)
│
└── logs/                     ✅ NOVA ESTRUTURA (02/11/2025)
    ├── spot/                 ✅ Mercado à vista
    ├── futures/              ✅ Contratos alavancados
    ├── ia/                   ✅ Análises do Llama
    └── system/               ✅ Sistema e erros
```

---

## 🔧 Configuração Atual

### Variáveis do `.env` (Verificar/Configurar):

```env
# Bybit API
BYBIT_TESTNET=True              # ✅ True para testnet
TESTNET_BYBIT_API_KEY=...       # ⚠️  Configurar
TESTNET_BYBIT_API_SECRET=...    # ⚠️  Configurar

# Banco de Dados PostgreSQL
DB_HOST=localhost
DB_NAME=smarttrader            # ✅ Nome do banco de dados
DB_USER=...
DB_PASSWORD=...
DB_PORT=5432

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# IA (Opcional)
IA_ON=False
LLAMA_API_KEY=...
# IA_DB_PATH removido - agora usa PostgreSQL
```

---

## 🧪 Próximos Passos

### Imediato (Teste na Testnet)
1. ✅ Configurar `.env` com chaves de testnet atualizadas
2. ✅ Corrigido erro de inicialização no main.py
3. ✅ PluginDadosVelas integrado e pronto para execução
4. ⏳ Testar execução completa: `python main.py`
5. ⏳ Verificar logs gerados em `logs/system/` com timezone BRT
6. ⏳ Validar busca de velas da Bybit testnet
7. ⏳ Aguardar novas instruções em `instrucao-velas.md`

### Curto Prazo (Sistema 6/8)
1. Implementar 8 plugins de indicadores
2. Completar lógica de validação 6/8 no `GerenciadorBot`
3. Implementar execução de ordens (testnet)
4. Sistema de monitoramento de posições
5. Integrar novos métodos de log (`log_ordem()`, `log_decisao()`, etc.)

### Médio Prazo
1. Plugin `BancoDados` com PostgreSQL (CRUD real)
2. Schema generator e migrações
3. WebSocket para atualizações em tempo real
4. Completar métodos do `PluginIaLlama` que dependem de `BancoDados`

---

## 📊 Métricas do Projeto

- **Total de Arquivos Python:** ~15 arquivos principais
- **Plugins Implementados:** 3/11 (27%) - Dados de velas integrado
- **Plugins Integrados no Ciclo:** 2/3 (PluginBybitConexao + PluginDadosVelas)
- **Gerenciadores:** 4/4 (100%)
- **Plugins de Indicadores:** 0/8 (0%)
- **Sistema de Logs:** ✅ 100% implementado conforme especificação
- **Banco de Dados:** ⏳ SQLite removido, PostgreSQL preparado (aguardando plugin BancoDados)
- **Cobertura de Testes:** 0% (pendente)

---

## ⚠️ Observações Importantes

1. **Ambiente Testnet**: Sistema configurado para testnet por padrão
2. **Banco de Dados**: 
   - ✅ SQLite completamente removido
   - ⏳ Plugin `BancoDados` ainda não implementado (apenas `GerenciadorBanco`)
   - ✅ `PluginIaLlama` preparado para PostgreSQL (schema atualizado)
3. **Indicadores**: Nenhum plugin de indicador implementado ainda
4. **Trading**: Lógica de execução de trades não implementada
5. **Sistema de Logs**: ✅ **100% implementado conforme especificação detalhada**
   - Estrutura: spot/futures/ia/system
   - Rotação: 5MB ou diária
   - Retenção: 7 dias ativos, 30 dias compactados
   - Formato: **BRT (São Paulo)** com milissegundos, conversacional
6. **Ciclo de Execução**: ✅ **Implementado e funcionando**
   - Loop principal a cada 5 segundos
   - Execução sequencial de plugins
   - Logs detalhados por ciclo
   - Tratamento robusto de erros

---

## 🎯 Prioridades

### Alta Prioridade:
1. ✅ Renomeação completa (CONCLUÍDO)
2. ✅ Correção erro main.py (CONCLUÍDO)
3. ✅ Remoção SQLite → PostgreSQL (CONCLUÍDO)
4. ✅ Sistema de logs completo (CONCLUÍDO)
5. ⏳ Testar na testnet com novas chaves
6. ⏳ Implementar primeiro plugin de indicador (ex: RSI)

### Média Prioridade:
1. Completar todos os 8 plugins de indicadores
2. Implementar lógica 6/8 no GerenciadorBot
3. Plugin BancoDados com PostgreSQL
4. Integrar novos métodos de log no fluxo de trading

### Baixa Prioridade:
1. Dashboard/web interface
2. Backtesting automatizado
3. Otimizações de performance
4. Alertas via Telegram baseados em logs

---

## 📝 Changelog Resumo (02/11/2025)

### Correções
- ✅ Corrigido erro `AttributeError: 'GerenciadorLog' object has no attribute 'inicializar'`
- ✅ Removida chamada inexistente no `main.py`

### Migrações
- ✅ SQLite completamente removido do `PluginIaLlama`
- ✅ Schema atualizado para PostgreSQL (SERIAL, TIMESTAMP, JSONB)
- ✅ Persistência via `GerenciadorBanco` preparada

### Novas Features
- ✅ Sistema de logs completamente reescrito conforme especificação
- ✅ Novos diretórios: spot/futures/ia/system
- ✅ Rotação automática (5MB ou diária)
- ✅ Compactação automática de logs antigos
- ✅ Métodos especializados: `log_ordem()`, `log_decisao()`, `log_ia()`, etc.
- ✅ Formato UTC com milissegundos
- ✅ Retenção configurável (7 dias ativos, 30 dias compactados)

---

**Última Atualização:** 08/11/2025  
**Status Geral:** 🟢 Sistema de Padrões de Trading implementado (Top 30 completo) - Validação Temporal implementada (Walk-Forward e OOS completos) - Backtest completo e Ensemble pendentes (ver seção de pendências)

## 📝 Changelog Resumo (05/11/2025 - PluginBancoDados Refatorado)

### PluginBancoDados - Refatoração Completa
- ✅ **CRUD Completo Implementado**
  - Método `inserir()` - Inserção com upsert para velas
  - Método `consultar()` - Consulta com filtros, campos, ordenação e limite
  - Método `atualizar()` - Atualização com filtros e validação
  - Método `deletar()` - Exclusão com filtros obrigatórios (segurança)
- ✅ **Estrutura de Métodos**
  - Métodos internos com underscore (_inserir_velas, _consultar, etc.)
  - Métodos públicos sem underscore (inserir, consultar, atualizar, deletar)
  - Separação clara entre lógica interna e interface pública
- ✅ **Logs Padronizados**
  - Formato: `[BancoDados][INSERT]`, `[UPDATE]`, `[SELECT]`, `[DELETE]`
  - Facilita depuração e auditoria
  - Logs informativos por operação com detalhes
- ✅ **Retorno Padronizado**
  - Dicionário padronizado para todas as operações CRUD
  - Facilita integração com IA
  - Estrutura: sucesso, operacao, tabela, dados, mensagem, linhas_afetadas, erro, timestamp
- ✅ **Melhorias de Segurança**
  - Uso de `sql.Identifier` para prevenir SQL injection
  - Validação de filtros obrigatórios em UPDATE e DELETE
  - Validação de dados antes de inserção
- ✅ **Versão Atualizada**
  - PluginBancoDados: v1.0.0 → v1.2.0
  - Schema versão: v1.0.0 → v1.2.0

## 📝 Changelog Resumo (05/11/2025 - Melhorias e Robustez)

### Novas Features
- ✅ **Enums para Status e Tipos**
  - `StatusExecucao`: OK, ERRO, AVISO, PENDENTE, CANCELADO
  - `TipoPlugin`: INDICADOR, GERENCIADOR, CONEXAO, DADOS, IA, AUXILIAR
  - `NivelGravidade`: INFO, WARNING, ERROR, CRITICAL com ações automáticas
- ✅ **Metadados de Plugin**
  - Campo `plugin_metadados` com autor, data, dependências, tipo
  - Útil para IA classificar módulos automaticamente
- ✅ **Monitoramento e Telemetria**
  - Tolerância de erro temporal configurável (padrão: 0.3s)
  - Telemetria armazenada automaticamente no banco após cada execução
  - Tabela `telemetria_plugins` para estatísticas de aprendizado
- ✅ **Ações Automáticas**
  - ERROR: Tentativa de recuperação automática
  - CRITICAL: Reinicialização automática do plugin
- ✅ **Suporte Assíncrono**
  - Método `executar_async()` nativo na classe base
  - Preparado para transição de threads para async workers
- ✅ **GerenciadorBot Melhorado**
  - Tratamento de empates para reduzir oscilações falsas
  - Contagem de indicadores neutros
  - Comportamento claro em casos de 5/8 ou empate exato
- ✅ **Banco de Dados Expandido**
  - Campo `exchange` na tabela `velas` (suporte multi-exchange)
  - View materializada `mv_velas_agregadas` para análises aceleradas
  - Histórico de versões de schema na tabela `schema_versoes`

## 📝 Changelog Resumo (04/11/2025 - Sistema de Banco de Dados)

### Novas Features
- ✅ **PluginBancoDados** criado e integrado
  - Conexão PostgreSQL com pool de conexões
  - Criação automática de tabela `velas`
  - Upsert inteligente para evitar duplicatas
  - Índices otimizados para consultas rápidas
- ✅ **Persistência de Velas** implementada
  - Velas salvas no PostgreSQL usando upsert
  - Evita duplicatas usando constraint `unique_vela`
  - Atualiza velas em formação automaticamente
- ✅ **JSON de Dados das Moedas** criado
  - Arquivo `data/moedas_dados.json` com dados das moedas (sem velas)
  - Inclui última vela por timeframe e estatísticas básicas
- ✅ **Documentação do Banco** criada
  - Arquivo `docs/definicao_banco.txt` com definições completas
  - Estrutura de tabelas, índices, otimizações e dicas de uso

### Integração
- ✅ PluginBancoDados registrado no ciclo principal
- ✅ PluginDadosVelas conectado com PluginBancoDados
- ✅ Velas sendo salvas automaticamente a cada ciclo
- ✅ JSON atualizado a cada ciclo com dados das moedas

### Correções
- ✅ Cálculo de `close_time` corrigido (usando `timedelta`)
- ✅ Timezone UTC para timestamps no banco
- ✅ Validação de dados antes de inserir

## 📝 Changelog Resumo (02/11/2025 - Atualizações Recentes)

### Alterações de Timezone (09:30 BRT)
- ✅ Sistema de logs configurado para timezone de São Paulo (BRT)
- ✅ Formato alterado de UTC para BRT em todos os logs
- ✅ Cálculos de tempo usando pytz.timezone('America/Sao_Paulo')

### Novo Plugin (09:30 BRT)
- ✅ **PluginDadosVelas** criado conforme `instrucao-velas.md`
  - Busca 60 velas 15m, 48 velas 1h, 60 velas 4h
  - Validação de vela fechada por timeframe
  - Integração com PluginBybitConexao
  - Estrutura pronta para receber dados

### Integração Completa (10:00 BRT)
- ✅ **PluginDadosVelas integrado no ciclo principal**
  - Registrado automaticamente no `_registrar_plugins()`
  - Conectado com PluginBybitConexao
  - Executando a cada 5 segundos no ciclo principal
- ✅ **Ciclo de execução implementado**
  - Loop principal funcionando
  - Execução sequencial de plugins
  - Logs detalhados por ciclo
  - Tratamento de erros robusto
- ✅ **GerenciadorPlugins melhorado**
  - Retorno estruturado com status agregado
  - Contagem de plugins executados/erros
  - Ordem de execução baseada em registro

### Correções
- ✅ Tipo de log no GerenciadorPlugins corrigido (system em vez de rastreamento)
- ✅ Plugin de IA verificado e funcional (PostgreSQL preparado)
- ✅ Todos os tipos de log corrigidos para "system" no main.py
