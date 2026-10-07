"""The loai prompt rut tu 108 FBX goc (xem anh thu nho 2026-10-02): DANG model x CHU DE.
Moi dang co vi du prompt + luat; moi chu de co danh sach model goc cung chu de (de Claude theo phong cach va
khong lap y). Ten model = ten file goc (bo ban _Fix trung)."""

# ---------------------------------------------------------------- DANG MODEL
# Decor (mesh D) theo bo goc - prompt.BRIEF bat 3-5 nhom decor NOI, 15-40 manh (nguoi dung 2026-10-02)
DECOR_DEFAULT = ("raised dots, stars, hearts, small flowers, buttons, studs along rims, small shapes scattered on "
                 "the base top")

FORMATS = {
    "char": {
        "vi": "Nhân vật chibi",
        "hint": "thú chibi làm MỘT việc, 1–3 đồ vật, thường có đế tròn",
        "style": "parts",
        "decor": "face details (black bead eyes, oval pink blush cheeks, a small nose, a smile), paw pads, buttons on "
                 "clothes, a bead necklace or a ring of studs on the hat band, raised flowers / stars / hearts on the "
                 "shirt, scarf or bag, small flowers / stars / pebbles / shells scattered on the base top",
        "models": ["DogMusic", "KeyboardCat", "Vocalist", "Frogdriver", "SurfingPenguin", "TiringDeliveryGuy",
                   "CrocodileDeliversMail", "Hard_workingTako_chan", "CatKnitting", "BearArt", "PigPicnic",
                   "watering_flower_vs02", "Pirate_Bird", "TheCaptain", "ChillingCapybara", "LazySloth", "AstroRobot",
                   "BabyRabbit", "Reindeer", "Totoro", "Chicken02", "Capybara", "Caterplillar", "FunnyDucks"],
        # Nguoi dung 2026-10-02 (rai ca mu trum): con vat phai du bo phan RIENG thi to mau moi co nghia. Tool chi
        # tach duoc cho co CO THAT / RANH hoac doi MAU; khoi dap noi cung mau (mat lom trong mu trum, nep bung) thi khong.
        "rule": "- A chibi animal/character doing ONE thing, with 1-3 simple chunky props, "
                "usually on a thick round base.\n"
                "- Build the character from SEPARATE simple bulging volumes and give EACH its own flat color: a "
                "round head; a raised round muzzle (or beak) in a lighter color; ears as separate knobs; a raised oval "
                "belly patch in a lighter color; short thick arms; stubby round feet; a tail. 7-12 body parts, each "
                "at least as big as an ear - no fingers, toes, claws, teeth (eyes, blush, paw pads go in the Decor).\n"
                "- Hats and clothes are a separate thick shell with a raised rim (hat brim, collar, cuffs, apron edge) "
                "in a contrasting color. The face stays OUTSIDE: never a hood, mask or costume around the face.\n"
                "- Props are held slightly AWAY from the body (a visible gap), never hugged tight against the belly. "
                "Smooth volumes only: no body folds, rolls, wrinkles or sculpted relief.",
        # Che do PROMPT ANH (Tripo web image-to-3D, 2026-10-07): do 108 FBX goc -> nhan vat ~26 bo phan mau, 9 mau,
        # mang cung mau lon nhat ~24% vi luon MAC DO: ao / quan / giay / gang / mu chia than ra; da con o dau, tay, chan.
        "image_rule": "- ONE chibi animal character doing one activity, DRESSED IN LAYERS, each piece its own color: "
                      "a top (shirt / jacket / sweater) with a contrasting collar and cuffs, a bottom (pants / overalls "
                      "/ skirt), shoes or boots, gloves or sleeves, a hat with a contrasting band, 1-2 accessories "
                      "(bag, scarf, glasses, backpack) and ONE prop held away from the body. The bare animal color "
                      "shows only on the head, hands and feet. Head: a lighter raised muzzle with a colored nose, "
                      "colored inner ears. Usually standing on a thick round base with a contrasting rim.",
        "image_examples": [
            "A chubby brown bear baker holding a tray of three pink cupcakes out in front with both paws. Round "
            "brown head, a raised cream muzzle with a black nose, cream inner ears. A white chef hat with a red band, "
            "a sky blue shirt with white collar and cuffs, a yellow apron with a pocket, brown pants, red shoes, "
            "white gloves, a small orange bag on the hip. On a thick round green base with a cream rim. Details: four "
            "white buttons on the shirt, three raised pink hearts on the apron, yellow studs on the hat band, five "
            "small flowers on the base.",
        ],
        "examples": [
            "A chubby golden hamster barista behind a small round wooden coffee counter, holding a big white coffee "
            "cup up in both paws. Round orange head, a raised cream muzzle ball with a pink nose, "
            "round orange ears with pink insides, a raised cream belly patch, short orange arms, stubby orange feet, "
            "a green apron with a thick white rim, a red coffee grinder on the counter, a thick round cream base. "
            "Decor: black bead eyes and pink blush ovals, pink paw pads, three raised white hearts on the apron, a "
            "ring of eight yellow studs around the counter top, six small pink and white flowers scattered on the "
            "base top.",
            "A round baby penguin fisherman sitting on a small white ice floe, holding a short brown fishing rod out "
            "in front with a red float. Black head and back, a raised white face patch, a raised white oval belly, "
            "an orange beak cone, orange flipper feet, black flippers held away from the body, a yellow knit beanie "
            "with a thick white rim and a red pom-pom, a small blue bucket with one orange fish. Decor: black bead "
            "eyes and pink blush ovals, three raised blue stars on the belly, a ring of eight red studs on the "
            "beanie rim, five round blue pebbles scattered on the ice.",
        ],
    },
    "object": {
        "vi": "Đồ vật",
        "hint": "một đồ vật đơn: xe, nhạc cụ, đồ dùng, túi, quần áo (như xe bus mini)",
        "style": "object",
        "decor": "buttons and knobs, a row of round rivets or studs along edges and bumpers, raised stars / hearts / "
                 "sparkles on panels and straps, round emblems, small round lights, dots on the strap",
        "models": ["Radio", "Guitar_Fix01", "SpeakerStack", "NeonSign", "CoolerBox", "HandBag", "DomeHandbag",
                   "SchoolsBag", "Sweater", "MakeupBag02", "JewelrySet", "Panasonic", "Grilled_Fix01", "SewingMachine",
                   "RockingChair02_vs01", "BookShelf", "DressingWardrobe", "ToyBoxChapter07", "BoardGames", "Cannon",
                   "Anchor", "RumBarrel02", "SailBoat", "AlienBuddy", "Lantern02", "LightSticks", "MusicalLego",
                   "YarnBall", "PlatformMaryJanes", "MahouShoujoDress"],
        "rule": "- ONE chunky object (vehicle, instrument, appliance, furniture, bag, clothing, toy) - no character, "
                "no scene. Built like an assembled toy from 12-20 separate rounded parts: main body split into "
                "distinct shells (e.g. a scooter: front shield, front fender, floorboard, rear body, a separate seat "
                "cushion, a seat back pad, a luggage rack), each with a groove or rim between them and its own color; "
                "wheels as tire + rim + hub cap; lights as ring + lens; buttons, bolts, grilles, straps as separate "
                "raised pieces. Vehicles need no base. Avoid thin rods, antennas, wires, handles thinner than a "
                "finger of the model.",
        "image_rule": "- ONE chunky object built in LAYERS: the main body split into 3-5 panels / shells in "
                      "different colors with raised trims and rims between them; wheels as tire + rim + hub cap; lights "
                      "as ring + lens; handles, straps, bows, knobs and buttons as separate raised pieces. No character.",
        "image_examples": [
            "A chunky retro radio toy. A red rounded body with a cream front panel framed by a thick red trim, a big "
            "round gray speaker ring with a dark blue center, a sky blue tuning window in a white frame, two big "
            "yellow knobs, a brown carrying handle on top with two gray hinges, four black round feet. Details: a "
            "ring of eight white studs around the speaker, three raised yellow stars on the side, two pink heart "
            "buttons on the top.",
        ],
        "examples": [
            "A chunky retro minibus toy with a rounded boxy body and soft edges. Lower body orange, upper body and "
            "roof cream, a thick white rim around the roof. Big sky blue windows: one wide windshield and three side "
            "windows. Four big black tires with gray round hubcaps. Two round yellow headlights in white rings, a gray "
            "oval grille and thick gray bumpers front and back. Two chunky round red side mirrors on the front corners. "
            "Decor: a row of six round white rivets along each bumper, three raised yellow stars on each side, a "
            "round red emblem on the front.",
            "A chunky cute retro camera toy with a rounded box body. Black body with a cream top plate, a big gray "
            "round lens with a sky blue glass center, a red round shutter button and a small yellow flash box on top, "
            "two chunky brown strap loops on the sides. Decor: a ring of ten small white dots around the lens, two "
            "raised pink hearts on the front, four yellow round buttons on the top plate.",
        ],
    },
    "food": {
        "vi": "Món ăn",
        "hint": "một món ăn trong bát/đĩa, topping to rõ (như Ramen, Udon, bánh)",
        "style": "object",
        "decor": "round emblems or a ring of dots on the bowl / plate side, sprinkles and seeds as chunky dots, "
                 "small berries, small herb leaves, swirls on fish cakes, crumbs as round pebbles on the plate",
        "models": ["Ramen", "Global_Udon", "MixedRice", "Steak", "Shavedlce", "FrenchBakery_vs01",
                   "Global_HouseCake_Fix01", "LV1_update", "Broccoli", "Radish"],
        "rule": "- ONE dish or snack: a chunky bowl / plate / cup and 4-8 BIG toppings, each a separate rounded chunk "
                "in its own color (egg, meat slice, shrimp, leaf, cherry...). No sauce drips, no tiny crumbs, no "
                "steam wisps, no text. Chopsticks or spoon only if thick.",
        "image_rule": "- ONE dish: a bowl / plate / cup with a thick contrasting rim and a base ring, 4-8 big "
                      "separate toppings each in its own color, emblem shapes on the bowl side. No sauce drips, steam "
                      "or crumbs.",
        "image_examples": [
            "A chunky bowl of ramen. A dark blue bowl with a thick white rim and a red base ring, cream noodles, "
            "toppings as big separate chunks: half a boiled egg (white with a yellow yolk), two pink fish cakes, a "
            "brown meat slice, a green nori sheet, a pile of green onion, two thick brown chopsticks on the rim. "
            "Details: three round red emblems on the bowl side, a white swirl on each fish cake, six green onion "
            "rings on the noodles.",
        ],
        "examples": [
            "A chunky bowl of ramen toy. Thick black bowl with a red rim, cream noodles piled in the middle, toppings as "
            "big separate chunks: half a boiled egg (white with a yellow yolk), two pink round fish cakes with a white "
            "swirl, one brown meat slice, a green leaf of nori and a small pile of green onion. Two thick brown "
            "chopsticks resting on the rim. Decor: three round red emblems on the bowl side, a white raised swirl on "
            "each fish cake, six small green onion rings scattered on the noodles.",
        ],
    },
    "scene": {
        "vi": "Cảnh nhỏ",
        "hint": "một góc cảnh trên đế: quầy, lều, bãi biển, sân khấu (3–6 đồ vật to)",
        "style": "multi",
        "decor": "small flowers, pebbles, shells and stars scattered on the base top, a row of round studs along the "
                 "base rim, white dots on mushrooms, hearts and stars on signs and walls, round buttons on boxes",
        "models": ["BeachBar", "HawaiiBeach", "PalmTreeHammock", "Camp", "Hive_camp", "BirdHouse_camp", "LotusPond",
                   "NachosTable", "Ramen_Stall02", "Ramen_Sigh", "Treasure_Hunt", "JollyRoger", "ConcertStage",
                   "DrumChapter06", "Vanity", "RoyalSofa", "Accessories", "Windmill", "PlanetPals", "Blender"],
        "rule": "- A small diorama on ONE thick base (round or rounded square): one main structure plus 3-6 big "
                "chunky props, no characters or at most one small one. Every prop a separate rounded object in its "
                "own color, spaced apart so they do not merge. No fences of thin sticks, no grass blades, no text.",
        "image_rule": "- A small diorama on a thick base with a contrasting rim: one main structure built from "
                      "parts in different colors (roof, walls, door, window frames, trims) plus 3-6 big props spaced "
                      "apart. No characters, or one small one.",
        "image_examples": [
            "A tiny camping scene on a thick round green base with a brown rim: a yellow tent with a red door flap and "
            "a white roof trim, a brown log campfire with orange flames, a blue cooler box with a white lid, a dark "
            "green pine tree with a brown trunk, two red mushrooms with cream stems. Details: white dots on the "
            "mushroom caps, six small yellow flowers and four gray pebbles on the base, a row of brown studs on the "
            "rim.",
        ],
        "examples": [
            "A tiny camping scene on a thick round green base: a big yellow tent with a red door flap, a small brown log "
            "campfire with chunky orange flames, a blue cooler box, a round dark green pine tree and two pink "
            "mushrooms. Decor: white dots on the mushroom caps, a raised red heart on the tent, six small yellow "
            "flowers and four gray pebbles scattered on the base top, a row of round brown studs along the base rim.",
        ],
    },
    "plant": {
        "vi": "Cây & hoa",
        "hint": "cây, hoa, xương rồng trong chậu (như Cactus, TreeGreen)",
        "style": "object",
        "decor": "small flowers and buds, white bumps as spikes, a ring of dots or small hearts on the pot, round "
                 "pebbles in the pot, a small ladybug or butterfly on a leaf",
        "models": ["Cactus_fix", "TreeGreen", "Lv1", "RabbitFL", "Broccoli"],
        "rule": "- ONE plant in a chunky pot or on a small base: thick stem, a few BIG rounded leaves / petals / "
                "fruits, each a separate chunk. Pot with a thick rim in a contrasting color. No thin twigs, no "
                "single grass blades, no flowers on thin stalks.",
        "image_rule": "- ONE plant in a pot: the pot with a thick contrasting rim and a band, a thick stem, big "
                      "rounded leaves / petals / fruits each a separate chunk, soil or pebbles on top in its own color.",
        "image_examples": [
            "A chunky cactus in a round orange clay pot with a thick cream rim and a blue band. A tall green cactus "
            "body with two round arms, a big pink flower with a yellow center on top, brown soil with gray pebbles. "
            "Details: small white bumps as spikes, a ring of eight white dots on the band, two raised pink hearts on "
            "the pot.",
        ],
        "examples": [
            "A chunky cactus in a round orange clay pot with a thick cream rim. One tall green cactus body with two "
            "round green arms and a big pink flower on top. Decor: small white bumps as spikes on the cactus, five "
            "round brown pebbles in the pot, a ring of eight white dots and two raised pink hearts on the pot side.",
        ],
    },
}

