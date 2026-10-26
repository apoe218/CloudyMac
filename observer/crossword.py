"""Daily crossword for the H-Town Observer print edition.

A 15x15 freeform puzzle generated from the clue bank below, seeded by the date so
every morning is different and yesterday's solution can be regenerated exactly.
Themed entries (Houston/Texas, Aggies/college football, Liverpool/soccer, weather,
space) are favoured; the rest is general knowledge for crossing letters.
"""
import html
import random
import re
from datetime import date

SIZE = 15

# CATEGORY: H=Houston/Texas, A=Aggies/CFB, L=Liverpool/soccer, W=weather/space, G=general
BANK = """
H|ASTRODOME|Houston's "Eighth Wonder of the World," opened in 1965
H|ASTROS|Houston's American League baseball club
H|TEXANS|NFL team that plays at NRG Stadium
H|ROCKETS|Houston NBA team named for the local space industry
H|DYNAMO|Houston's MLS club
H|BAYOU|Slow-moving Gulf Coast waterway
H|BUFFALO|___ Bayou, which winds through downtown Houston
H|RODEO|Annual Houston Livestock Show and ___
H|NASA|Agency running Johnson Space Center
H|GALVESTON|Island city south of Houston
H|KATY|Suburb west of Houston along I-10
H|SUGARLAND|Fort Bend County city with a sweet name
H|TEXAS|Lone Star State
H|ALAMO|San Antonio mission remembered in a battle cry
H|AUSTIN|Texas capital
H|DALLAS|Cowboys' home city
H|BRAZOS|River that gives College Station's county its name
H|LONESTAR|___ State: Texas
H|BLUEBONNET|Texas state flower
H|ARMADILLO|Armored roadside critter of Texas
H|BRISKET|Smoked Texas barbecue staple
H|KOLACHE|Czech pastry beloved in Texas
H|FAJITA|Sizzling Tex-Mex platter
H|QUESO|Melted cheese dip, in Tex-Mex
H|TEXMEX|Cuisine of nachos and enchiladas
H|JALAPENO|Pepper often stuffed with cheese
H|LONGHORN|Texas cattle breed with a famous spread of horns
H|MESQUITE|Wood used for smoking meats in Texas
H|BEYONCE|Houston-born superstar
H|NRG|___ Stadium, home of the Texans
H|HOUSTON|Space City, USA
H|SAM|Houston's namesake, ___ Houston
H|HERMANN|___ Park, home of the Houston Zoo
H|MONTROSE|Eclectic Houston neighborhood near the Museum District
H|HEIGHTS|The ___, historic Houston neighborhood
H|SPACE|___ City, Houston's nickname
H|PECAN|Texas state tree's nut
H|CACTUS|Prickly desert plant
H|COWBOY|Ranch hand on horseback
H|RANCH|Large Texas spread
H|HOWDY|Texas greeting
A|AGGIES|Texas A&M athletes
A|GIGEM|Aggie cheer: "___ 'Em!"
A|WHOOP|Aggie exclamation
A|REVEILLE|Texas A&M's collie mascot
A|KYLE|___ Field, Aggie home gridiron
A|CORPS|Texas A&M's ___ of Cadets
A|MAROON|Aggie color
A|TWELFTHMAN|Aggie tradition of the student body as the extra player
A|YELL|What Aggie "leaders" lead
A|SEC|Conference of the Aggies and Crimson Tide
A|HEISMAN|Trophy for the nation's top college player
A|MANZIEL|Aggie quarterback who won the 2012 Heisman
A|BRYAN|Twin city of College Station
A|BATTALION|Texas A&M's student newspaper, The ___
A|TOUCHDOWN|Six-point score
A|FIELDGOAL|Three-point kick between the uprights
A|QUARTERBACK|Signal-caller
A|PUNT|Fourth-down kick
A|FUMBLE|Dropped ball that is still live
A|BLITZ|Rush the passer with extra defenders
A|GRIDIRON|Football field, in older parlance
A|ENDZONE|Where six points are scored
A|SAFETY|Two-point defensive score
A|HUDDLE|Players' pre-snap gathering
A|KICKOFF|Start of a half
A|INTERCEPTION|Defensive "pick," formally
A|SACK|QB takedown behind the line
A|ROSE|___ Bowl, "Granddaddy of Them All"
A|PLAYOFF|Postseason tournament
A|TAILGATE|Parking-lot party before kickoff
A|TACKLE|Bring a runner down
A|SNAP|Center's start to a play
A|CRIMSON|Alabama's color
A|TIDE|Alabama's nickname: Crimson ___
A|VOLS|Tennessee's nickname
A|GATORS|Florida's team
A|BULLDOGS|Georgia's team
A|TIGERS|LSU's feline team
A|RAZORBACKS|Arkansas team whose fans call the Hogs
A|OKLAHOMA|Sooner State
A|SOONERS|Oklahoma football team
A|GEORGIA|Peach State
A|AUBURN|Alabama school with Tigers
A|OLE|___ Miss
A|VANDERBILT|Nashville SEC school
A|MIZZOU|Missouri, informally
A|KENTUCKY|Bluegrass State
A|COACH|Sideline strategist
A|RIVALRY|Texas-Texas A&M, for decades
A|HELMET|Gridiron headgear
A|UPRIGHTS|Goalposts' vertical bars on a football field
L|ANFIELD|Liverpool's home ground
L|KOP|Famous end of Anfield
L|SHANKLY|Bill, legendary Liverpool manager of the 1960s and '70s
L|DALGLISH|"King Kenny" of Liverpool
L|GERRARD|Steven, long-time Liverpool captain
L|KLOPP|Jurgen who won the 2019 Champions League with Liverpool
L|SALAH|Egyptian forward who joined Liverpool in 2017
L|VANDIJK|Dutch defender at Liverpool
L|MERSEY|River beside Liverpool
L|MERSEYSIDE|Liverpool's metropolitan county
L|ISTANBUL|City of Liverpool's 2005 Champions League comeback
L|BEATLES|Liverpool's Fab Four
L|YNWA|Anfield anthem, in initials
L|LIVERBIRD|Mythical bird on Liverpool's crest
L|EVERTON|Liverpool's neighbors across Stanley Park
L|DERBY|Match between local rivals
L|HATTRICK|Three goals in one game
L|OFFSIDE|Flag-raising offense for a lurking forward
L|GOALIE|Keeper
L|STRIKER|Forward who scores
L|WINGER|Wide attacker
L|PENALTY|Spot kick awarded for a foul in the box
L|CORNER|Kick from the arc
L|NUTMEG|Pass the ball through a defender's legs
L|TREBLE|Three trophies in a season
L|WEMBLEY|London stadium hosting FA Cup finals
L|PITCH|Soccer field, in Britain
L|FIXTURE|Scheduled match
L|ARSENAL|Gunners of North London
L|CHELSEA|Blues from Stamford Bridge
L|SPURS|Tottenham's nickname
L|UEFA|Governing body of European soccer
L|FIFA|World soccer's governing body
L|ANTHEM|Stirring song played before Champions League kickoff
L|MADRID|Spanish capital with a famous Real club
L|REAL|___ Madrid
L|BAYERN|Munich Bundesliga giants
L|JUVENTUS|Turin's "Old Lady"
L|BARCELONA|Catalan club with Camp Nou
L|STOPPAGE|___ time, added minutes
L|CAPTAIN|Armband wearer
L|REFEREE|Whistle-blower
L|WHISTLE|What the ref blows
L|PREMIER|___ League
L|CHAMPIONS|Winners of the league, e.g.
L|SCARF|Supporter's woolen accessory
L|RELEGATION|Fate of clubs finishing at the bottom
W|HUMIDITY|What makes Houston summers feel sticky
W|HURRICANE|Gulf storm named from an annual list
W|HARVEY|2017 hurricane that flooded Houston
W|DROUGHT|Dry spell
W|FRONT|Cold ___ (welcome relief in Houston)
W|SQUALL|Sudden gust and storm
W|CUMULUS|Puffy fair-weather cloud
W|BAROMETER|Pressure gauge
W|ISOBAR|Line of equal pressure on a map
W|TORNADO|Twister
W|MONSOON|Seasonal rain wind
W|DEWPOINT|Temperature at which air condenses
W|FLOOD|Bayou overflow
W|TROPICAL|___ storm
W|BREEZE|Gentle wind
W|HAIL|Frozen pellets from the sky
W|SLEET|Icy rain
W|RAINBOW|Arc after a shower
W|NIMBUS|Rain cloud
W|FORECAST|Weatherman's prediction
W|ORBIT|Path around a planet
W|APOLLO|NASA program that put 12 people on the Moon
W|GEMINI|Two-person NASA capsule program
W|COMET|Icy visitor with a tail
W|NEBULA|Interstellar cloud
W|GALAXY|Milky Way, for one
W|LUNAR|Of the Moon
W|MARS|Red Planet
W|SATURN|Ringed giant
W|SHUTTLE|Reusable NASA spacecraft retired in 2011
W|ASTRONAUT|Space traveler
W|LAUNCH|Liftoff
W|CAPSULE|Small spacecraft module
W|ROVER|Mars explorer
W|MISSION|___ Control in Houston
W|TELESCOPE|Hubble, for one
W|METEOR|Shooting star
W|ECLIPSE|Sun-blocking event
G|CAIRO|Egypt's capital
G|LIMA|Peru's capital
G|OSLO|Norway's capital
G|ROME|Capital on the Tiber
G|PARIS|City of Light
G|TOKYO|Japan's capital
G|NILE|Egyptian river
G|DANUBE|River through Vienna and Budapest
G|AMAZON|Rainforest river
G|ALPS|European mountain range
G|KENYA|Nairobi's country
G|CANADA|Ottawa's country
G|BRAZIL|Samba nation
G|SPAIN|Madrid's country
G|ITALY|Boot-shaped nation
G|EGYPT|Land of the pyramids
G|PERU|Machu Picchu's land
G|CHILE|Long country along the Andes
G|GHANA|Accra's country
G|JAPAN|Land of the Rising Sun
G|INDIA|Delhi's country
G|ATLANTIC|Ocean east of the US
G|PACIFIC|Largest ocean
G|ARCTIC|Polar region in the far north
G|SAHARA|Largest hot desert
G|EVEREST|World's highest peak
G|NAIROBI|Kenya's capital
G|OTTAWA|Canada's capital
G|BERLIN|German capital
G|LONDON|Thames city
G|VIENNA|Austrian capital
G|DUBLIN|Irish capital
G|LISBON|Portuguese capital
G|ATHENS|Greek capital
G|ARIA|Opera solo
G|ERA|Time period
G|ALOE|Soothing plant for sunburn
G|OREO|Cookie with a twist-off top
G|ATLAS|Book of maps
G|IDEA|Brainstorm product
G|ELITE|Select group
G|OASIS|Desert watering hole
G|ANTLER|Deer headgear
G|TEAL|Blue-green
G|SALSA|Dip or dance
G|TACO|Tuesday special
G|OPERA|"La Traviata," for one
G|PIANO|88-key instrument
G|VIOLIN|Strad, for one
G|ORGAN|Church instrument
G|CELLO|Bowed instrument bigger than a violin
G|BANJO|Bluegrass string instrument
G|GUITAR|Six-string instrument
G|TENOR|High male voice
G|ALTO|Voice between soprano and tenor
G|RADIO|Dashboard device
G|COFFEE|Morning cup
G|LATTE|Espresso with steamed milk
G|PASTA|Spaghetti, e.g.
G|PIZZA|Pie with toppings
G|BAGEL|Ring-shaped roll
G|LEMON|Sour citrus fruit
G|LIME|Green citrus fruit
G|MANGO|Tropical fruit
G|OLIVE|Martini garnish
G|ONION|Layered veggie that makes you cry
G|ESSAY|Written assignment
G|STATE|Say formally
G|TRAIN|Locomotive's string of cars
G|RIVER|Flowing waterway
G|ROUTE|Planned way
G|STEAK|Grilled cut of beef
G|TOAST|Browned bread
G|SPICE|Cumin or paprika
G|ANGLE|Fishing activity or point of view
G|ENTER|Come in
G|RESET|Start over on a device
G|ISLAND|Land surrounded by water
G|NOTION|Vague idea
G|STORM|Rain-and-wind event
G|ROAST|Oven-cooked meat
G|TENNIS|Net game with a racket
G|GOLF|Game of birdies and bogeys
G|HOCKEY|Puck sport
G|BASEBALL|Diamond sport
G|MARATHON|26.2-mile race
G|SPRINT|Short, fast race
G|OLYMPICS|Quadrennial sports event
G|TROPHY|Cup awarded to a winner
G|STADIUM|Large sports venue
G|ARENA|Indoor sports venue
G|SEASON|Time of year, or what you do to a steak
G|INSIDE|Not outdoors
G|OUTSIDE|Not indoors
G|AREA|Region
G|OPEN|Not closed
G|EAST|Direction of sunrise
G|WEST|Direction of sunset
G|NORTH|Compass heading, up on a map
G|SOUTH|Compass heading, down on a map
"""


