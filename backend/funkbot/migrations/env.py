"""Alembic entry point. The application supplies its already-open connection."""
from alembic import context

connection = context.config.attributes.get('connection')
if connection is None:
    raise RuntimeError('Migrations must be started through the Funk Bot database layer.')

context.configure(connection=connection, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