# ---------------------------------------------------------------- CHU DE
THEMES = {
    "free": {"vi": "Tự do", "en": "", "models": []},
    "music": {"vi": "Âm nhạc", "en": "music: instruments, singers, concert stage, speakers, radio, light sticks",
              "models": ["DogMusic", "KeyboardCat", "Vocalist", "DrumChapter06", "Guitar_Fix01", "SpeakerStack",
                         "ConcertStage", "MusicNote_Chapter6", "MusicalLego", "LightSticks", "NeonSign", "Radio"]},
    "pirate": {"vi": "Hải tặc", "en": "pirates and the sea: ships, anchors, cannons, treasure, barrels, sea creatures",
               "models": ["JollyRoger", "Cannon", "Anchor", "TheCaptain", "Pirate_Bird", "Treasure_Hunt",
                          "RumBarrel02", "SteernSquid", "SailBoat"]},
    "food": {"vi": "Ẩm thực", "en": "food and cooking: dishes, bakery, street food stalls, kitchen appliances",
             "models": ["Ramen", "Global_Udon", "MixedRice", "Steak", "Shavedlce", "FrenchBakery_vs01",
                        "Global_HouseCake_Fix01", "NachosTable", "Ramen_Stall02", "Ramen_Sigh", "Grilled_Fix01",
                        "Blender", "Broccoli", "Radish", "LV1_update"]},
    "fashion": {"vi": "Thời trang & làm đẹp", "en": "fashion and beauty: clothes, shoes, bags, makeup, jewelry, vanity",
                "models": ["Sweater", "MahouShoujoDress", "PlatformMaryJanes", "DomeHandbag", "HandBag",
                           "MakeupBag02", "JewelrySet", "Vanity", "DressingWardrobe", "SchoolsBag"]},
    "home": {"vi": "Nhà cửa & đồ dùng", "en": "home: furniture, appliances, crafts, board games, toy boxes",
             "models": ["BookShelf", "RoyalSofa", "RockingChair02_vs01", "Accessories", "SewingMachine", "YarnBall",
                        "Panasonic", "BoardGames", "ToyBoxChapter07", "DecorativeLights", "CatKnitting"]},
    "beach": {"vi": "Biển & mùa hè", "en": "beach and summer: surfing, beach bar, palm trees, coolers, crabs, fish",
              "models": ["BeachBar", "HawaiiBeach", "PalmTreeHammock", "SurfingPenguin", "FunnyDucks",
                         "ChillingCapybara", "Crab", "CoolerBox", "ApexPreDator"]},
    "nature": {"vi": "Cắm trại & thiên nhiên", "en": "camping and nature: tents, beehives, birdhouses, ponds, "
                                                  "gardens, windmills, forest animals",
               "models": ["Camp", "Hive_camp", "BirdHouse_camp", "TreeGreen", "Cactus_fix", "LotusPond", "Lv1",
                          "watering_flower_vs02", "PigPicnic", "Windmill", "LazySloth", "Caterplillar", "RabbitFL"]},
    "space": {"vi": "Vũ trụ", "en": "space: UFOs, robots, planets, stars, moon, aliens, monsters",
              "models": ["AlienBuddy", "AstroRobot", "AtomicStar", "Moon", "PlanetPals", "GlobMonster"]},
    "jobs": {"vi": "Nghề nghiệp", "en": "jobs: delivery, driver, painter, gardener, chef, captain, mechanic",
             "models": ["CrocodileDeliversMail", "TiringDeliveryGuy", "Hard_workingTako_chan", "Frogdriver",
                        "BearArt", "watering_flower_vs02", "TheCaptain"]},
    "festival": {"vi": "Lễ hội", "en": "festivals and seasons: Christmas, mid-autumn lanterns, Halloween, "
                                       "New Year, birthdays",
                 "models": ["Reindeer", "Lantern02", "Moon", "Global_HouseCake_Fix01"]},
    "school": {"vi": "Học đường & đồ chơi", "en": "school and toys: school bags, books, stationery, toys, sweets",
               "models": ["SchoolsBag", "BookShelf", "BoardGames", "ToyBoxChapter07", "MusicalLego", "LV1_update",
                          "YarnBall"]},
}


def items_formats():
    return [(k, v["vi"], v["hint"]) for k, v in FORMATS.items()]


def items_themes():
    return [(k, v["vi"], v["en"] or "Claude tự chọn chủ đề") for k, v in THEMES.items()]
