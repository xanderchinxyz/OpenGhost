from math import sqrt

from py5 import *
import py5

# width and height of the sketch
WIDTH = 720
HEIGHT = 720

# --- calm "fish tank" feel -------------------------------------------------
# A handful of fish drifting slowly, gently avoiding one another. No predators.
SEPARATION_FACTOR = 0.45     # strong: keeps each fish's footprint clear of others
CENTER_FACTOR = 0.004        # very light pull toward nearby fish (loose schooling)
VELOCITY_FACTOR = 0.03       # very light heading match with nearby fish
SCHOOL_RANGE = 170           # how far a fish notices others for schooling
BOUND_FACTOR = 0.30          # easy turn away from the glass
WANDER = 0.02                # tiny random steering -> lazy, lifelike drift
DAMPING = 0.985              # gentle drag so fish coast and slow down
FACING_THRESHOLD = 0.08      # min horizontal speed before a fish flips which way it faces
EPSILON = 1e-6

# --- the fish ---------------------------------------------------------------
# Multi-line ASCII art, RIGHT-FACING only (the left-facing version is produced
# in code by mirror_rows()). Drawn in a MONOSPACE font so rows/spaces line up;
# spaces shape the silhouette and are skipped when drawing.
ROUND = ("  ^^^",
         " /===\\",
         "><==(O)>",
         " \\===/")                 # rounded reef fish

TALL  = ("   /\\",
         "  /==\\",
         "><(==O)>",
         "  \\==/",
         "   \\/")                   # tall, disc-shaped fish

LONG  = ("  ^^^^^^",
         "><======(O)>",
         "  vvvvvv")                 # long torpedo fish

BETTA = ("  \\\\",
         "   \\=\\",
         "><==(O)>",
         "   /=/",
         "  //")                     # flowing-finned fish

TINY  = ("  ^",
         "><(o>",
         "  v")                      # little darter

# A palette is a list of RGB bands painted head->tail across the fish, so the
# HEAD colour (palette[0]) leads the swim direction. Multi-band palettes give
# real-fish patterns; single-band palettes are solid-coloured.
WHITE = (245, 245, 245)
DARK  = (45, 45, 55)

# name, art rows, text size (px), palette (head->tail), max drift speed
FISH_TANK = (
    ("clownfish",   ROUND, 22, ((255, 130, 40), WHITE, DARK),            0.70),
    ("blue tang",   TALL,  24, ((45, 120, 235), DARK, (255, 215, 60)),   0.60),
    ("koi",         LONG,  22, (WHITE, (240, 120, 50), DARK),            0.65),
    ("yellow tang", ROUND, 20, ((255, 205, 50),),                       0.70),
    ("betta",       BETTA, 22, ((230, 70, 100), (255, 120, 150)),       0.55),
    ("neon tetra",  TINY,  15, ((120, 200, 255), (235, 60, 80)),        1.00),
)


MIRROR = str.maketrans("()<>[]{}/\\bdpq", ")(><][}{\\/dbqp")
def mirror_rows(rows):
    """Flip right-facing art to left-facing: reverse each row and swap paired glyphs."""
    w = max(len(r) for r in rows)
    return tuple(r.ljust(w)[::-1].translate(MIRROR) for r in rows)


