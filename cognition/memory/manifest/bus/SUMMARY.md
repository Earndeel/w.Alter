The Walter bus delivers events between modules (PostgreSQL schema `bus`, LISTEN/NOTIFY) and keeps each consumer's processing cursor, so modules react to changes instead of polling.
