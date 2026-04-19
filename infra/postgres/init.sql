-- Seismic Command — database bootstrap
-- Runs once on first container start (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Schemas keep user data separate from cached/geo data.
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS rag;

SET search_path TO app, public;