class Boid:
    __slots__ = ("x", "y", "dx", "dy", "name", "rows", "ts", "palette", "speed", "radius", "facing")

    def __init__(self, x, y, dx, dy, name, rows, ts, palette, speed):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.name = name
        self.rows = rows
        self.ts = ts
        self.palette = palette
        self.speed = speed
        self.facing = 1 if dx >= 0 else -1   # persistent heading; flips only past a threshold
        # personal-space bubble sized to the fish's rendered footprint, so big
        # fish keep big gaps and nothing overlaps (Menlo advance ~0.6 em wide).
        w = max(len(r) for r in rows) * ts * 0.60
        h = len(rows) * ts * 1.15
        self.radius = 0.5 * max(w, h) + 6

    def update(self):
        self.x += self.dx
        self.y += self.dy
        # only flip facing on clear horizontal motion -> no rapid mirror "flashing"
        if self.dx > FACING_THRESHOLD:
            self.facing = 1
        elif self.dx < -FACING_THRESHOLD:
            self.facing = -1

    def show(self):
        # draw the fish as multi-line monospace ASCII art, facing its heading.
        # Each column is painted from one of the palette's colour bands.
        text_font(fish_font)                 # monospace -> rows & spaces align
        text_size(self.ts)
        text_align(LEFT, CENTER)

        facing_right = self.facing >= 0
        rows = self.rows if facing_right else mirror_rows(self.rows)

        palette = self.palette
        bands = len(palette)
        width_cols = max(len(r) for r in rows)
        char_w = text_width("0")             # uniform advance in a monospace font
        line_h = self.ts * 1.05

        left_x = self.x - (width_cols * char_w) / 2.0     # centre the whole sprite
        top_y = self.y - (len(rows) - 1) * line_h / 2.0

        for r, row in enumerate(rows):
            y = top_y + r * line_h
            for c, ch in enumerate(row):
                if ch == " ":
                    continue                 # spaces just shape the silhouette
                base = c * bands // width_cols
                # head colour (palette[0]) leads the swim direction
                band = (bands - 1 - base) if facing_right else base
                fill(*palette[band])
                text(ch, left_x + c * char_w, y)

    def keep_in_bounds(self):
        # turn away while the whole footprint is still inside the glass
        pad = self.radius
        if self.x < pad:
            self.dx += BOUND_FACTOR
        elif self.x > WIDTH - pad:
            self.dx -= BOUND_FACTOR

        if self.y < pad:
            self.dy += BOUND_FACTOR
        elif self.y > HEIGHT - pad:
            self.dy -= BOUND_FACTOR

    def limit_speed(self):
        speed = sqrt(self.dx * self.dx + self.dy * self.dy)
        if speed > self.speed:
            self.dx = (self.dx / speed) * self.speed
            self.dy = (self.dy / speed) * self.speed

    def apply_behaviors(self, boids):
        """Calm tank: keep clear of others, drift loosely together, wander."""
        sep_x = sep_y = 0.0
        center_x = center_y = 0.0
        avg_dx = avg_dy = 0.0
        neighbors = 0

        for other in boids:
            if other is self:
                continue
            dx = self.x - other.x
            dy = self.y - other.y
            dist = sqrt(dx * dx + dy * dy) + EPSILON

            # anti-overlap: push apart while personal bubbles intersect
            gap = self.radius + other.radius
            if dist < gap:
                push = (gap - dist) / gap        # 0 at touch, 1 when concentric
                sep_x += (dx / dist) * push
                sep_y += (dy / dist) * push

            # loose schooling with whoever is nearby
            if dist < SCHOOL_RANGE:
                center_x += other.x
                center_y += other.y
                avg_dx += other.dx
                avg_dy += other.dy
                neighbors += 1

        self.dx += sep_x * SEPARATION_FACTOR
        self.dy += sep_y * SEPARATION_FACTOR

        if neighbors > 0:
            center_x /= neighbors
            center_y /= neighbors
            avg_dx /= neighbors
            avg_dy /= neighbors
            self.dx += (center_x - self.x) * CENTER_FACTOR
            self.dy += (center_y - self.y) * CENTER_FACTOR
            self.dx += (avg_dx - self.dx) * VELOCITY_FACTOR
            self.dy += (avg_dy - self.dy) * VELOCITY_FACTOR

        # lazy wander + gentle drag -> slow, calm, drifting-tank feel
        self.dx += random(-WANDER, WANDER)
        self.dy += random(-WANDER, WANDER)
        self.dx *= DAMPING
        self.dy *= DAMPING


def settings():
    size(WIDTH, HEIGHT, py5.P2D)

