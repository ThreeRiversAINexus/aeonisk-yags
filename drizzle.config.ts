import { defineConfig } from 'drizzle-kit';
import { config } from 'dotenv';

config();

export default defineConfig({
  schema: './src/infrastructure/database/schema.ts',
  out: './drizzle',
  driver: 'pg',
  dbCredentials: {
    connectionString: process.env['DATABASE_URL'] || 'postgresql://aeonisk:aeonisk_password@localhost:5432/aeonisk_game'
  }
});