#!/usr/bin/env python3
"""
SQLite to Postgres migration script for tenant bot data.

Migrates all tenant data from local SQLite database to a Postgres database.
Safe to rerun - uses upserts to handle existing data.

Usage:
    python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db

Environment:
    DATABASE_URL: Postgres connection string (required for migration)
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import psycopg
except ImportError:
    print("Error: psycopg is required. Install with: pip install psycopg[binary]")
    sys.exit(1)


def get_sqlite_connection(db_path: str) -> sqlite3.Connection:
    """Get SQLite connection."""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_connection(database_url: str) -> psycopg.Connection:
    """Get Postgres connection."""
    try:
        conn = psycopg.connect(database_url)
        return conn
    except psycopg.OperationalError as e:
        raise ConnectionError(f"Failed to connect to Postgres: {e}")


def init_postgres_schema(pg_conn: psycopg.Connection) -> None:
    """Ensure Postgres schema is initialized."""
    cursor = pg_conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata JSONB
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_telegram_config (
            tenant_id TEXT PRIMARY KEY,
            telegram_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            telegram_bot_token TEXT,
            telegram_chat_id TEXT,
            telegram_message_template TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            session_name TEXT,
            session_date TEXT NOT NULL,
            session_state TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata JSONB,
            PRIMARY KEY (tenant_id, session_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            commenter TEXT NOT NULL,
            comment TEXT NOT NULL,
            comment_id TEXT,
            collected_at TEXT NOT NULL,
            printed_at TEXT,
            profile_url TEXT,
            order_date TEXT,
            source_host TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata JSONB,
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                ON DELETE CASCADE,
            FOREIGN KEY (tenant_id, session_id) REFERENCES sessions(tenant_id, session_id)
                ON DELETE CASCADE
        )
    """)
    
    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_tenant_session 
        ON orders(tenant_id, session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_tenant_date 
        ON orders(tenant_id, order_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_tenant 
        ON sessions(tenant_id, session_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_telegram_chat_id 
        ON tenant_telegram_config(telegram_chat_id)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_enabled_tenant_chat
        ON tenant_telegram_config (telegram_chat_id)
        WHERE telegram_enabled = true
    """)
    
    pg_conn.commit()


def get_sqlite_counts(sqlite_conn: sqlite3.Connection) -> Dict[str, int]:
    """Get row counts from SQLite."""
    cursor = sqlite_conn.cursor()
    counts = {}
    
    for table in ['tenants', 'tenant_telegram_config', 'sessions', 'orders']:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        row = cursor.fetchone()
        counts[table] = row['count'] if row else 0
    
    return counts


def get_postgres_counts(pg_conn: psycopg.Connection) -> Dict[str, int]:
    """Get row counts from Postgres."""
    cursor = pg_conn.cursor()
    counts = {}
    
    for table in ['tenants', 'tenant_telegram_config', 'sessions', 'orders']:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        row = cursor.fetchone()
        counts[table] = row[0] if row else 0
    
    return counts


def migrate_tenants(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    """Migrate tenants table."""
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    sqlite_cursor.execute("SELECT * FROM tenants")
    rows = sqlite_cursor.fetchall()
    
    migrated = 0
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO tenants (tenant_id, created_at, updated_at, metadata)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                updated_at = EXCLUDED.updated_at,
                metadata = EXCLUDED.metadata
        """, (
            row['tenant_id'],
            row['created_at'],
            row['updated_at'],
            row['metadata']
        ))
        migrated += 1
    
    pg_conn.commit()
    return migrated


def migrate_tenant_telegram_config(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    """Migrate tenant_telegram_config table."""
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    sqlite_cursor.execute("SELECT * FROM tenant_telegram_config")
    rows = sqlite_cursor.fetchall()
    
    migrated = 0
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO tenant_telegram_config
            (tenant_id, telegram_enabled, telegram_bot_token, telegram_chat_id,
             telegram_message_template, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                telegram_enabled = EXCLUDED.telegram_enabled,
                telegram_bot_token = EXCLUDED.telegram_bot_token,
                telegram_chat_id = EXCLUDED.telegram_chat_id,
                telegram_message_template = EXCLUDED.telegram_message_template,
                updated_at = EXCLUDED.updated_at
        """, (
            row['tenant_id'],
            bool(row['telegram_enabled']),  # Convert SQLite int to bool
            row['telegram_bot_token'],
            row['telegram_chat_id'],
            row['telegram_message_template'],
            row['created_at'],
            row['updated_at']
        ))
        migrated += 1
    
    pg_conn.commit()
    return migrated


def migrate_sessions(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    """Migrate sessions table."""
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    sqlite_cursor.execute("SELECT * FROM sessions")
    rows = sqlite_cursor.fetchall()
    
    migrated = 0
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO sessions
            (session_id, tenant_id, session_name, session_date, session_state,
             created_at, updated_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, session_id) DO UPDATE SET
                session_name = EXCLUDED.session_name,
                session_state = EXCLUDED.session_state,
                updated_at = EXCLUDED.updated_at,
                metadata = EXCLUDED.metadata
        """, (
            row['session_id'],
            row['tenant_id'],
            row['session_name'],
            row['session_date'],
            row['session_state'],
            row['created_at'],
            row['updated_at'],
            row['metadata']
        ))
        migrated += 1
    
    pg_conn.commit()
    return migrated


def migrate_orders(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> int:
    """Migrate orders table."""
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    sqlite_cursor.execute("SELECT * FROM orders")
    rows = sqlite_cursor.fetchall()
    
    migrated = 0
    for row in rows:
        pg_cursor.execute("""
            INSERT INTO orders
            (order_id, tenant_id, session_id, commenter, comment, comment_id,
             collected_at, printed_at, profile_url, order_date, source_host,
             created_at, updated_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (order_id) DO UPDATE SET
                commenter = EXCLUDED.commenter,
                comment = EXCLUDED.comment,
                profile_url = EXCLUDED.profile_url,
                updated_at = EXCLUDED.updated_at,
                metadata = EXCLUDED.metadata
        """, (
            row['order_id'],
            row['tenant_id'],
            row['session_id'],
            row['commenter'],
            row['comment'],
            row['comment_id'],
            row['collected_at'],
            row['printed_at'],
            row['profile_url'],
            row['order_date'],
            row['source_host'],
            row['created_at'],
            row['updated_at'],
            row['metadata']
        ))
        migrated += 1
    
    pg_conn.commit()
    return migrated


def get_per_tenant_counts(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection) -> None:
    """Print per-tenant row counts for verification."""
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    # Get unique tenant IDs
    sqlite_cursor.execute("SELECT DISTINCT tenant_id FROM tenants ORDER BY tenant_id")
    tenants = [row['tenant_id'] for row in sqlite_cursor.fetchall()]
    
    print("\nPer-tenant session and order counts:")
    print("=" * 60)
    print(f"{'Tenant ID':<30} {'SQLite Sessions':<15} {'Postgres Sessions':<15}")
    print("-" * 60)
    
    for tenant_id in tenants:
        sqlite_cursor.execute(
            "SELECT COUNT(*) as count FROM sessions WHERE tenant_id = ?",
            (tenant_id,)
        )
        sqlite_session_count = sqlite_cursor.fetchone()['count']
        
        pg_cursor.execute(
            "SELECT COUNT(*) as count FROM sessions WHERE tenant_id = %s",
            (tenant_id,)
        )
        pg_session_count = pg_cursor.fetchone()[0]
        
        print(f"{tenant_id:<30} {sqlite_session_count:<15} {pg_session_count:<15}")
    
    print("\n" + "=" * 60)
    print(f"{'Tenant ID':<30} {'SQLite Orders':<15} {'Postgres Orders':<15}")
    print("-" * 60)
    
    for tenant_id in tenants:
        sqlite_cursor.execute(
            "SELECT COUNT(*) as count FROM orders WHERE tenant_id = ?",
            (tenant_id,)
        )
        sqlite_order_count = sqlite_cursor.fetchone()['count']
        
        pg_cursor.execute(
            "SELECT COUNT(*) as count FROM orders WHERE tenant_id = %s",
            (tenant_id,)
        )
        pg_order_count = pg_cursor.fetchone()[0]
        
        print(f"{tenant_id:<30} {sqlite_order_count:<15} {pg_order_count:<15}")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate SQLite tenant data to Postgres",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migrate_sqlite_to_postgres.py --sqlite data/tenant_data.db
  DATABASE_URL="postgresql://..." python scripts/migrate_sqlite_to_postgres.py
        """
    )
    
    parser.add_argument(
        "--sqlite",
        default="data/tenant_data.db",
        help="Path to SQLite database (default: data/tenant_data.db)"
    )
    
    args = parser.parse_args()
    
    # Get Postgres connection string from environment
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable is required")
        print("Set it with: export DATABASE_URL='postgresql://...'")
        sys.exit(1)
    
    try:
        print("🔍 Connecting to SQLite...")
        sqlite_conn = get_sqlite_connection(args.sqlite)
        print(f"✓ Connected to SQLite: {args.sqlite}")
        
        print("🔍 Connecting to Postgres...")
        pg_conn = get_postgres_connection(database_url)
        print("✓ Connected to Postgres")
        
        print("📋 Initializing Postgres schema...")
        init_postgres_schema(pg_conn)
        print("✓ Schema initialized")
        
        print("\n📊 Pre-migration counts:")
        print("=" * 40)
        sqlite_counts = get_sqlite_counts(sqlite_conn)
        for table, count in sqlite_counts.items():
            print(f"  SQLite {table:<25} {count:>5}")
        
        print("\n🚀 Starting migration...")
        print("=" * 40)
        
        tenants_migrated = migrate_tenants(sqlite_conn, pg_conn)
        print(f"✓ Migrated {tenants_migrated} tenants")
        
        configs_migrated = migrate_tenant_telegram_config(sqlite_conn, pg_conn)
        print(f"✓ Migrated {configs_migrated} tenant configs")
        
        sessions_migrated = migrate_sessions(sqlite_conn, pg_conn)
        print(f"✓ Migrated {sessions_migrated} sessions")
        
        orders_migrated = migrate_orders(sqlite_conn, pg_conn)
        print(f"✓ Migrated {orders_migrated} orders")
        
        print("\n📊 Post-migration counts:")
        print("=" * 40)
        pg_counts = get_postgres_counts(pg_conn)
        for table, count in pg_counts.items():
            print(f"  Postgres {table:<22} {count:>5}")
        
        # Verify counts match
        print("\n✅ Verification:")
        print("=" * 40)
        all_match = True
        for table in sqlite_counts:
            if sqlite_counts[table] == pg_counts[table]:
                print(f"✓ {table:<25} counts match ({sqlite_counts[table]})")
            else:
                print(f"✗ {table:<25} count mismatch!")
                print(f"  SQLite: {sqlite_counts[table]}, Postgres: {pg_counts[table]}")
                all_match = False
        
        # Show per-tenant counts
        get_per_tenant_counts(sqlite_conn, pg_conn)
        
        if all_match:
            print("\n🎉 Migration completed successfully!")
            return 0
        else:
            print("\n⚠️  Migration completed with mismatches. Please review above.")
            return 1
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    sys.exit(main())
