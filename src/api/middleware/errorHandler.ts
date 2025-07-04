import { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';
import { logger } from '../../utils/logger';

export class ApiError extends Error {
  public statusCode: number;
  public isOperational: boolean;

  constructor(
    statusCode: number,
    message: string,
    isOperational = true
  ) {
    super(message);
    this.statusCode = statusCode;
    this.isOperational = isOperational;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export const errorHandler = (
  err: Error,
  req: Request,
  res: Response,
  next: NextFunction
) => {
  logger.error({
    error: err.message,
    stack: err.stack,
    path: req.path,
    method: req.method
  });

  if (err instanceof ApiError) {
    return res.status(err.statusCode).json({
      error: err.message,
      status: err.statusCode
    });
  }

  if (err instanceof ZodError) {
    return res.status(400).json({
      error: 'Validation error',
      details: err.errors,
      status: 400
    });
  }

  // Default error response
  res.status(500).json({
    error: 'Internal server error',
    status: 500
  });
};