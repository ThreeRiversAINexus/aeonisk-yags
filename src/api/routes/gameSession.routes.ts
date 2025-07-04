import { Router } from 'express';

export const gameSessionRouter = Router();

// Stub game session routes - to be implemented
gameSessionRouter.get('/', (req, res) => {
  res.status(501).json({ error: 'Not implemented yet' });
});

gameSessionRouter.post('/', (req, res) => {
  res.status(501).json({ error: 'Not implemented yet' });
});