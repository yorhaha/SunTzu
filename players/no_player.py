from sc2.bot_ai import BotAI
from sc2.constants import UnitTypeId
import time

class NoPlayer(BotAI):
    def __init__(self):
        super().__init__()

    async def run(self, iteration: int):
        if iteration == 10:
            import pdb; pdb.set_trace()
        if iteration == 50:
            import pdb; pdb.set_trace()
