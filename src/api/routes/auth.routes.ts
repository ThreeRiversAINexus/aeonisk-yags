import { Router } from 'express';

export const authRouter = Router();

// Stub auth routes - to be implemented
authRouter.post('/register', (req, res) => {
  res.status(501).json({ error: 'Not implemented yet' });
});

authRouter.post('/login', (req, res) => {
  res.status(501).json({ error: 'Not implemented yet' });
});

authRouter.post('/logout', (req, res) => {
  res.status(501).json({ error: 'Not implemented yet' });
});