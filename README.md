# Aeonisk Backend

A comprehensive backend API for the Aeonisk game system, providing complete game state management, real-time updates, and secure player interactions.

## Architecture

### Technology Stack
- **Runtime**: Node.js with TypeScript
- **Framework**: Express.js
- **Database**: PostgreSQL with Drizzle ORM
- **Real-time**: Socket.IO
- **Authentication**: JWT
- **Testing**: Jest with Supertest
- **Containerization**: Podman

### Project Structure
```
aeonisk-backend/
├── src/
│   ├── domain/           # Domain entities and business logic
│   │   ├── entities/     # Character, GameSession entities
│   │   └── schemas/      # Zod validation schemas
│   ├── infrastructure/   # Database and external services
│   │   ├── database/     # Drizzle schema and connection
│   │   └── repositories/ # Data access layer
│   ├── services/         # Business logic services
│   ├── api/              # HTTP layer
│   │   ├── routes/       # Express routes
│   │   ├── controllers/  # Request handlers
│   │   └── middleware/   # Auth, error handling
│   └── utils/            # Shared utilities
├── tests/
│   ├── unit/            # Unit tests
│   ├── integration/     # API integration tests
│   └── e2e/             # End-to-end tests
└── drizzle/             # Database migrations
```

## Features

### Game State Management
- Complete character creation and management
- Game session tracking with phases
- Action recording and history
- NPC management
- Void and Soulcredit economy

### Real-time Updates
- WebSocket support for live game updates
- Session-based rooms for multiplayer
- Character state synchronization
- AI NPC updates

### Security
- JWT authentication
- Rate limiting
- Input validation with Zod
- SQL injection protection via Drizzle ORM
- CORS configuration

### AI Integration
- AI DM capabilities
- NPC agent support
- ChromaDB integration for RAG
- Game lore and rules retrieval

## API Endpoints

### Authentication
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout

### Characters
- `GET /api/characters` - List user's characters
- `POST /api/characters` - Create new character
- `GET /api/characters/:id` - Get character details
- `PUT /api/characters/:id` - Update character
- `DELETE /api/characters/:id` - Delete character
- `POST /api/characters/:id/void` - Modify void score
- `POST /api/characters/:id/soulcredit` - Modify soulcredit
- `POST /api/characters/:id/seeds/add` - Add raw seed
- `POST /api/characters/:id/seeds/attune` - Attune seed

### Game Sessions
- `GET /api/sessions` - List user's sessions
- `POST /api/sessions` - Create new session
- `GET /api/sessions/:id` - Get session details
- `PUT /api/sessions/:id` - Update session
- `POST /api/sessions/:id/characters` - Add character to session
- `POST /api/sessions/:id/actions` - Record action
- `POST /api/sessions/:id/npcs` - Add NPC

## Setup

### Prerequisites
- Node.js 18+
- PostgreSQL 14+
- Podman (or Docker)

### Installation
```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.example .env

# Start infrastructure with Podman
task podman:up

# Run database migrations
npm run db:migrate

# Start development server
task dev
```

### Testing
```bash
# Run all tests
task test

# Run tests in watch mode
task test:watch

# Run with coverage
task test:coverage
```

## Environment Variables
```
# Server
PORT=3000
NODE_ENV=development

# Database
DATABASE_URL=postgresql://aeonisk:aeonisk_password@localhost:5432/aeonisk_game

# ChromaDB
CHROMADB_URL=http://localhost:8000

# JWT
JWT_SECRET=your-secret-key-here
JWT_EXPIRE=7d

# Rate Limiting
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX_REQUESTS=100

# CORS
CORS_ORIGIN=http://localhost:5173

# Logging
LOG_LEVEL=info
```

## Database Schema

### Core Tables
- `users` - User accounts
- `characters` - Player characters
- `game_sessions` - Game sessions
- `session_characters` - M2M relationship
- `npcs` - Non-player characters
- `actions` - Game actions/events
- `void_history` - Void score changes

## WebSocket Events

### Client → Server
- `authenticate` - Authenticate socket connection
- `join-session` - Join game session room
- `leave-session` - Leave game session room

### Server → Client
- `character-update` - Character state change
- `session-update` - Session state change
- `action-recorded` - New action in session
- `npc-action` - AI NPC performed action

## Development Workflow

1. **Test-Driven Development**: Write tests first
2. **Type Safety**: Full TypeScript coverage
3. **Domain-Driven Design**: Clear separation of concerns
4. **Repository Pattern**: Abstract data access
5. **Service Layer**: Business logic isolation

## Next Steps

- [ ] Implement full authentication system
- [ ] Add game session WebSocket handlers
- [ ] Integrate AI DM capabilities
- [ ] Add ritual system endpoints
- [ ] Implement campaign management
- [ ] Add file upload for character portraits
- [ ] Implement data export/import
- [ ] Add metrics and monitoring
