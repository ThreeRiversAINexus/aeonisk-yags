import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import { CharacterController } from '../controllers/character.controller';
import { CharacterService } from '../../services/CharacterService';
import { CharacterRepository } from '../../infrastructure/repositories/CharacterRepository';
import { db } from '../../infrastructure/database';

const characterRepository = new CharacterRepository(db);
const characterService = new CharacterService(characterRepository);
const characterController = new CharacterController(characterService);

export const characterRouter = Router();

// All routes require authentication
characterRouter.use(authenticate);

// Character CRUD operations
characterRouter.post('/', characterController.create);
characterRouter.get('/', characterController.list);
characterRouter.get('/:id', characterController.get);
characterRouter.put('/:id', characterController.update);
characterRouter.delete('/:id', characterController.delete);

// Special character operations
characterRouter.post('/:id/void', characterController.modifyVoidScore);
characterRouter.post('/:id/soulcredit', characterController.modifySoulcredit);
characterRouter.post('/:id/seeds/add', characterController.addRawSeed);
characterRouter.post('/:id/seeds/attune', characterController.attuneSeed);