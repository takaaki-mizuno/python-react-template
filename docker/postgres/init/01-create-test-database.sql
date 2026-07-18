\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE app_test'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'app_test'
)\gexec
