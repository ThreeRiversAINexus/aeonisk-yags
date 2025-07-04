import { app } from './app';
import { createServer } from 'http';
import { Server } from 'socket.io';
import { logger } from './utils/logger';

const PORT = process.env['PORT'] || 3000;

// Create HTTP server
const httpServer = createServer(app);

// Initialize Socket.IO
const io = new Server(httpServer, {
  cors: {
    origin: process.env['CORS_ORIGIN'] || 'http://localhost:5173',
    credentials: true
  }
});

// Socket.IO connection handling
io.on('connection', (socket) => {
  logger.info(`Client connected: ${socket.id}`);

  // Join user to their personal room for targeted updates
  socket.on('authenticate', (userId: string) => {
    socket.join(`user:${userId}`);
    logger.info(`User ${userId} joined their room`);
  });

  // Join game session room
  socket.on('join-session', (sessionId: string) => {
    socket.join(`session:${sessionId}`);
    logger.info(`Socket ${socket.id} joined session ${sessionId}`);
  });

  // Leave game session room
  socket.on('leave-session', (sessionId: string) => {
    socket.leave(`session:${sessionId}`);
    logger.info(`Socket ${socket.id} left session ${sessionId}`);
  });

  socket.on('disconnect', () => {
    logger.info(`Client disconnected: ${socket.id}`);
  });
});

// Export io for use in other modules
export { io };

// Start server
httpServer.listen(PORT, () => {
  logger.info(`Server running on port ${PORT}`);
  logger.info(`Environment: ${process.env['NODE_ENV']}`);
});