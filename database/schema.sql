CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(20) DEFAULT 'binance',
    price DECIMAL(18,8),
    change_percent DECIMAL(8,4),
    volume DECIMAL(20,8),
    sma_5m DECIMAL(18,8),
    ema_50 DECIMAL(18,8),
    ema_200 DECIMAL(18,8),
    rsi DECIMAL(5,2),
    macd DECIMAL(10,6),
    bollinger_upper DECIMAL(18,8),
    bollinger_lower DECIMAL(18,8),
    support DECIMAL(18,8),
    resistance DECIMAL(18,8),
    ai_action VARCHAR(10),
    ai_confidence INT CHECK (ai_confidence BETWEEN 0 AND 100),
    gemini_action VARCHAR(10),
    llama_action VARCHAR(10),
    qwen_action VARCHAR(10),
    priority VARCHAR(10),
    category VARCHAR(20),
    patterns TEXT[],
    reasoning TEXT
);

CREATE INDEX IF NOT EXISTS idx_symbol_time ON alerts(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_priority ON alerts(priority);

CREATE TABLE IF NOT EXISTS price_history (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    open DECIMAL(18,8),
    high DECIMAL(18,8),
    low DECIMAL(18,8),
    close DECIMAL(18,8),
    volume DECIMAL(20,8),
    PRIMARY KEY (symbol, timestamp)
);

