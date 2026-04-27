#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <Bluepad32.h>

static const int I2C_SDA_PIN = 21;
static const int I2C_SCL_PIN = 22;
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, I2C_SCL_PIN, I2C_SDA_PIN);

ControllerPtr controllers[BP32_MAX_GAMEPADS];

static const uint8_t DPAD_UP_MASK = 0x01;
static const uint8_t DPAD_DOWN_MASK = 0x02;
static const uint8_t DPAD_RIGHT_MASK = 0x04;
static const uint8_t DPAD_LEFT_MASK = 0x08;

struct InputState {
    bool left;
    bool right;
    bool up;
    bool down;
    bool a;
    bool b;
    bool x;
    bool y;
};

struct ButtonEdge {
    bool a;
    bool b;
    bool x;
    bool y;
};

enum Scene {
    SC_WAIT,
    SC_TITLE,
    SC_WORLD,
    SC_DIALOG,
    SC_INV,
    SC_END
};

enum TileType {
    T_ROAD = 0,
    T_WALL = 1,
    T_FLOWER = 2,
    T_GATE = 3
};

enum ItemId {
    IT_RED_RIBBON,
    IT_MILK_BOTTLE,
    IT_BELL,
    IT_WOODEN_SPOON,
    IT_CANDLE,
    IT_BLUE_SCARF,
    IT_POCKET_WATCH,
    IT_RAIN_UMBRELLA,
    IT_SILVER_THIMBLE,
    IT_HONEY_JAR,
    IT_FIDDLE_BOW,
    IT_BRASS_KEY,
    IT_FEATHER_QUILL,
    IT_MOON_COOKIE,
    IT_STAR_LANTERN,
    IT_SATIN_CROWN,
    IT_COUNT
};

struct NpcDef {
    const char* name;
    uint8_t tx;
    uint8_t ty;
    int8_t needItem;
    int8_t giveItem;
    const char* askText;
    const char* rhymeA;
    const char* rhymeB;
};

static const char* ITEM_NAMES[IT_COUNT] = {
    "RedRibbon", "MilkBottle", "Bell", "WoodSpoon",
    "Candle", "BlueScarf", "PocketWatch", "Umbrella",
    "Thimble", "HoneyJar", "FiddleBow", "BrassKey",
    "FeatherQuill", "MoonCookie", "StarLantern", "SatinCrown"
};

static const NpcDef NPCS[] = {
    {"BoPeep", 2, 1, IT_RED_RIBBON, IT_MILK_BOTTLE, "Bring ribbon, dear.", "Ribbon bright and neat,", "take this milk so sweet."},
    {"MilkMaid", 6, 1, IT_MILK_BOTTLE, IT_BELL, "Lost my milk today.", "Bottle back, worries fell,", "here's my copper bell."},
    {"Shepherd", 10, 1, IT_BELL, IT_WOODEN_SPOON, "Need a bell for flock.", "Meadow rings at noon,", "trade for wooden spoon."},
    {"Baker", 13, 1, IT_WOODEN_SPOON, IT_CANDLE, "No spoon for dough.", "Stir till dawn can handle,", "take a tallow candle."},
    {"NightWatch", 2, 3, IT_CANDLE, IT_BLUE_SCARF, "My post is dark.", "Candle cuts the wharf,", "keep this blue knit scarf."},
    {"Tailor", 5, 3, IT_BLUE_SCARF, IT_POCKET_WATCH, "Scarf for final stitch.", "Scarf of sky and notch,", "trade for pocket watch."},
    {"ClockMouse", 8, 3, IT_POCKET_WATCH, IT_RAIN_UMBRELLA, "Clockwork needs time.", "Tick and tock, umbrella,", "carry through the weather."},
    {"BridgeMan", 11, 3, IT_RAIN_UMBRELLA, IT_SILVER_THIMBLE, "Storm on my bridge.", "Rain and river quiver,", "take this thimble silver."},
    {"Seamstress", 13, 3, IT_SILVER_THIMBLE, IT_HONEY_JAR, "Thimble for gloves.", "Moonlit stitch by star,", "thank you, honey jar."},
    {"BeeKeeper", 2, 5, IT_HONEY_JAR, IT_FIDDLE_BOW, "Need my honey back.", "Honey glows at dawn,", "take this fiddle bow."},
    {"Fiddler", 5, 5, IT_FIDDLE_BOW, IT_BRASS_KEY, "Bow for evening song.", "Strings sing high and low,", "here's a brassy key."},
    {"GateGirl", 8, 5, IT_BRASS_KEY, IT_FEATHER_QUILL, "This gate is jammed.", "Hinges dance with thrill,", "trade for feather quill."},
    {"Poet", 10, 5, IT_FEATHER_QUILL, IT_MOON_COOKIE, "Quill for one last line.", "Write the windy brook,", "take this moonlit cookie."},
    {"Owl", 12, 5, IT_MOON_COOKIE, IT_STAR_LANTERN, "Midnight snack?", "Cookie gone by turn,", "owl gives star lantern."},
    {"LampKeep", 4, 4, IT_STAR_LANTERN, IT_SATIN_CROWN, "Light my square.", "Lantern high in town,", "now receive this crown."},
    {"Queen", 14, 4, IT_SATIN_CROWN, -1, "Bring me my crown.", "Crown returned with ring,", "nursery town now sings."}
};

