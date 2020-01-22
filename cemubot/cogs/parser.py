import datetime
from discord.ext import commands
import discord
import json
import re
import requests
import time

from cogs import config

class Parser():
	def __init__(self):
		self.file = None
		self.channel = None
		self.embed = None

	async def parse_log(self, file, channel, reply_msg, title_ids):
		try:
			self.file = file.decode('utf-8').replace('\r', '')
		except UnicodeDecodeError:
			# brazilian portugese was causing problems
			self.file = file.decode('latin-1').replace('\r', '')
		self.channel = channel
		self.reply_msg = reply_msg
		self.title_ids = title_ids
		self.embed = {
			"emu_info": {
				"cemu_version": "Unknown",
				"cemuhook_version": "Unknown"
			},
			"game_info": {
				"title_id": "Unknown",
				"title_version": "Unknown",
				"wiki_page": "Unknown",
				"compatibility": {
					"rating": "Unknown",
					"version": "N/A"
				},
				"rpx_hash": "Unknown",
				"shadercache_name": "Unknown"
			},
			"specs": {
				"cpu": "Unknown",
				"ram": "Unknown",
				"gpu": "Unknown",
				"gpu_driver": "Unknown"
			},
			"settings": {
				"cpu_mode": "Unknown",
				"cpu_extensions": "Unknown",
				"disabled_cpu_extensions": "",
				"backend": "Unknown",
				"gx2drawdone": "Unknown",
				"console_region": "Auto",
				"thread_quantum": "",
				"custom_timer_mode": "Unknown"
			},
			"relevant_info": []
		}
		if not re.search(r"------- Init Cemu .*? -------", self.file, re.M):
			await self.reply_msg.edit(content="Error: This is not a Cemu log file.")
			return
		elif not re.search(r"------- Loaded title -------", self.file, re.M):
			await self.reply_msg.edit(content="Error: No game detected. Submit a log during or after emulating a game. Reopening Cemu clears the log.")
			return
		
		self.detect_emu_info()
		self.detect_specs()
		try:
			self.detect_settings()
		except AttributeError:
			self.embed["relevant_info"] += ["ℹ Incomplete log; some information was not found"]
		self.get_relevant_info()
		
		await self.reply_msg.edit(content=None, embed=self.create_embed())

	def detect_emu_info(self):
		self.embed["emu_info"]["cemu_version"] = re.search(r"------- Init Cemu (.*?) -------", self.file, re.M).group(1)
		try:
			self.embed["emu_info"]["cemuhook_version"] = re.search(r"Cemuhook version: (.*?)$", self.file, re.M).group(1)
		except AttributeError:
			self.embed["emu_info"]["cemuhook_version"] = "N/A"
		self.embed["game_info"]["title_id"] = re.search(r"TitleId: (.*?)$", self.file, re.M).group(1).upper()
		self.embed["game_info"]["title_version"] = re.search(r"TitleVersion: v([0-9]+)", self.file, re.M).group(1)

		self.embed["game_info"]["wiki_page"] = ""
		if self.title_ids[self.embed["game_info"]["title_id"]]["wiki_has_game_id_redirect"]:
			self.embed["game_info"]["wiki_page"] = f"http://wiki.cemu.info/wiki/{self.title_ids[self.embed['game_info']['title_id']]['game_id']}"
		else:
			# todo: use a cache of the cemu wiki instead of making a request on each parse
			title = self.title_ids[self.embed['game_info']['title_id']]['game_title']
			title = re.sub(r'[^\x00-\x7f]', r'', title)
			title = title.replace(' ', '_')
			self.embed["game_info"]["wiki_page"] = f"http://wiki.cemu.info/wiki/{title}"
		# experimental, probably buggy
		if self.embed["game_info"]["wiki_page"]:
			compat = requests.get(self.embed["game_info"]["wiki_page"])
			if compat.status_code == 200:
				try:
					# pArSiNg hTmL wItH rEgEx iS a bAd iDeA
					compat = re.findall(r"<tr style=\"vertical-align:middle;\">.*?</tr>", compat.text, re.M|re.S)[-1]
					self.embed["game_info"]["compatibility"] = {
						"rating": re.search(r"<a href=\"/wiki/Category:.*?_\(Rating\)\" title=\"Category:.*? \(Rating\)\">(.*?)</a>", compat).group(1),
						"version": re.search(r"<a href=\"(?:/wiki/|/index\.php\?title=)Release.*? title=\".*?\">(.*?)</a>", compat).group(1)
					}
				except (IndexError, AttributeError):
					pass
			else:
				self.embed["game_info"]["wiki_page"] = ""
		
		self.embed["game_info"]["rpx_hash"] = re.search(r"RPX hash: (.*?)$", self.file, re.M).group(1)
		self.embed["game_info"]["shadercache_name"] = re.search(r"shaderCache name: (.*?)$", self.file, re.M).group(1)

	def detect_specs(self):
		self.embed["specs"]["cpu"] = re.search(r"(?<!CPU[0-9] )CPU: (.*?) *$", self.file, re.M).group(1)
		self.embed["specs"]["ram"] = re.search(r"RAM: ([0-9]+)MB", self.file, re.M).group(1)
		self.embed["specs"]["gpu"] = re.search(r"(?:GL_RENDERER: |Using GPU: )(.*?)$", self.file, re.M).group(1)
		try:
			self.embed["specs"]["gpu_driver"] = re.search(r"GL_VERSION: (.*?)$", self.file, re.M).group(1)
		except AttributeError:
			self.embed["specs"]["gpu_driver"] = "Unknown"
	
	def detect_settings(self):
		self.embed["settings"]["cpu_mode"] = re.search(r"CPU-Mode: (.*?)$", self.file, re.M).group(1)
		self.embed["settings"]["cpu_extensions"] = re.search(r"Recompiler initialized. CPU extensions: (.*?)$", self.file, re.M).group(1)
		enabled_cpu_extensions = ' '.join(re.findall(r"CPU extensions that will actually be used by recompiler: (.*?)$", self.file, re.M))
		if enabled_cpu_extensions:
			self.embed["settings"]["disabled_cpu_extensions"] = {x for x in re.findall(r"(\b\w*\b)", self.embed["settings"]["cpu_extensions"], re.M)} \
															- {x for x in re.findall(r"(\b\w*\b)", enabled_cpu_extensions, re.M) if x}
			self.embed["settings"]["disabled_cpu_extensions"] = ', '.join([x for x in self.embed['settings']['disabled_cpu_extensions'] if x])
		self.embed["settings"]["backend"] = ("OpenGL" if "OpenGL" in self.file else "Vulkan")
		self.embed["settings"]["gx2drawdone"] = ("Enabled" if "Full sync at GX2DrawDone: true" in self.file else "Disabled")
		self.embed["settings"]["console_region"] = re.search(r"Console region: (.*?)$", self.file, re.M).group(1)
		self.embed["settings"]["thread_quantum"] = (None if "Thread quantum set to " not in self.file else re.search(r'Thread quantum set to (.*?)$', self.file, re.M).group(1))
		try:
			self.embed["settings"]["custom_timer_mode"] = re.search(r"Custom timer mode: (.*?)$", self.file, re.M).group(1)
		except AttributeError:
			self.embed["settings"]["custom_timer_mode"] = "none"
		if self.embed["settings"]["custom_timer_mode"] == "none":
			self.embed["settings"]["custom_timer_mode"] = "Default"
	
	def get_relevant_info(self):
		self.embed["relevant_info"].extend(RulesetParser(self.file, self.embed, "misc/rulesets.json").parse())
		self.embed["relevant_info"] += [f"ℹ RPX hash: `{self.embed['game_info']['rpx_hash']}` ║ Shader cache name: `{self.embed['game_info']['shadercache_name']}`"]
		
	def create_embed(self):
		game_title = self.title_ids[self.embed["game_info"]["title_id"]]["game_title"]
		if self.embed["game_info"]["compatibility"]["rating"] != "Unknown":
			description = f"Tested as **{self.embed['game_info']['compatibility']['rating']}** on {self.embed['game_info']['compatibility']['version']}"
		else:
			description = "Unknown compatibility rating"
		# i saw a couple of tests where the rating wasn't one of the standard five,
		# so i'm putting this in a try-except block just in case
		try:
			colour = config.cfg["compatibility_colors"][self.embed["game_info"]["compatibility"]["rating"].lower()]
		except KeyError:
			colour = config.cfg["compatibility_colors"]["unknown"]
			
		embed = discord.Embed(colour=discord.Colour(colour), 
							  title=self.embed["game_info"]["title_id"]+(" ("+game_title+")" if game_title else " (Unknown title)"),
							  url=(self.embed["game_info"]["wiki_page"] or None),
							  description=description,
							  timestamp=datetime.datetime.utcfromtimestamp(time.time()))
		game_emu_info = f"""
Cemu {self.embed['emu_info']['cemu_version']}
Cemuhook {self.embed['emu_info']['cemuhook_version']}
**Title version:** v{self.embed['game_info']['title_version']}
"""
		specs = f"""
**CPU:** {self.embed['specs']['cpu']}
**RAM:** {self.embed['specs']['ram']}MB
**GPU:** {self.embed['specs']['gpu']}
**GPU driver:** {self.embed['specs']['gpu_driver']}
"""
		settings = f"""
**CPU mode:** {self.embed['settings']['cpu_mode']}
**Graphics backend:** {self.embed['settings']['backend']}
**Full sync at GX2DrawDone:** {self.embed['settings']['gx2drawdone']}
**Custom timer mode:** {self.embed["settings"]["custom_timer_mode"]}
"""
		if not self.embed["relevant_info"]:
			self.embed["relevant_info"] = ["N/A"]
		embed.add_field(name="Game/Emulator Info", value=game_emu_info, inline=True)
		embed.add_field(name="Specs", value=specs, inline=True)
		embed.add_field(name="Settings", value=settings, inline=False)
		embed.add_field(name="Relevant Info", value='\n'.join(self.embed["relevant_info"]), inline=False)
		return embed


