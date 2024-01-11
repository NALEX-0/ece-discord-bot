'''
Author: Stavros Avramidis
'''

import asyncio
import logging
import os
import pickle
import re
import requests

from datetime import datetime, timedelta, date
from random import choice
import unicodedata as ud

import discord

from bs4 import BeautifulSoup, formatter
from discord.ext import commands, tasks


TOKEN = os.environ["TOKEN"]
DISCORD_CHANNEL_ID = int(1194940888284135434)
DISCROD_SAVE_CHANNEL_ID = int(1194940663784034444)

URL = "https://www.ece.ntua.gr/gr/archive"
URL_PREFIX = "https://www.ece.ntua.gr"

CATEGORIES = {
    "Προπτυχιακά": 0x5887ba,
    "Προγράμματα": 0xef775e,
    "Εγγραφές": 0x96aa44,
    "ΣΗΜΜΥ": 0xFFFFFF,
}

SHMMY_KEYWORDS = (
    "ΤΣΑΝΑΚΑΣ",
    "ΚΟΖΥΡΗΣ",
    "ΚΟΣΜΗΤΩΡΑΣ",
    "ΕΞΕΤΑΣ.*",
    "ΑΠΕΡΓΙΑ.*",
    "ΕΞΑΜΗΝΟΥ?",
    "ΑΝΑΒΟΛΗΣ?",
    "ΕΚΤΑΚΤΗ",
    "ΜΜΜ",
    "ΔΕΝ?",
)

SHMMY_KEYWORDS_PATTERN = r'\b(?:' + '|'.join(SHMMY_KEYWORDS) + r')\b'

REMOVE_ACCENTS_FILTER = {ord('\N{COMBINING ACUTE ACCENT}'): None}


def greek_to_upper(s: str):
    return ud.normalize('NFD', s).upper().translate(REMOVE_ACCENTS_FILTER)


def has_shmmy_keywords(s: str):
    s = greek_to_upper(s)
    match = re.search(SHMMY_KEYWORDS_PATTERN, s, flags=re.IGNORECASE)

    return match is not None



announcements = ()

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@tasks.loop(seconds=120)
async def check_for_announcements():
    logging.info(f"Scrapping {URL}")

    dirtybit = False

    r = requests.get(url=URL)
    if r.status_code != 200:
        logging.error(f"Unable to scrap ece.ntua.gr Got: {r.status_code}")
        return

    soup = BeautifulSoup(r.content, "lxml")
    table = soup.find(id="archiveTable")

    today = datetime.now()

    for row in table.findAll("tr"):
        announcement = {}
        row_cols = row.findAll("td")

        if row_cols[2].text != "Ανακοινώσεις":
            continue

        date = datetime.strptime(row_cols[0].text, "%d/%m/%Y")
        if today - date > timedelta(days=10):
            break

        id = int(row_cols[0].find("a", href=True)["href"].replace(
            "/gr/announcement/", ""))
        cat = row_cols[3].text

        global announcements
        if id in announcements or cat not in CATEGORIES:
            continue

        announcement["Date"] = date.strftime("%d/%m/%Y")
        announcement["Title"] = row_cols[1].text
        announcement["Cat"] = cat
        announcement["ID"] = id
        announcement["URL"] = URL_PREFIX + row_cols[0].find("a",
                                                            href=True)["href"]

        if cat == "ΣΗΜΜΥ" and not has_shmmy_keywords(announcement["Title"]):
            continue

        #
        # Get Announcment Description
        #
        r2 = requests.get(url=announcement["URL"])
        if r2.status_code != 200:
            logging.error(
                f"Unable to scrap announcement's page Got: {r2.status_code}")
            return

        soup2 = BeautifulSoup(r2.content, "lxml")
        desc = soup2.find(id="content").findAll("p")
        desc = "\n".join(p.text for p in desc)

        if len(desc) > 400:
            desc = desc[:397] + "..."

        #
        # Discord message
        #
        discord_channel = client.get_channel(DISCORD_CHANNEL_ID)
        embed = discord.Embed(
            title=announcement["Title"],
            url=announcement["URL"],
            description=f"**{announcement['Cat']}**\n\n{desc}",
            color=CATEGORIES[announcement['Cat']],
        )
        embed.set_author(
            name="Μια ανακοίνωση να κάνουμε!",
            icon_url=
            "https://cdn.discordapp.com/app-assets/1151413211904606290/1151774722124689470.png",
        )
        embed.set_footer(text=str(announcement["Date"]))

        try:
            await discord_channel.send(embed=embed)
            announcements += (id, )
            dirtybit = True

        except Exception as e:
            logging.error(f"Couldn't send message! {e}")

    if dirtybit:
        with open("data.pickle", "wb+") as handle:
            pickle.dump(announcements, handle, protocol=pickle.HIGHEST_PROTOCOL)
        
        channel = client.get_channel(DISCROD_SAVE_CHANNEL_ID)
        await channel.send(file = discord.File("data.pickle"))



@tasks.loop(minutes=60)
async def change_status():
    c = ["Octave", "LTSpice", "Putty", "MPLAB-X", "grader"]

    rand_activity = choice(c)
    await client.change_presence(activity=discord.Game(name=rand_activity))


@client.event
async def on_ready():
    logging.info(f"{client.user} has connected to Discord!")

    channel = client.get_channel(DISCROD_SAVE_CHANNEL_ID)
    message = await channel.fetch_message(channel.last_message_id)
    print(message.attachments)

    if message.attachments:
        await message.attachments[0].save(fp="data.pickle")
        print("Retrieved internal state")
        try:
            with open("data.pickle", "rb+") as handle:
                global announcements
                announcements = pickle.load(handle)
                print(announcements)
    
        except (OSError, IOError) as _:
            logging.info("pickle file not found")

    check_for_announcements.start()
    change_status.start()


if __name__ == "__main__":
    logging.basicConfig(encoding="utf-8", level=logging.INFO)
    client.run(TOKEN)
