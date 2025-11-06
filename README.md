# Smart_Trader - Sistema 6/8 Trading Bot

Bot de trading automatizado para Bybit utilizando 8 indicadores técnicos com validação cruzada (Sistema 6/8).

## 📋 Descrição

O sistema utiliza 8 indicadores técnicos e executa trades quando **6 ou mais** indicadores apontam na mesma direção. Qualquer reversão em 1 indicador encerra a posição imediatamente.

### Os 8 Indicadores

1. **Ichimoku Cloud** (9,26,52,26)
2. **Supertrend** (10, 3)
3. **Bollinger Bands + Squeeze** (20, 2)
4. **Volume + Breakout**
5. **EMA Crossover** (9/21)
6. **MACD** (12,26,9)
7. **RSI** (14)
8. **VWAP** (intraday)

## 🏗️ Estrutura do Projeto

```
Smart_Trader/
├── main.py                 # Ponto de entrada principal
├── .env                    # Configurações sensíveis (não versionado)
├── CHANGELOG.md            # Histórico de alterações
├── requirements.txt        # Dependências Python
│
├── plugins/
│   ├── __init__.py
│   ├── base_plugin.py      # Classe base para todos os plugins
│   │
│   ├── indicadores/        # Plugins de indicadores técnicos
│   │   ├── __init__.py
│   │   ├── plugin_ichimoku.py
│   │   ├── plugin_supertrend.py
│   │   ├── plugin_bollinger.py
│   │   ├── plugin_volume.py
│   │   ├── plugin_ema.py
│   │   ├── plugin_macd.py
│   │   ├── plugin_rsi.py
│   │   └── plugin_vwap.py
│   │
│   └── gerenciadores/      # Gerenciadores principais
│       ├── __init__.py
│       ├── gerenciador.py           # Classe base
│       ├── gerenciador_log.py       # Sistema de logs
│       ├── gerenciador_banco.py     # Persistência de dados
│       ├── gerenciador_plugins.py   # Orquestração de plugins
│       └── gerenciador_bot.py       # Controle de trades
│
├── utils/
│   ├── __init__.py
│   ├── config.py           # Configuração centralizada
│   └── logging_config.py   # Helpers de logging
│
└── logs/                   # Logs organizados por tipo
    ├── bot/
    ├── banco/
    ├── dados/
    ├── sinais/
    ├── erros/
    └── rastreamento/
```

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/MarcusAbenAthar/Smart_Trader.git
cd Smart_Trader
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure o arquivo .env

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
# Bybit API (Mainnet ou Testnet)
BYBIT_TESTNET=True  # True para testnet, False para mainnet
BYBIT_API_KEY=sua_api_key_aqui
BYBIT_API_SECRET=sua_api_secret_aqui
TESTNET_BYBIT_API_KEY=sua_testnet_api_key  # Se usar testnet
TESTNET_BYBIT_API_SECRET=sua_testnet_api_secret  # Se usar testnet

# Banco de Dados PostgreSQL
DB_HOST=localhost
DB_NAME=smarttrader
DB_USER=seu_usuario
DB_PASSWORD=sua_senha

# Telegram (opcional, para notificações)
TELEGRAM_BOT_TOKEN=seu_bot_token
TELEGRAM_CHAT_ID=seu_chat_id
```

## 🎯 Uso

### Executar o bot

```bash
python main.py
```

### Modo Testnet vs Mainnet

Edite a variável `BYBIT_TESTNET` no arquivo `.env`:
- `True`: Usa a testnet (recomendado para testes)
- `False`: Usa a mainnet (ambiente real)

## 📊 Estratégia de Trading

### Regras de Entrada

- **Mínimo 6/8 indicadores** devem estar alinhados na mesma direção
- **Filtros obrigatórios:**
  1. Cloud + Supertrend devem estar OK
  2. Squeeze BB (< 0.04 por ≥5 velas)
  3. Rompimento BB + Volume > 2x média

### Regras de Saída

Qualquer um dos seguintes eventos fecha a posição imediatamente:
- Supertrend muda de cor
- Preço cruza o lado oposto da Cloud
- MACD histograma reverte
- Volume < 40% da média(20)
- Distância VWAP > 3% sem volume > 1.5x média

### Gerenciamento de Risco

- **SL**: Nível mais próximo entre base da Cloud ou Supertrend
- **TP**: 2.3 × distância do SL (R:R fixo)
- **Trailing Stop**: Supertrend (ativa após +1.0 × SL)
- **Tamanho da posição**: Ajustado por ATR(14) e liquidez (máx 2% capital)

## 🔧 Configuração de Pares

Configurações padrão por par (em `utils/config.py`):

| Par       | Timeframe | Alavancagem | Risco |
|-----------|-----------|-------------|-------|
| BTC/USDT  | 15m       | 3x          | 1.5%  |
| ETH/USDT  | 15m       | 3x          | 1.2%  |
| SOL/USDT  | 5m        | 2x          | 1.0%  |
| XRP/USDT  | 5m        | 2x          | 0.8%  |

## 📝 Documentação

- **Regras de Ouro**: `docs/regras_de_ouro.txt`
- **Definição da Estratégia**: `docs/definicao_estrategia.txt`
- **Changelog**: `CHANGELOG.md`

## 🧩 Arquitetura

### Plugins

Todos os plugins seguem o padrão:
- Herdam de `Plugin` (em `plugins/base_plugin.py`)
- Ciclo de vida: `inicializar()` → `executar()` → `finalizar()`
- Armazenam dados em `self.dados_completos` (crus e analisados)
- Persistem dados via `GerenciadorBanco`

### Gerenciadores

- **GerenciadorLog**: Sistema de logs estruturado
- **GerenciadorBanco**: Validação e persistência de dados
- **GerenciadorPlugins**: Orquestração do ciclo de vida dos plugins
- **GerenciadorBot**: Controle de trades e validação 6/8

## ⚠️ Avisos

- **SEMPRE use testnet para testes**
- **Nunca compartilhe suas chaves API**
- **O bot opera com capital real em mainnet - use com cuidado**
- **Recomendado**: Comece com valores baixos até validar a estratégia

## 📄 Licença

Ver arquivo `LICENSE` para detalhes.

## 🔗 Links

- Repositório: https://github.com/MarcusAbenAthar/Smart_Trader
- Documentação: `docs/`

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, siga as regras definidas em `docs/regras_de_ouro.txt`.

---

**Desenvolvido seguindo as Regras de Ouro do projeto**