static const uint8_t NPC_COUNT = sizeof(NPCS) / sizeof(NPCS[0]);

static const uint8_t MAP_W = 16;
static const uint8_t MAP_H = 7;
static const uint8_t TILE = 8;

static uint8_t worldMap[MAP_H][MAP_W] = {
    {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1},
    {1,0,0,2,0,0,0,2,0,0,0,2,0,0,0,1},
    {1,0,1,1,0,1,0,0,1,1,0,0,0,1,0,1},
    {1,0,0,0,0,0,0,2,0,0,0,2,0,0,0,1},
    {1,2,1,0,0,1,0,0,1,0,0,0,0,3,0,1},
    {1,0,0,0,2,0,0,2,0,0,1,0,0,0,0,1},
    {1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1},
};

static Scene scene = SC_WAIT;
static InputState prevInput = {false, false, false, false, false, false, false, false};

static int playerTx = 8;
static int playerTy = 3;
static int playerDir = 1;
static uint8_t playerStep = 0;

static uint32_t sceneStartMs = 0;
static uint32_t lastMoveMs = 0;
static uint32_t sparklePhase = 0;

static bool hasItem[IT_COUNT];
static bool npcDone[NPC_COUNT];
static uint8_t completedSteps = 0;
static uint8_t invCursor = 0;

static int activeNpc = -1;
static char dialogLine1[24] = "";
static char dialogLine2[24] = "";
static char dialogLine3[24] = "";
static char hintLine[24] = "";
static uint32_t hintUntil = 0;

int clampInt(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

void setScene(Scene s) {
    scene = s;
    sceneStartMs = millis();
}

void setHint(const char* txt, uint16_t ms) {
    strncpy(hintLine, txt, sizeof(hintLine) - 1);
    hintLine[sizeof(hintLine) - 1] = '\0';
    hintUntil = millis() + ms;
}

ControllerPtr activeController() {
    for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
        if (controllers[i] && controllers[i]->isConnected()) {
            return controllers[i];
        }
    }
    return nullptr;
}

void onConnectedController(ControllerPtr ctl) {
    for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
        if (!controllers[i]) {
            controllers[i] = ctl;
            Serial.printf("Controller connected on slot %d\n", i);
            return;
        }
    }
}

void onDisconnectedController(ControllerPtr ctl) {
    for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
        if (controllers[i] == ctl) {
            controllers[i] = nullptr;
            return;
        }
    }
}

