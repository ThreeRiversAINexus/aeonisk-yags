import { Request, Response, NextFunction } from 'express';
import { CharacterService } from '../../services/CharacterService';

interface AuthRequest extends Request {
  userId?: string;
}

export class CharacterController {
  constructor(private service: CharacterService) {
    // Bind methods to ensure correct 'this' context
    this.create = this.create.bind(this);
    this.list = this.list.bind(this);
    this.get = this.get.bind(this);
    this.update = this.update.bind(this);
    this.delete = this.delete.bind(this);
    this.modifyVoidScore = this.modifyVoidScore.bind(this);
    this.modifySoulcredit = this.modifySoulcredit.bind(this);
    this.addRawSeed = this.addRawSeed.bind(this);
    this.attuneSeed = this.attuneSeed.bind(this);
  }

  async create(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const character = await this.service.createCharacter(
        req.userId!,
        req.body
      );
      res.status(201).json(character.toJSON());
    } catch (error) {
      next(error);
    }
  }

  async list(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const characters = await this.service.getCharactersByUser(req.userId!);
      res.json(characters.map(c => c.toJSON()));
    } catch (error) {
      next(error);
    }
  }

  async get(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const character = await this.service.getCharacterById(
        req.params['id']!,
        req.userId!
      );
      res.json(character.toJSON());
    } catch (error) {
      next(error);
    }
  }

  async update(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const character = await this.service.updateCharacter(
        req.params['id']!,
        req.userId!,
        req.body
      );
      res.json(character.toJSON());
    } catch (error) {
      next(error);
    }
  }

  async delete(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      await this.service.deleteCharacter(req.params['id']!, req.userId!);
      res.status(204).send();
    } catch (error) {
      next(error);
    }
  }

  async modifyVoidScore(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const { change, reason } = req.body;
      const character = await this.service.modifyVoidScore(
        req.params['id']!,
        req.userId!,
        change,
        reason
      );
      res.json(character.toJSON());
    } catch (error) {
      next(error);
    }
  }

  async modifySoulcredit(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const { change } = req.body;
      const character = await this.service.modifySoulcredit(
        req.params['id']!,
        req.userId!,
        change
      );
      res.json(character.toJSON());
    } catch (error) {
      next(error);
    }
  }

  async addRawSeed(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const { seedId, source } = req.body;
      const character = await this.service.addRawSeed(
        req.params['id']!,
        req.userId!,
        seedId,
        source
      );
      res.json(character.toJSON());
    } catch (error) {
      next(error);
    }
  }

  async attuneSeed(req: AuthRequest, res: Response, next: NextFunction) {
    try {
      const { seedId, element } = req.body;
      const { character, result } = await this.service.attuneSeed(
        req.params['id']!,
        req.userId!,
        seedId,
        element
      );
      res.json({
        character: character.toJSON(),
        result
      });
    } catch (error) {
      next(error);
    }
  }
}