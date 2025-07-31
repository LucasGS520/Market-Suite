-- Script Lua para implementação de Sliding-window Rate Limiter no Redis
-- Baseado na Lógica do RateLimiter em Python

-- KEYS[1] = Chave do Redis para o sorted set
-- ARGV[1] = Timestamp atual em milissegundos
-- ARGV[2] = Tamanho da janela em milissegundos
-- ARGV[3] = Limite máximo de requisições na janela

-- Retorna 1 se estiver abaixo ou igual ao limite, 0 caso contrário

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Calcula o início da janela
local window_start = now_ms - window_ms

-- Remove timestamp fora da janela atual
redis.call("ZREMRANGEBYSCORE", key, 0, window_start)

-- Adiciona o timestamp atual ao sorted set
redis.call("ZADD", key, now_ms, now_ms)

-- Contagem de quantos membros existem na janela
local count = tonumber(redis.call("ZCARD", key))

-- Garante que a chave expire automaticamente após a duração da janela
local window_sec = math.floor(window_ms / 1000) + 1
redis.call("EXPIRE", key, window_sec)

-- Se o numero de timestamp na janela for <= limite, permite; casos contrários são bloqueados
if count <= limit then
    return 1
else
    return 0
end