InputState readInput() {
    InputState in = {false, false, false, false, false, false, false, false};
    ControllerPtr ctl = activeController();
    if (!ctl) return in;

    uint8_t d = ctl->dpad();
    in.left = (d & DPAD_LEFT_MASK) != 0;
    in.right = (d & DPAD_RIGHT_MASK) != 0;
    in.up = (d & DPAD_UP_MASK) != 0;
    in.down = (d & DPAD_DOWN_MASK) != 0;
    in.a = ctl->a();
    in.b = ctl->b();
    in.x = ctl->x();
    in.y = ctl->y();
    return in;
}

ButtonEdge readEdges(const InputState& in) {
    ButtonEdge e;
    e.a = in.a && !prevInput.a;
    e.b = in.b && !prevInput.b;
    e.x = in.x && !prevInput.x;
    e.y = in.y && !prevInput.y;
    prevInput = in;
    return e;
}

void setDialog3(const char* l1, const char* l2, const char* l3) {
    strncpy(dialogLine1, l1, sizeof(dialogLine1) - 1);
    dialogLine1[sizeof(dialogLine1) - 1] = '\0';
    strncpy(dialogLine2, l2, sizeof(dialogLine2) - 1);
    dialogLine2[sizeof(dialogLine2) - 1] = '\0';
    strncpy(dialogLine3, l3, sizeof(dialogLine3) - 1);
    dialogLine3[sizeof(dialogLine3) - 1] = '\0';
}

void resetGame() {
    for (int i = 0; i < IT_COUNT; i++) {
        hasItem[i] = false;
    }
    for (int i = 0; i < NPC_COUNT; i++) {
        npcDone[i] = false;
    }

    hasItem[IT_RED_RIBBON] = true;
    completedSteps = 0;
    invCursor = 0;
    playerTx = 8;
    playerTy = 3;
    playerDir = 1;
    playerStep = 0;
    activeNpc = -1;
}

void drawCentered(const char* txt, int y) {
    int w = u8g2.getStrWidth(txt);
    u8g2.drawStr((128 - w) / 2, y, txt);
}

void drawHud() {
    char line[24];
    u8g2.setFont(u8g2_font_5x7_tf);
    snprintf(line, sizeof(line), "QUEST:%u/16", completedSteps);
    u8g2.drawStr(1, 7, line);

    int count = 0;
    for (int i = 0; i < IT_COUNT; i++) {
        if (hasItem[i]) count++;
    }
    snprintf(line, sizeof(line), "BAG:%d", count);
    u8g2.drawStr(84, 7, line);
}

void drawWait() {
    static bool blink = false;
    static uint32_t blinkMs = 0;
    if (millis() - blinkMs > 350) {
        blink = !blink;
        blinkMs = millis();
    }

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x12_tf);
    drawCentered("MOTHER GOOSE", 22);
    u8g2.setFont(u8g2_font_5x7_tf);
    drawCentered("Pair Xbox Controller", 38);
    if (blink) drawCentered("PAIRING...", 56);
    u8g2.sendBuffer();
}

void drawTitle(const ButtonEdge& edge) {
    uint32_t t = millis() - sceneStartMs;

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x12_tf);
    drawCentered("MOTHER GOOSE", 18);

    for (int i = 0; i < 22; i++) {
        int px = (i * 17 + (t / (3 + (i % 3)))) % 128;
        int py = (i * 11 + (t / (4 + (i % 2)))) % 28;
        u8g2.drawPixel(px, py);
    }

    u8g2.setFont(u8g2_font_5x7_tf);
    drawCentered("16 Delivery Rhymes", 36);
    drawCentered("A Start  X Inventory", 48);
    drawCentered("B New Run", 58);
    u8g2.sendBuffer();

    if (edge.a) setScene(SC_WORLD);
    if (edge.x) setScene(SC_INV);
    if (edge.b) resetGame();
}

