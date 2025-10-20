# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aeonisk YAGS is a comprehensive gaming ecosystem built around a science-fantasy tabletop RPG. The repository contains multiple interconnected applications:

1. **aeonisk-assistant**: React/TypeScript frontend for AI-assisted game management
2. **aeonisk-backend**: Node.js/Express backend API with PostgreSQL 
3. **aeonisk-rag-backend**: RAG service for game content retrieval using ChromaDB
4. **Content**: Game rules, lore, and modules in Markdown format
5. **Datasets**: Training data and character examples for AI systems
6. **Scripts**: Python utilities for game engine, benchmarking, and content processing

## Common Development Commands

### Primary Development Stack
Use the Taskfile for all common operations:

```bash
# Start entire infrastructure stack  
task stack

# Start only infrastructure services
task infra  

# Development server for backend
task dev

# Run tests
task test
task test:watch
task test:coverage

# Build and quality checks
task build
task lint 
task typecheck
```

### Frontend Development (aeonisk-assistant)
```bash
cd aeonisk-assistant
npm run dev          # Vite development server
npm run build        # Production build
npm run test         # Vitest tests
npm run lint         # ESLint
```

### Database Operations
```bash
task db:init         # Initialize databases
task db:psql         # PostgreSQL shell
npm run db:migrate   # Run Drizzle migrations
npm run db:studio    # Drizzle Studio
```

### Service Management
```bash
task start          # Start all services (Postgres, Redis, ChromaDB)
task stop           # Stop all services
task status         # Show service status
task logs           # View service logs
```

## Architecture

### Backend Architecture (Domain-Driven Design)
```
src/
├── domain/         # Core business entities and schemas
│   ├── entities/   # Character, GameSession classes
│   └── schemas/    # Zod validation schemas
├── infrastructure/ # Database and external services
│   ├── database/   # Drizzle ORM schema
│   └── repositories/ # Data access layer
├── services/       # Business logic services
├── api/           # HTTP layer
│   ├── routes/    # Express routes
│   ├── controllers/ # Request handlers
│   └── middleware/ # Auth, validation, error handling
└── utils/         # Shared utilities
```

### Frontend Architecture (React + Zustand)
```
src/
├── components/    # React components
├── lib/          # Core libraries
│   ├── chat/     # Chat service layer
│   ├── game/     # Game logic (character creation, AI DM)
│   ├── rag/      # ChromaDB integration
│   └── llm/      # LLM provider adapters
├── stores/       # Zustand state management
└── types/        # TypeScript type definitions
```

### Key Technologies
- **Backend**: Node.js, Express, TypeScript, Drizzle ORM, PostgreSQL
- **Frontend**: React, Vite, TypeScript, Tailwind CSS, Zustand
- **AI/ML**: OpenAI API, ChromaDB, Transformers.js
- **Infrastructure**: Podman/Docker, Redis
- **Testing**: Jest, Vitest, Supertest

## Game System Context

Aeonisk is built on the YAGS (Yet Another Game System) foundation with these key concepts:

- **Character System**: Attributes + Skills + d20 mechanics
- **Void Score**: Spiritual corruption tracking (0-10 scale)  
- **Soulcredit**: Spiritual economy currency
- **Bonds**: Formal character relationships as mechanical elements
- **Ritual System**: Willpower × Astral Arts vs thresholds with consequences
- **AI Players**: Automated characters with personality and decision-making

### Core Game Entities
- `Character`: Player/NPC with attributes, skills, void score, bonds
- `GameSession`: Multi-player game state with phases and action tracking  
- `Ritual`: Magical actions with costs, risks, and mechanical effects
- `Bond`: Formal relationships between characters with mechanical benefits

## Development Guidelines

### Character Creation Flow
The system uses a priority-based character creation:
1. Campaign Level determines overall power
2. Priority allocation (Primary/Secondary/Tertiary) for Attributes/Experience/Advantages
3. Point spending within allocated pools
4. Derived stats calculation (Health = Size × 2, etc.)

### AI Integration Points
- **AI DM**: Game master automation using content RAG
- **Character AI**: NPC behavior with personality-driven decision making
- **Content Generation**: Campaign and scenario creation
- **RAG System**: ChromaDB for rules/lore retrieval

### Testing Approach
- Unit tests for business logic in `lib/` and `domain/`
- Integration tests for API endpoints
- Component tests for React UI
- Use `@testing-library` for React components
- Jest for backend, Vitest for frontend

### Database Schema
Core tables: users, characters, game_sessions, session_characters, npcs, actions, void_history. Uses Drizzle ORM for type-safe database operations.

## Important Notes

- Always run `task typecheck` and `task lint` before committing
- Use `task stack` for full development environment  
- Character void scores have mechanical significance at 5+ levels
- The ritual system requires careful balance between power and consequences
- Canonical game content lives in the `datasets/` tree; optional archives can be placed in `archive/`