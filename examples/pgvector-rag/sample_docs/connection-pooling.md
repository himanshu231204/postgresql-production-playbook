category: performance
# Connection pooling
Each PostgreSQL connection is a separate server process, so opening thousands of direct connections wastes memory. Put a pooler such as PgBouncer in front of the database, or size the application pool carefully. In transaction pooling mode, session level features like prepared statements and advisory locks need extra care.