void drawTile(uint8_t t, int x, int y, uint8_t phase) {
    if (t == T_WALL) {
        u8g2.drawBox(x, y, TILE, TILE);
        u8g2.drawPixel(x + 1 + (phase % 2), y + 1);
        u8g2.drawPixel(x + 5, y + 5);
    } else if (t == T_FLOWER) {
        u8g2.drawFrame(x, y, TILE, TILE);
        u8g2.drawPixel(x + 4, y + 2);
        u8g2.drawPixel(x + 2, y + 5);
        u8g2.drawPixel(x + 6, y + 5);
    } else if (t == T_GATE) {
        u8g2.drawRFrame(x, y, TILE, TILE, 1);
        u8g2.drawVLine(x + 4, y + 1, 6);
        u8g2.drawPixel(x + 2, y + 3);
        u8g2.drawPixel(x + 6, y + 3);
    } else {
        if ((x / 8 + y / 8 + phase) % 3 == 0) {
            u8g2.drawPixel(x + 1, y + 6);
        }
    }
}

void drawNpcSprite(uint8_t idx, int x, int y, uint32_t t) {
    int mode = idx % 4;
    int bob = ((t / 180 + idx) % 2 == 0) ? 0 : 1;
    int oy = y + bob;

    u8g2.drawRFrame(x + 1, oy + 1, 6, 6, 1);

    if (mode == 0) {
        int blink = ((t / 280 + idx) % 4 == 0) ? 0 : 1;
        if (blink) {
            u8g2.drawPixel(x + 3, oy + 2);
            u8g2.drawPixel(x + 5, oy + 2);
        } else {
            u8g2.drawHLine(x + 3, oy + 2, 1);
            u8g2.drawHLine(x + 5, oy + 2, 1);
        }
        u8g2.drawHLine(x + 2, oy + 5, 4);
    } else if (mode == 1) {
        int arm = ((t / 120 + idx) % 2 == 0) ? 0 : 1;
        u8g2.drawPixel(x + 3, oy + 2);
        u8g2.drawPixel(x + 5, oy + 2);
        u8g2.drawHLine(x + 2, oy + 5, 4);
        u8g2.drawLine(x, oy + 3, x + 1, oy + (arm ? 1 : 5));
        u8g2.drawLine(x + 7, oy + 3, x + 8, oy + (arm ? 5 : 1));
    } else if (mode == 2) {
        int hat = ((t / 160 + idx) % 3);
        u8g2.drawPixel(x + 3, oy + 2);
        u8g2.drawPixel(x + 5, oy + 2);
        u8g2.drawHLine(x + 2, oy + 5, 4);
        u8g2.drawHLine(x + 1, oy, 6);
        u8g2.drawPixel(x + 2 + hat, oy - 1);
    } else {
        int spark = (t / 90 + idx) % 6;
        u8g2.drawPixel(x + 3, oy + 2);
        u8g2.drawPixel(x + 5, oy + 2);
        u8g2.drawHLine(x + 2, oy + 5, 4);
        u8g2.drawPixel(x + (spark % 3), oy + (spark / 3));
        u8g2.drawPixel(x + 7 - (spark % 3), oy + (spark / 3));
    }
}

int findNpcNearPlayer() {
    for (int i = 0; i < NPC_COUNT; i++) {
        int dx = abs(playerTx - NPCS[i].tx);
        int dy = abs(playerTy - NPCS[i].ty);
        if (dx + dy <= 1) {
            return i;
        }
    }
    return -1;
}

int findObjectiveNpc() {
    int fallback = -1;
    for (int i = 0; i < NPC_COUNT; i++) {
        if (!npcDone[i]) {
            if (fallback < 0) fallback = i;
            int need = NPCS[i].needItem;
            if (need < 0 || hasItem[need]) {
                return i;
            }
        }
    }
    return fallback;
}