def load_bank():
    seen, out = set(), []
    for line in BANK.strip().splitlines():
        cat, ans, clue = line.split("|", 2)
        ans = re.sub(r"[^A-Z]", "", ans.upper())
        if len(ans) < 3 or ans in seen:
            continue
        seen.add(ans)
        out.append((cat, ans, clue.strip()))
    return out


class Grid:
    def __init__(self):
        self.cells = {}   # (r,c) -> letter
        self.dirs = {}    # (r,c) -> set of 'A'/'D' words covering the cell
        self.words = []   # (answer, r, c, dir, clue)
        self.by_letter = {}  # letter -> [(r,c)]

    def fits(self, w, r, c, d):
        dr, dc = (0, 1) if d == "A" else (1, 0)
        n = len(w)
        er, ec = r + dr * n, c + dc * n
        if not (0 <= r < SIZE and 0 <= c < SIZE and 0 <= er - dr < SIZE and 0 <= ec - dc < SIZE):
            return -1
        if (r - dr, c - dc) in self.cells or (er, ec) in self.cells:
            return -1
        cross = 0
        for i, ch in enumerate(w):
            p = (r + dr * i, c + dc * i)
            have = self.cells.get(p)
            if have is not None:
                if have != ch or d in self.dirs[p]:
                    return -1
                cross += 1
            else:
                # empty cell: neighbours on either side (perpendicular) must be empty
                for q in ((p[0] + dc, p[1] + dr), (p[0] - dc, p[1] - dr)):
                    if q in self.cells:
                        return -1
        return cross

    def put(self, w, r, c, d, clue):
        dr, dc = (0, 1) if d == "A" else (1, 0)
        for i, ch in enumerate(w):
            p = (r + dr * i, c + dc * i)
            if p not in self.cells:
                self.by_letter.setdefault(ch, []).append(p)
            self.cells[p] = ch
            self.dirs.setdefault(p, set()).add(d)
        self.words.append((w, r, c, d, clue))

    def bbox(self):
        rs = [p[0] for p in self.cells]
        cs = [p[1] for p in self.cells]
        return min(rs), max(rs), min(cs), max(cs)


