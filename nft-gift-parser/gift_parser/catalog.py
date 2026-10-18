"""Известные коллекции NFT-подарков (slug из ссылки t.me/nft/<slug>-<номер>).

Список идёт от новых к старым. Telegram регулярно выпускает новые коллекции —
чтобы добавить свежую, впишите её в начало COLLECTIONS. Проверить, что slug
существует, можно командой `python -m gift_parser --check <Slug>`.
"""

# (slug, название)
COLLECTIONS: list[tuple[str, str]] = [
    # 2025: коллаборации и летние выпуски
    ("UFCStrike", "UFC Strike"),
    ("KhabibsPapakha", "Khabib's Papakha"),
    ("SnoopDogg", "Snoop Dogg"),
    ("SwagBag", "Swag Bag"),
    ("SnoopCigar", "Snoop Cigar"),
    ("LowRider", "Low Rider"),
    ("WestsideSign", "Westside Sign"),
    ("JollyChimp", "Jolly Chimp"),
    ("MoonPendant", "Moon Pendant"),
    ("IonicDryer", "Ionic Dryer"),
    ("InputKey", "Input Key"),
    ("MightyArm", "Mighty Arm"),
    ("ArtisanBrick", "Artisan Brick"),
    ("CloverPin", "Clover Pin"),
    ("SkyStilettos", "Sky Stilettos"),
    ("FreshSocks", "Fresh Socks"),
    ("HappyBrownie", "Happy Brownie"),
    ("IceCream", "Ice Cream"),
    ("SpringBasket", "Spring Basket"),
    ("InstantRamen", "Instant Ramen"),
    ("FaithAmulet", "Faith Amulet"),
    ("MousseCake", "Mousse Cake"),
    ("BowTie", "Bow Tie"),
    ("LushBouquet", "Lush Bouquet"),
    ("HeroicHelmet", "Heroic Helmet"),
    ("NailBracelet", "Nail Bracelet"),
    ("LightSword", "Light Sword"),
    ("GemSignet", "Gem Signet"),
    ("RestlessJar", "Restless Jar"),
    ("PrettyPosy", "Pretty Posy"),
    ("SpyAgaric", "Spy Agaric"),
    ("EasterEgg", "Easter Egg"),
    # 2025: зима и весна
    ("ValentineBox", "Valentine Box"),
    ("JoyfulBundle", "Joyful Bundle"),
    ("CupidCharm", "Cupid Charm"),
    ("PetSnake", "Pet Snake"),
    ("SnakeBox", "Snake Box"),
    ("BigYear", "Big Year"),
    ("DurovsCap", "Durov's Cap"),
    ("BunnyMuffin", "Bunny Muffin"),
    # 2024: новогодние
    ("SantaHat", "Santa Hat"),
    ("SnowGlobe", "Snow Globe"),
    ("SnowMittens", "Snow Mittens"),
    ("XmasStocking", "Xmas Stocking"),
    ("HolidayDrink", "Holiday Drink"),
    ("JingleBells", "Jingle Bells"),
    ("CandyCane", "Candy Cane"),
    ("SleighBell", "Sleigh Bell"),
    ("WinterWreath", "Winter Wreath"),
    ("GingerCookie", "Ginger Cookie"),
    ("StarNotepad", "Star Notepad"),
    ("TamaGadget", "Tama Gadget"),
    ("LolPop", "Lol Pop"),
    ("HypnoLollipop", "Hypno Lollipop"),
    ("SpicedWine", "Spiced Wine"),
    ("PartySparkler", "Party Sparkler"),
    ("HomemadeCake", "Homemade Cake"),
    ("CookieHeart", "Cookie Heart"),
    ("JesterHat", "Jester Hat"),
    ("DeskCalendar", "Desk Calendar"),
    ("BDayCandle", "B-Day Candle"),
    ("JackInTheBox", "Jack-in-the-Box"),
    ("BerryBox", "Berry Box"),
    ("HangingStar", "Hanging Star"),
    # 2024: хэллоуин
    ("MadPumpkin", "Mad Pumpkin"),
    ("WitchHat", "Witch Hat"),
    ("ScaredCat", "Scared Cat"),
    ("EvilEye", "Evil Eye"),
    ("HexPot", "Hex Pot"),
    ("FlyingBroom", "Flying Broom"),
    ("ElectricSkull", "Electric Skull"),
    ("SkullFlower", "Skull Flower"),
    ("VoodooDoll", "Voodoo Doll"),
    ("CrystalBall", "Crystal Ball"),
    ("TrappedHeart", "Trapped Heart"),
    # Первые коллекции
    ("PlushPepe", "Plush Pepe"),
    ("PreciousPeach", "Precious Peach"),
    ("HeartLocket", "Heart Locket"),
    ("SignetRing", "Signet Ring"),
    ("DiamondRing", "Diamond Ring"),
    ("EternalRose", "Eternal Rose"),
    ("EternalCandle", "Eternal Candle"),
    ("LootBag", "Loot Bag"),
    ("IonGem", "Ion Gem"),
    ("PerfumeBottle", "Perfume Bottle"),
    ("SwissWatch", "Swiss Watch"),
    ("MagicPotion", "Magic Potion"),
    ("KissedFrog", "Kissed Frog"),
    ("GenieLamp", "Genie Lamp"),
    ("RecordPlayer", "Record Player"),
    ("LovePotion", "Love Potion"),
    ("LoveCandle", "Love Candle"),
    ("TopHat", "Top Hat"),
    ("ToyBear", "Toy Bear"),
    ("SharpTongue", "Sharp Tongue"),
    ("MiniOscar", "Mini Oscar"),
    ("AstralShard", "Astral Shard"),
    ("NekoHelmet", "Neko Helmet"),
    ("VintageCigar", "Vintage Cigar"),
    ("SakuraFlower", "Sakura Flower"),
    ("LunarSnake", "Lunar Snake"),
]


def latest(n: int = 10) -> list[tuple[str, str]]:
    """Самые новые `n` коллекций."""
    return COLLECTIONS[:n]


def find(query: str) -> list[tuple[str, str]]:
    """Поиск по slug или названию (без учёта регистра и пробелов)."""
    q = "".join(query.lower().split())
    return [(s, name) for s, name in COLLECTIONS
            if q in s.lower() or q in "".join(name.lower().split())]
