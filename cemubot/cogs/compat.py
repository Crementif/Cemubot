from discord.ext import commands
from fuzzywuzzy import process
import discord
import urllib.parse
import re

class Compat(commands.Cog, name="Compatibility Wiki"):
    def __init__(self, bot):
        self.bot = bot
        self.search_dict = dict()
        # create title search set
        for ent in self.bot.title_ids:
            if self.bot.title_ids[ent]["wiki_has_game_id_redirect"] and self.bot.title_ids[ent]["region"] != "JAP":
                simple_name = re.sub(r"[^a-z0-9: ]+", '', self.bot.title_ids[ent]["game_title"].lower()).strip()
                if ':' in simple_name:
                    # make games that have their title prefixed with the game's series searchable
                    self.search_dict[simple_name.split(':')[0].strip()] = self.bot.title_ids[ent]["game_id"]
                    self.search_dict[simple_name.split(':')[1].strip()] = self.bot.title_ids[ent]["game_id"]
                else:
                    self.search_dict[simple_name] = self.bot.title_ids[ent]["game_id"]

    @commands.command(name="compat", help="Search for the game's compatibility wiki page.")
    async def compatibility(self, ctx, *, hint: str):
        simple_hint = re.sub(r"[^a-z0-9 ]+", '', hint.lower())
        guess = process.extractOne(simple_hint, list(self.search_dict.keys()), score_cutoff=60)
        if guess is not None:
            await ctx.send(content=f"The game's compatibility information can be found <https://wiki.cemu.info/wiki/{self.search_dict[guess[0]]}>")
        else:
            await ctx.send(content=f"Couldn't find a good match for the game that you were searching for. Try viewing the compat wiki results <http://wiki.cemu.info/index.php?search={urllib.parse.quote_plus(simple_hint)}>")

def setup(bot):
    bot.add_cog(Compat(bot))