def attempt(bank, rng):
    g = Grid()
    themed = {"H": 1.2, "A": 1.2, "L": 1.2, "W": 0.7, "G": 0.0}
    order = sorted(bank, key=lambda e: -(rng.random() + themed[e[0]] * 0.5))
    longs = [e for e in order if len(e[1]) >= 9] or order
    cat, w, clue = rng.choice(longs)
    g.put(w, SIZE // 2 + rng.choice((-1, 0, 1)), (SIZE - len(w)) // 2, "A", clue)
    used = {w}
    while True:
        best, best_score = [], 0
        for cat, w, clue in order:
            if w in used:
                continue
            for i, wc in enumerate(w):
                for pr, pc in g.by_letter.get(wc, ()):
                    for d in ("A", "D"):
                        r, c = (pr, pc - i) if d == "A" else (pr - i, pc)
                        k = g.fits(w, r, c, d)
                        if k < 1:
                            continue
                        score = k * 3 + len(w) * 0.3 + themed[cat] + rng.random()
                        if score > best_score + 1e-9:
                            best, best_score = [(w, r, c, d, clue)], score
        if not best:
            break
        w, r, c, d, clue = best[0]
        g.put(w, r, c, d, clue)
        used.add(w)
    return g


def runs_ok(g):
    """Every run of 2+ letters in the grid must be exactly one placed answer."""
    found = set()
    for d in ("A", "D"):
        for r in range(SIZE):
            for c in range(SIZE):
                dr, dc = (0, 1) if d == "A" else (1, 0)
                if (r, c) in g.cells and (r - dr, c - dc) not in g.cells:
                    n = 0
                    while (r + dr * n, c + dc * n) in g.cells:
                        n += 1
                    if n >= 2:
                        found.add((r, c, d, n))
    placed = {(r, c, d, len(w)) for w, r, c, d, _ in g.words}
    return found == placed


def generate(day, tries=40):
    rng = random.Random(day.toordinal() * 7919)
    bank = load_bank()
    best, best_score = None, -1
    for _ in range(tries):
        g = attempt(bank, rng)
        if not runs_ok(g):
            continue
        r0, r1, c0, c1 = g.bbox()
        score = len(g.words) * 10 + (r1 - r0) + (c1 - c0) + len(g.cells) * 0.2
        if score > best_score:
            best, best_score = g, score
    return best


def number(g):
    """Standard numbering: reading order over cells that start a word."""
    starts = {}
    for w, r, c, d, clue in g.words:
        starts.setdefault((r, c), {})[d] = (w, clue)
    nums, n = {}, 0
    for r in range(SIZE):
        for c in range(SIZE):
            if (r, c) in starts:
                n += 1
                nums[(r, c)] = n
    across, down = [], []
    for (r, c), dd in starts.items():
        for d, (w, clue) in dd.items():
            (across if d == "A" else down).append((nums[(r, c)], clue, len(w)))
    return nums, sorted(across), sorted(down)


def render(day):
    """Return (puzzle_html, answers_html, stats) for a given date."""
    g = generate(day)
    y = generate(date.fromordinal(day.toordinal() - 1))
    nums, across, down = number(g)
    cells = []
    for r in range(SIZE):
        for c in range(SIZE):
            if (r, c) in g.cells:
                n = nums.get((r, c))
                cells.append(f'<div>{f"<i>{n}</i>" if n else ""}</div>')
            else:
                cells.append('<div class="b"></div>')

    def clue_list(items):
        return "".join(f'<li value="{n}"><b>{n}</b> {html.escape(clue)} <span>({ln})</span></li>'
                       for n, clue, ln in items)

    ymini = []
    for r in range(SIZE):
        for c in range(SIZE):
            ch = y.cells.get((r, c))
            ymini.append(f'<div>{ch}</div>' if ch else '<div class="b"></div>')
    puzzle = (f'<div class="xw">{"".join(cells)}</div>'
              f'<div class="clues"><div><h4>Across</h4><ol>{clue_list(across)}</ol></div>'
              f'<div><h4>Down</h4><ol>{clue_list(down)}</ol></div></div>')
    answers = f'<div class="xwmini">{"".join(ymini)}</div>'
    return puzzle, answers, {"words": len(g.words), "across": len(across), "down": len(down)}


if __name__ == "__main__":
    import sys, time
    t = time.time()
    day = date.today()
    g = generate(day)
    for r in range(SIZE):
        print("".join(g.cells.get((r, c), "·") for c in range(SIZE)))
    print(len(g.words), "words", round(time.time() - t, 1), "s", file=sys.stderr)
