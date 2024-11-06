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
Structure Name,Prerequisites,Produces,Allows Production/ Construction Of
Command Center,None,SCV Orbital Command Planetary Fortress,Engineering Bay
Orbital Command,Barracks,SCV,n/a
Planetary Fortress,Engineering Bay,SCV,n/a
Supply Depot,None,n/a,Barracks
Refinery,None,n/a,n/a
Barracks,Supply Depot,Marine Reaper Marauder Ghost,Marine Reaper Bunker Factory Ghost Academy
Engineering Bay,Command Center,"+Infantry Weapons +Infantry Armor Hi-Sec Auto Tracking, Nanosteel Frame, Upgrade Structure Armor",Missile Turret Sensor Tower Planetary Fortress
Missile Turret,Engineering Bay,n/a,n/a
Bunker,Barracks,n/a,n/a
Sensor Tower,Engineering Bay,n/a,n/a
Factory,Barracks,Hellion Widow Mine Siege Tank Hellbat Thor,Hellion Widow Mine Starport Armory
Armory,Factory,+Vehicle Weapons +Ship Weapons +Ship/Vehicle Armor,Hellbat Thor +2/3 level upgrades at Engineering Bay
Starport,Factory,Viking Medivac Banshee Raven Battlecruiser,Viking Medivac
Fusion Core,Starport,Weapon RefitBehemoth Reactor,Battlecruiser
Ghost Academy,Barracks,"Personal Cloaking, Moebius Reactor, Arm Nuclear Silo",Ghost
Tech Lab: Barracks,n/a,"Combat Shields, Stimpack, Concussive Shells",Marauder Ghost (with Ghost Academy)
Tech Lab: Factory,n/a,"Infernal Pre-Igniter, Drilling Claws, Transformation Servos",Siege Tank Hellbat (with Armory) Thor (with Armory)
Tech Lab: Starport,n/a,"Caduceus Reactor, Durable Materials, Corvid Reactor, Cloaking Field",Banshee Raven Battlecruiser (with Fusion Core)
Reactor,n/a,n/a,Produce 2 units at a time
""".strip()