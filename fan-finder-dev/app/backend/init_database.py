#!/usr/bin/env python3
"""
Initialize database tables in Supabase
Run this once to create all required tables
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client
import sys

# Load environment variables
load_dotenv()

def init_database():
    """Initialize Supabase database tables"""

    try:
        # Get Supabase credentials
        SUPABASE_URL = os.getenv('SUPABASE_URL')
        SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

        # Fallback to config file
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            import json
            secrets_file = os.path.join(os.path.dirname(__file__), 'config', 'secrets.json')
            if os.path.exists(secrets_file):
                with open(secrets_file, 'r') as f:
                    secrets = json.load(f)
                    SUPABASE_URL = secrets.get('supabase', {}).get('url')
                    SUPABASE_SERVICE_KEY = secrets.get('supabase', {}).get('service_key')

        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            print("[ERROR] Supabase credentials not found. Please set SUPABASE_URL and SUPABASE_SERVICE_KEY")
            sys.exit(1)

        # Create Supabase client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("[INFO] Connected to Supabase")

        # SQL to create models table
        create_models_sql = """
        CREATE TABLE IF NOT EXISTS models (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            model_name VARCHAR(255) NOT NULL UNIQUE,
            description TEXT,
            is_active BOOLEAN DEFAULT true,
            tags TEXT[] DEFAULT '{}',
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            CONSTRAINT models_name_not_empty CHECK (model_name != '')
        );

        CREATE INDEX IF NOT EXISTS idx_models_is_active ON models(is_active);
        CREATE INDEX IF NOT EXISTS idx_models_name ON models(model_name);

        CREATE OR REPLACE FUNCTION update_models_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trigger_update_models_updated_at ON models;
        CREATE TRIGGER trigger_update_models_updated_at
        BEFORE UPDATE ON models
        FOR EACH ROW
        EXECUTE FUNCTION update_models_updated_at();

        GRANT SELECT, INSERT, UPDATE, DELETE ON models TO authenticated;
        GRANT SELECT, INSERT, UPDATE, DELETE ON models TO service_role;
        """

        # Execute SQL using Supabase RPC or by creating table directly
        # Since we can't execute raw SQL through Supabase client, we'll verify table exists
        try:
            response = supabase.table('models').select('id').limit(1).execute()
            print("[SUCCESS] Models table already exists")
            return True
        except Exception as e:
            if "does not exist" in str(e).lower() or "relation" in str(e).lower():
                print("[ERROR] Models table does not exist")
                print("\n[SOLUTION] You must manually create the table in Supabase:")
                print("1. Go to your Supabase dashboard: https://supabase.com/dashboard")
                print("2. Click on 'SQL Editor' from the left menu")
                print("3. Click 'New Query'")
                print("4. Copy and paste the following SQL:\n")
                print("=" * 60)
                print(create_models_sql)
                print("=" * 60)
                print("\n5. Click 'Run'")
                print("\nAfter creating the table, restart your Fan Finder application.\n")
                return False
            else:
                raise e

    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