boids: list[Boid] = []
fish_font = None
seaweed: list = []        # swaying strands rooted along the bottom
bubbles: list = []        # slow rising bubbles
tick = 0                  # frame counter driving sway/rise animation

def setup():
    global fish_font
    background(0)
    fish_font = create_font("Menlo", 32)     # monospace so multi-line art lines up

    # spread the fish out so they start with plenty of open water around them
    spots = (
        (WIDTH * 0.25, HEIGHT * 0.30), (WIDTH * 0.72, HEIGHT * 0.27),
        (WIDTH * 0.50, HEIGHT * 0.50), (WIDTH * 0.28, HEIGHT * 0.70),
        (WIDTH * 0.75, HEIGHT * 0.68), (WIDTH * 0.52, HEIGHT * 0.85),
    )

    boids.clear()
    for (name, rows, ts, palette, speed), (sx, sy) in zip(FISH_TANK, spots):
        x = sx + random(-30, 30)
        y = sy + random(-30, 30)
        dx = random(-0.4, 0.4)               # start slow -> ease into a calm drift
        dy = random(-0.4, 0.4)
        boids.append(Boid(x, y, dx, dy, name, rows, ts, palette, speed))

    # thin bendy seaweed rooted along the bottom, reaching ~1/3 up the tank
    seaweed.clear()
    for _ in range(9):
        seaweed.append({
            "x": random(WIDTH),
            "height": random(HEIGHT * 0.26, HEIGHT * 0.38),
            "segs": 16,
            "phase": random(TWO_PI),
            "amp": random(10, 22),           # how far the tip sways
            "speed": random(0.015, 0.03),    # sway rate
            "weight": random(2.0, 3.5),      # strand thickness
            "col": (random(25, 55), random(120, 190), random(70, 110)),  # greens
        })

    # a scattering of slow rising bubbles
    bubbles.clear()
    for _ in range(16):
        bubbles.append({
            "x": random(WIDTH),
            "y": random(HEIGHT),
            "r": random(2, 6),
            "speed": random(0.4, 1.2),       # upward drift
            "phase": random(TWO_PI),
            "wspeed": random(0.02, 0.06),    # horizontal wobble rate
            "wamp": random(0.5, 1.6),        # wobble width
        })

def draw_seaweed():
    """Thin bendy strands swaying from the tank floor."""
    no_fill()
    for s in seaweed:
        stroke(*s["col"])
        stroke_weight(s["weight"])
        n = s["segs"]
        pts = []
        for i in range(n + 1):
            t = i / n                         # 0 at the root, 1 at the tip
            y = HEIGHT - t * s["height"]
            # bend grows toward the tip (* t) for a rooted, seaweed-like sway
            sway = sin(tick * s["speed"] + s["phase"] + t * 3.0) * s["amp"] * t
            pts.append((s["x"] + sway, y))
        # connect the points as a smooth-enough bendy polyline
        for i in range(n):
            line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])


def draw_bubbles():
    """Faint bubbles drifting up, wobbling, and looping back to the floor."""
    no_fill()
    stroke_weight(1)
    stroke(180, 220, 255, 150)
    for b in bubbles:
        b["y"] -= b["speed"]
        if b["y"] < -10:                      # off the top -> respawn at the floor
            b["y"] = HEIGHT + random(10, 40)
            b["x"] = random(WIDTH)
        wob = sin(tick * b["wspeed"] + b["phase"]) * b["wamp"]
        circle(b["x"] + wob, b["y"], b["r"] * 2)


def draw():
    global tick
    tick += 1
    no_cursor()
    background(0)

    draw_seaweed()                            # behind the fish
    draw_bubbles()

    no_stroke()                               # fish glyphs are filled, not stroked
    for boid in boids:
        boid.apply_behaviors(boids)
        boid.limit_speed()
        boid.keep_in_bounds()
        boid.update()
        boid.show()


run_sketch()