bool findNextStepTowards(int targetTx, int targetTy, int* outTx, int* outTy) {
    const int total = MAP_W * MAP_H;
    int qx[total];
    int qy[total];
    int head = 0;
    int tail = 0;

    bool visited[MAP_H][MAP_W];
    int parentX[MAP_H][MAP_W];
    int parentY[MAP_H][MAP_W];

    for (int y = 0; y < MAP_H; y++) {
        for (int x = 0; x < MAP_W; x++) {
            visited[y][x] = false;
            parentX[y][x] = -1;
            parentY[y][x] = -1;
        }
    }

    visited[playerTy][playerTx] = true;
    qx[tail] = playerTx;
    qy[tail] = playerTy;
    tail++;

    const int dx[4] = {1, -1, 0, 0};
    const int dy[4] = {0, 0, 1, -1};

    while (head < tail) {
        int cx = qx[head];
        int cy = qy[head];
        head++;

        if (cx == targetTx && cy == targetTy) {
            int rx = cx;
            int ry = cy;
            while (!(parentX[ry][rx] == playerTx && parentY[ry][rx] == playerTy)) {
                int px = parentX[ry][rx];
                int py = parentY[ry][rx];
                if (px < 0 || py < 0) break;
                rx = px;
                ry = py;
            }
            *outTx = rx;
            *outTy = ry;
            return true;
        }

        for (int i = 0; i < 4; i++) {
            int nx = cx + dx[i];
            int ny = cy + dy[i];
            if (nx < 0 || ny < 0 || nx >= MAP_W || ny >= MAP_H) continue;
            if (visited[ny][nx]) continue;
            if (worldMap[ny][nx] == T_WALL) continue;
            visited[ny][nx] = true;
            parentX[ny][nx] = cx;
            parentY[ny][nx] = cy;
            qx[tail] = nx;
            qy[tail] = ny;
            tail++;
        }
    }

    return false;
}

void useHintStep() {
    int objective = findObjectiveNpc();
    if (objective < 0) {
        setHint("Everything done!", 1000);
        return;
    }

    int nextTx = playerTx;
    int nextTy = playerTy;
    if (findNextStepTowards(NPCS[objective].tx, NPCS[objective].ty, &nextTx, &nextTy)) {
        if (nextTx != playerTx || nextTy != playerTy) {
            if (nextTx > playerTx) playerDir = 1;
            if (nextTx < playerTx) playerDir = -1;
            playerStep ^= 1;
            playerTx = nextTx;
            playerTy = nextTy;
            lastMoveMs = millis();
        }
        char line[24];
        snprintf(line, sizeof(line), "Hint -> %s", NPCS[objective].name);
        setHint(line, 1000);
    } else {
        setHint("No route found", 1000);
    }
}

void openNpcDialog(int idx) {
    activeNpc = idx;
    const NpcDef& n = NPCS[idx];

    if (npcDone[idx]) {
        setDialog3(n.name, "Delivery complete.", "Thank you again.");
        setScene(SC_DIALOG);
        return;
    }

    if (n.needItem >= 0 && !hasItem[n.needItem]) {
        setDialog3(n.name, n.askText, "Bring the right item.");
        setScene(SC_DIALOG);
        return;
    }

    if (n.needItem >= 0) {
        hasItem[n.needItem] = false;
    }
    if (n.giveItem >= 0) {
        hasItem[n.giveItem] = true;
    }

    npcDone[idx] = true;
    completedSteps = clampInt(completedSteps + 1, 0, 16);
    setDialog3(n.name, n.rhymeA, n.rhymeB);

    if (completedSteps >= 16) {
        setScene(SC_END);
        return;
    }

    setScene(SC_DIALOG);
}

void handleWorldMovement(const InputState& in) {
    uint32_t now = millis();
    if (now - lastMoveMs < 120) return;

    int nx = playerTx;
    int ny = playerTy;

    if (in.left && !in.right) {
        nx--;
        playerDir = -1;
    }
    if (in.right && !in.left) {
        nx++;
        playerDir = 1;
    }
    if (in.up && !in.down) ny--;
    if (in.down && !in.up) ny++;

    nx = clampInt(nx, 0, MAP_W - 1);
    ny = clampInt(ny, 0, MAP_H - 1);

    if (worldMap[ny][nx] != T_WALL && (nx != playerTx || ny != playerTy)) {
        playerTx = nx;
        playerTy = ny;
        playerStep ^= 1;
        lastMoveMs = now;
    }
}

