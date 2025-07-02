format_prompt = """
```
[
    {
        "action": "<action_name>",
        "units": [<unit_id>, <unit_id>, ...], # units you want to command
        "target_unit" (optional): <unit_id>, # some existing unit
        "target_position" (optional): [x, y]
    },
    // more actions ...
]
```

Example:
```
[
    {
        "action": "ATTACK_ATTACK",
        "units": [1, 2, 3],
        "target_unit": 9
    },
    {
        "action": "MOVE_MOVE",
        "units": [4, 5],
        "target_position": [50, 60]
    },
    {
        "action": "COMMANDCENTERTRAIN_SCV",
        "units": [6]
    }
]
```
""".strip()


def construct_text(info: dict):
    return "\n\n".join([f"###{key}###\n{value}" for key, value in info.items()])

TERRANN_TECH_TREE = f"""
Core & Economy
    Command Center: unlocks SCV, Orbital Command, Planetary Fortress, and Engineering Bay
    Orbital Command: an upgrade to the Command Center that produces SCVs and can call down MULEs for increased mining
    Planetary Fortress: a defensive upgrade for the Command Center with a powerful ground attack
    Supply Depot: increases supply cap and unlocks the Barracks
    Refinery: allows SCVs to harvest Vespene Gas

Infantry & Defenses
    Barracks: produces infantry units (Marine, Reaper, Marauder, Ghost) and unlocks the Bunker, Factory and Ghost Academy
    Engineering Bay: researches infantry and building upgrades; unlocks the Missile Turret, Sensor Tower and Planetary Fortress
    Bunker: a defensive structure that infantry units can garrison inside for protection
    Missile Turret: a static defense structure that attacks air units
    Sensor Tower: a utility structure that detects enemy units on the minimap in a large radius
    Ghost Academy: unlocks the Ghost unit and researches its upgrades, including Personal Cloaking and the ability to arm nukes

Mechanical & Air
    Factory: produces mechanical ground units (Hellion, Widow Mine, Siege Tank, Hellbat, Thor) and unlocks the Starport and Armory
    Armory: research weapon/armor upgrades; unlocks the Hellbat, Thor and higher-level infantry upgrades
    Starport: produce air units (Viking, Medivac, Banshee, Raven, Battlecruiser)
    Fusion Core: unlock Battlecruiser

Add-ons
    Tech Lab of Barracks: unlock Marauder and Ghost
    Tech Lab of Factory: unlock Siege Tank, Hellbat and Thor
    Tech Lab of Starport: unlock Banshee, Raven and Battlecruiser
    Reactor: allow structures to produce two units simultaneously
""".strip()