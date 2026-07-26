"""
Supabase client singleton — used by all handlers.
Uses the service-role key so writes work regardless of RLS state.
"""
from supabase import create_client, Client
from bot.config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