void drawPlayerSprite(int x, int y, uint32_t t) {
    int bob = ((t / 180) % 2 == 0) ? 0 : 1;
    int py = y + bob;

    u8g2.drawRFrame(x, py, TILE, TILE, 1);
    u8g2.drawDisc(x + 4, py + 2, 2);
    u8g2.drawBox(x + 3, py + 4, 3, 2);

    if (playerStep == 0) {
        u8g2.drawPixel(x + 3, py + 7);
        u8g2.drawPixel(x + 5, py + 6);
    } else {
        u8g2.drawPixel(x + 3, py + 6);
        u8g2.drawPixel(x + 5, py + 7);
    }

    if (playerDir > 0) {
        u8g2.drawPixel(x + 5, py + 2);
    } else {
        u8g2.drawPixel(x + 3, py + 2);
    }
}

void drawPortraitForNpc(int npcIndex, int x, int y, uint32_t t) {
    u8g2.drawRFrame(x, y, 20, 20, 2);
    if (npcIndex < 0 || npcIndex >= NPC_COUNT) {
        u8g2.drawDisc(x + 10, y + 8, 4);
        u8g2.drawHLine(x + 6, y + 14, 8);
        return;
    }

    int mode = npcIndex % 4;
    int bob = ((t / 200 + npcIndex) % 2 == 0) ? 0 : 1;
    int px = x + 4;
    int py = y + 3 + bob;

    u8g2.drawRFrame(px, py, 12, 12, 2);
    u8g2.drawDisc(px + 4, py + 4, 1);
    u8g2.drawDisc(px + 8, py + 4, 1);
    u8g2.drawHLine(px + 3, py + 8, 6);

    if (mode == 1) {
        u8g2.drawLine(px - 2, py + 5, px, py + 3);
        u8g2.drawLine(px + 12, py + 5, px + 14, py + 7);
    } else if (mode == 2) {
        u8g2.drawHLine(px + 2, py - 2, 8);
        u8g2.drawPixel(px + 6, py - 3);
    } else if (mode == 3) {
        int s = (t / 120) % 3;
        u8g2.drawPixel(px + s, py + 1);
        u8g2.drawPixel(px + 11 - s, py + 1);
    }
}

void drawWorld(const InputState& in, const ButtonEdge& edge) {
    if (edge.x) {
        setScene(SC_INV);
        return;
    }

    if (edge.y) {
        useHintStep();
    } else {
        handleWorldMovement(in);
    }

    sparklePhase = (millis() / 180) % 8;
    u8g2.clearBuffer();
    drawHud();

    for (int y = 0; y < MAP_H; y++) {
        for (int x = 0; x < MAP_W; x++) {
            drawTile(worldMap[y][x], x * TILE, 10 + y * TILE, sparklePhase);
        }
    }

    uint32_t t = millis();
    for (int i = 0; i < NPC_COUNT; i++) {
        int nx = NPCS[i].tx * TILE;
        int ny = 10 + NPCS[i].ty * TILE;
        drawNpcSprite(i, nx, ny, t);
        if (npcDone[i]) {
            u8g2.drawPixel(nx + 7, ny);
            u8g2.drawPixel(nx + 7, ny + 1);
        }
    }

    int px = playerTx * TILE;
    int py = 10 + playerTy * TILE;
    drawPlayerSprite(px, py, t);

    int nearNpc = findNpcNearPlayer();
    if (nearNpc >= 0) {
        int nx = NPCS[nearNpc].tx * TILE;
        int ny = 10 + NPCS[nearNpc].ty * TILE;
        u8g2.drawCircle(nx + 4, ny - 1, 1);
    }

    u8g2.setFont(u8g2_font_5x7_tf);
    if (millis() < hintUntil) {
        u8g2.drawStr(1, 63, hintLine);
    } else {
        u8g2.drawStr(1, 63, "A talk X bag Y hint");
    }
    u8g2.sendBuffer();

    if (edge.a) {
        if (nearNpc >= 0) {
            openNpcDialog(nearNpc);
        } else {
            activeNpc = -1;
            setDialog3("Sjors", "Nobody nearby.", "Find receiver.");
            setScene(SC_DIALOG);
        }
    }
}