class RulesetParser():
	def __init__(self, log_file, properties, ruleset_file_dir):
		self.log_file = log_file
		self.properties = properties
		with open(ruleset_file_dir, 'r', encoding='utf-8') as f:
			self.ruleset_file = json.load(f)

	def parse(self):
		relevant_info = []
		relevant_info.extend(self.parse_ruleset(self.ruleset_file["any"]))
		try:
			ruleset = self.ruleset_file[self.properties["game_info"]["title_id"]]
			# to avoid duplicate rulesets, 
			# one title ID (usually USA) holds the game's ruleset,
			# and the other regions simply redirect to it
			if type(ruleset) == str:
				ruleset = self.ruleset_file[ruleset]
			relevant_info.extend(self.parse_ruleset(ruleset))
		except KeyError:
			pass
		return relevant_info
	
	def parse_ruleset(self, ruleset):
		messages = []
		for rule in ruleset:
			match_type = rule.pop(0)
			message = rule.pop(-1)
			test_results = []
			for test in rule:
				if test["property"] == "log":
					prop = self.log_file
				else:
					prop = self.get_property(test["property"])
				rule_type = test["type"]
				value = test["value"]
				if \
				(rule_type == "str_eq" and prop == value) or \
				(rule_type == "str_ne" and prop != value) or \
				(rule_type == "str_contains" and value in prop) or \
				(rule_type == "str_not_contains" and value not in prop) or \
				(rule_type == "int_lt" and int(prop) < value) or \
				(rule_type == "int_eq" and int(prop) == value) or \
				(rule_type == "int_gt" and int(prop) > value) or \
				(rule_type == "rgx_matches" and re.search(value, prop, re.M)):
					test_results.append(True)
				else:
					test_results.append(False)
			if (any(test_results) if match_type == "any" else all(test_results)):
				messages.append(message.format(**self.properties))
		return messages
		
	def get_property(self, key):
		d = self.properties
		key = key.split('.')
		while key:
			d = d[key[0]]
			if type(d) == dict:
				key.pop(0)
				continue
			else:
				return d
