# Sable from session_config_combat_ambush.json
attributes = {
    "Strength": 3,
    "Agility": 4,
    "Endurance": 4,
    "Perception": 4,
    "Intelligence": 3,
    "Empathy": 2,
    "Willpower": 3,
    "Dexterity": 3
}

size = 5  # Default size for humans
agility = attributes.get('Agility', 3)
endurance = attributes.get('Endurance', 3)
SOAK_COMBAT_BALANCE = 4

base_soak = size + agility + endurance - 5
soak = base_soak + SOAK_COMBAT_BALANCE

print(f"Sable's Soak Calculation:")
print(f"Size({size}) + Agility({agility}) + Endurance({endurance}) - 5 + balance({SOAK_COMBAT_BALANCE})")
print(f"{size} + {agility} + {endurance} - 5 + {SOAK_COMBAT_BALANCE} = {soak}")
print(f"\nBase soak (before balance): {base_soak}")
print(f"Final soak (with balance): {soak}")