void drawDialog(const ButtonEdge& edge) {
    u8g2.clearBuffer();
    drawHud();

    u8g2.drawRFrame(3, 13, 122, 44, 2);
    drawPortraitForNpc(activeNpc, 8, 18, millis());

    u8g2.setFont(u8g2_font_6x12_tf);
    u8g2.drawStr(32, 27, dialogLine1);
    u8g2.setFont(u8g2_font_5x7_tf);
    u8g2.drawStr(32, 39, dialogLine2);
    u8g2.drawStr(32, 48, dialogLine3);
    u8g2.drawStr(32, 56, "A/B back");
    u8g2.sendBuffer();

    if (edge.a || edge.b) {
        if (completedSteps >= 16) {
            setScene(SC_END);
        } else {
            setScene(SC_WORLD);
        }
    }
}

void drawInventory(const InputState& in, const ButtonEdge& edge) {
    if (in.up && !in.down && millis() - lastMoveMs > 120) {
        invCursor = (invCursor + IT_COUNT - 1) % IT_COUNT;
        lastMoveMs = millis();
    }
    if (in.down && !in.up && millis() - lastMoveMs > 120) {
        invCursor = (invCursor + 1) % IT_COUNT;
        lastMoveMs = millis();
    }

    u8g2.clearBuffer();
    drawHud();

    u8g2.setFont(u8g2_font_6x12_tf);
    u8g2.drawStr(4, 20, "INVENTORY");
    u8g2.setFont(u8g2_font_5x7_tf);

    const int visibleRows = 5;
    int start = invCursor - (visibleRows / 2);
    if (start < 0) start = 0;
    if (start > IT_COUNT - visibleRows) start = IT_COUNT - visibleRows;

    for (int i = 0; i < visibleRows; i++) {
        int itemIndex = start + i;
        int y = 30 + i * 7;
        if (itemIndex == invCursor) {
            u8g2.drawStr(1, y, ">");
        }
        char line[24];
        snprintf(line, sizeof(line), "%s %s", ITEM_NAMES[itemIndex], hasItem[itemIndex] ? "yes" : "--");
        u8g2.drawStr(8, y, line);
    }

    u8g2.drawStr(1, 63, "B back");
    u8g2.sendBuffer();

    if (edge.b || edge.x) {
        setScene(SC_WORLD);
    }
}

void drawEnd(const ButtonEdge& edge) {
    uint32_t t = millis() - sceneStartMs;

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x12_tf);
    drawCentered("ALL DELIVERED", 18);

    for (int i = 0; i < 30; i++) {
        int px = (i * 9 + (t / (2 + (i % 3)))) % 128;
        int py = 20 + ((i * 7 + (t / 8)) % 40);
        u8g2.drawPixel(px, py);
    }

    u8g2.setFont(u8g2_font_5x7_tf);
    drawCentered("Sixteen rhymes complete", 38);
    drawCentered("Town is glowing", 48);
    drawCentered("A/B restart", 60);
    u8g2.sendBuffer();

    if (edge.a || edge.b) {
        resetGame();
        setScene(SC_TITLE);
    }
}

void setup() {
    Serial.begin(115200);
    delay(150);

    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    u8g2.begin();

    BP32.setup(&onConnectedController, &onDisconnectedController);
    BP32.forgetBluetoothKeys();

    randomSeed(esp_random());
    resetGame();
    setScene(SC_WAIT);
}

void loop() {
    BP32.update();

    InputState in = readInput();
    ButtonEdge edge = readEdges(in);

    if (!activeController()) {
        setScene(SC_WAIT);
        drawWait();
        delay(16);
        return;
    }

    if (scene == SC_WAIT) {
        setScene(SC_TITLE);
    }

    switch (scene) {
        case SC_TITLE:
            drawTitle(edge);
            break;
        case SC_WORLD:
            drawWorld(in, edge);
            break;
        case SC_DIALOG:
            drawDialog(edge);
            break;
        case SC_INV:
            drawInventory(in, edge);
            break;
        case SC_END:
            drawEnd(edge);
            break;
        default:
            drawWait();
            break;
    }

    delay(16);
}
