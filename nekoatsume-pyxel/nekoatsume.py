"""
ねこあつめ Pyxel 版(文字だけの UI)

    実行:  pyxel run nekoatsume.py      (または python nekoatsume.py)
    Web :  https://kitao.github.io/pyxel/wasm/launcher/?run=<ユーザー名>.<リポジトリ名>.nekoatsume

操作は「タップ / クリック」が基本。リストはドラッグ(ホイール・↑↓キーも可)でスクロール。
1〜5 キーで下のタブを切り替えられる。ゲームのルールは game.py にある。
"""

import os
import time

import pyxel

import game

# ===== 設定 =====
SCREEN_W = 256
SCREEN_H = 256
FONT_PATH = "PixelMplus12-Regular.ttf" #"PixelMplus10-Regular.ttf"
FONT_SIZE = 12
VENDOR = "Neko-Kuroi"          # セーブ先(user_data_dir)に使う名前
APP_NAME = "nekoatsume-pyxel"
SAVE_NAME = "save.json"

HEADER_H = 18
TAB_Y = 230
TAB_H = SCREEN_H - TAB_Y
ROW_H = 16
LOG_MAX = 30
TOAST_FRAMES = 75              # 30fps で約2.5秒

# パレット(Pyxel 標準 16 色)
C_BG, C_PANEL, C_TEXT, C_SUB, C_DIM = 0, 1, 7, 6, 13
C_ACCENT, C_GOOD, C_BAD, C_SILVER, C_GOLD = 10, 11, 8, 6, 10

TABS = [("yard", "にわ"), ("shop", "ショップ"), ("bag", "もちもの"), ("cats", "おたから"), ("help", "ヘルプ")]

HELP_LINES = [
    "ねこあつめへようこそ!",
    "",
    "1. ショップでおもちゃとエサを買う",
    "2. もちものから、おもちゃを庭に置き、エサも置く",
    "3. 猫が遊びに来て、帰るときにさかなを置いていく",
    "4. 「にわ」でさかなを受け取る",
    "",
    "エサは300分(5時間)でなくなります。アプリを閉じている間も時間は進みます。",
    "エサがないと、猫は来ません。",
    "",
    "猫の累計滞在が3000分を超えると、お宝を持ってくることがあります。",
]


NO_LINE_START = "。、,.!?:;)]」』)…ー・!?"


def fish_text(amount, cur):
    return "{0}のさかな{1}匹".format(game.cur_name(cur), amount)


def event_text(ev):
    kind = ev[0]
    if kind == "arrive":
        return "{0}が{1}で遊び始めた".format(game.CATS[ev[1]]["name"], game.TOYS[ev[2]]["name"])
    if kind == "leave":
        return "{0}が帰った(+{1}{2})".format(game.CATS[ev[1]]["name"], game.cur_name(ev[4]), ev[3])
    if kind == "treasure":
        return "{0}がお宝を置いていった!".format(game.CATS[ev[1]]["name"])
    if kind == "food_out":
        return "エサがなくなった"
    return ""


class Typewriter:
    """1文字ずつ表示するための小さな状態機械。

    aozora_reader.py(kanekofumiko)の演出を移植したもの。
    表示する文字列はあらかじめ折り返し済み("\\n" 区切り)で渡す前提で、
    改行はコマ数を消費せずに読み飛ばす。
    """
    INTERVAL = 2   # 1文字ごとのフレーム数(30fpsで秒間15文字ほど)

    def __init__(self):
        self.text = ""
        self.revealed = 0
        self.timer = 0
        self.done = True

    def set_text(self, text):
        if text == self.text:
            return
        self.text = text
        self.revealed = 0
        self.timer = 0
        self.done = len(text) == 0

    def skip(self):
        self.revealed = len(self.text)
        self.done = True

    def update(self, on_char=None):
        if self.done:
            return
        self.timer += 1
        if self.timer < self.INTERVAL:
            return
        self.timer = 0
        while self.revealed < len(self.text) and self.text[self.revealed] == "\n":
            self.revealed += 1
        if self.revealed < len(self.text):
            ch = self.text[self.revealed]
            self.revealed += 1
            if on_char:
                on_char(ch)
        if self.revealed >= len(self.text):
            self.done = True

    @property
    def visible(self):
        return self.text[:self.revealed]


class App:
    def __init__(self, run=True):
        pyxel.init(SCREEN_W, SCREEN_H, title="ねこあつめ", fps=30)
        pyxel.mouse(True)
        self.font = pyxel.Font(FONT_PATH, FONT_SIZE) if os.path.exists(FONT_PATH) else None
        self.clock = time.time

        # 画面の状態
        self.screen = "yard"
        self.sub = {"shop": 0, "bag": 0}       # 0=おもちゃ 1=エサ
        self.selected = {"shop": None, "cats": None}
        self.scroll = {}
        self.log = []                          # [{"full": 折り返し済みテキスト, "revealed": int}]
        self.log_timer = 0
        self.toast = None                      # {"col":..., "frames":...}
        self.toast_tw = Typewriter()
        self.panel_tw = Typewriter()
        self.panel_key = None                  # 図鑑パネルの再生アニメが必要かの判定用
        self.panel_colors = []
        self.modal = None                      # {"text":..., "yes": fn}
        self.hits = []
        self.areas = []
        self.press = None
        self._init_sound()

        self._init_save()
        self.state = self._load()
        self._on_launch()

        if run:
            pyxel.run(self.update, self.draw)

    # ------------------------------------------------------------ 音
    def _init_sound(self):
        """一文字ずつ表示するときの生成サウンド(aozora_reader.py の演出を移植)。"""
        self.snd_talk = pyxel.Sound()
        self.snd_talk.set("c3", "t", "2", "n", 1)
        self.snd_talk_space = pyxel.Sound()
        self.snd_talk_space.set("c3", "t", "3", "n", 1)

    def _play_type_sound(self, ch):
        pyxel.play(3, self.snd_talk_space if ch.isspace() else self.snd_talk)

    # ------------------------------------------------------------ 保存
    def _init_save(self):
        self.save_path = None
        try:
            base = os.environ.get("NEKOATSUME_SAVE_DIR") or pyxel.user_data_dir(VENDOR, APP_NAME)
            os.makedirs(base, exist_ok=True)
            self.save_path = os.path.join(base, SAVE_NAME)
        except Exception:
            self.save_path = None

    def _load(self):
        now = self.clock()
        self.startup_notice = ""
        if self.save_path and os.path.exists(self.save_path):
            try:
                with open(self.save_path, encoding="utf-8") as f:
                    return game.loads(f.read(), now)
            except Exception:
                try:
                    os.replace(self.save_path, self.save_path + ".bad")
                except OSError:
                    pass
                self.startup_notice = "セーブデータが読めなかったので、新しく始めます"
        return game.new_state(now)

    def save(self):
        if not self.save_path:
            return
        try:
            tmp = self.save_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(game.dumps(self.state))
            os.replace(tmp, self.save_path)
        except OSError:
            self.save_path = None
            self.show_toast("セーブできませんでした", C_BAD)

    def _on_launch(self):
        rep = game.resume(self.state, self.clock())
        if self.startup_notice:
            self.show_toast(self.startup_notice, C_BAD)
        if rep["ticks"] >= 2:
            self.add_log("離れていた間に{0}分たちました。猫が{1}回遊びに来たよ".format(rep["ticks"], rep["visits"]))
        if rep["bonus_treasure"]:
            self.add_log("{0}がお宝を持ってきた!".format(game.CATS[rep["bonus_treasure"]]["name"]))
        self._notice_pending()
        self.save()

    def _notice_pending(self):
        if self.state["pending_money"] or self.state["pending_treasures"]:
            self.show_toast("さかなやお宝が届いています。「にわ」で受け取ろう", C_ACCENT)

    # ------------------------------------------------------------ 文字の補助
    def tw(self, s):
        return self.font.text_width(s) if self.font else len(s) * pyxel.FONT_WIDTH

    def tx(self, x, y, s, col=C_TEXT):
        pyxel.text(x, y, s, col, self.font)

    def tx_right(self, right_x, y, s, col=C_TEXT):
        self.tx(right_x - self.tw(s), y, s, col)

    def fit(self, s, max_w, fallback=None):
        if self.tw(s) <= max_w:
            return s
        return fallback if fallback is not None else s[:max(1, len(s) * max_w // max(1, self.tw(s)) - 1)] + "…"

    def wrap(self, s, max_w):
        lines = []
        for para in s.split("\n"):
            line = ""
            for ch in para:
                if self.tw(line + ch) > max_w and line and ch not in NO_LINE_START:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
            lines.append(line)
        return lines

    def add_log(self, text):
        full = "\n".join(self.wrap(text, SCREEN_W - 20))
        self.log.append({"full": full, "revealed": 0})
        self.log = self.log[-LOG_MAX:]

    def _advance_log_typing(self):
        """一番古い「まだ出し終えていない」できごとだけを、1文字ずつ進める(順番に表示される)。"""
        for entry in self.log:
            if entry["revealed"] >= len(entry["full"]):
                continue
            self.log_timer += 1
            if self.log_timer >= Typewriter.INTERVAL:
                self.log_timer = 0
                full = entry["full"]
                while entry["revealed"] < len(full) and full[entry["revealed"]] == "\n":
                    entry["revealed"] += 1
                if entry["revealed"] < len(full):
                    ch = full[entry["revealed"]]
                    entry["revealed"] += 1
                    self._play_type_sound(ch)
            break

    def _log_typing(self):
        return any(e["revealed"] < len(e["full"]) for e in self.log)

    def _skip_log(self):
        for e in self.log:
            e["revealed"] = len(e["full"])

    def visible_log(self, max_lines):
        """新しい順に、行数に収まる分だけ「一文まるごと」取り出す(途中で切れた文は出さない)。
        まだ表示の順番が回ってきていない(revealed==0)できごとは出さない。"""
        out = []
        for entry in reversed(self.log):
            if entry["revealed"] == 0:
                continue
            lines = entry["full"][:entry["revealed"]].split("\n")
            if len(out) + len(lines) > max_lines:
                break
            out = lines + out
        return out

    def show_toast(self, text, col=C_TEXT):
        self.toast = {"col": col, "frames": TOAST_FRAMES}
        self.toast_tw.set_text("\n".join(self.wrap(text, SCREEN_W - 24)))

    # ------------------------------------------------------------ 入力
    def _pointer(self):
        """(x, y, 押した瞬間, 押している, 離した瞬間, ホイール)。テストでは差し替える。"""
        return (pyxel.mouse_x, pyxel.mouse_y,
                pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT), pyxel.btn(pyxel.MOUSE_BUTTON_LEFT),
                pyxel.btnr(pyxel.MOUSE_BUTTON_LEFT), pyxel.mouse_wheel)

    def _keys(self):
        """キーボード入力(押した瞬間の集合)。テストでは差し替える。"""
        keys = set()
        for name in ("KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_UP", "KEY_DOWN"):
            if pyxel.btnp(getattr(pyxel, name)):
                keys.add(name)
        return keys

    def _area_at(self, x, y):
        for area in reversed(self.areas):
            _key, ax, ay, aw, ah, _maxs = area
            if ax <= x < ax + aw and ay <= y < ay + ah:
                return area
        return None

    def _scroll_by(self, area, dy):
        key, _ax, _ay, _aw, _ah, maxs = area
        self.scroll[key] = min(max(self.scroll.get(key, 0) + dy, 0), maxs)

    def handle_input(self):
        mx, my, pressed, held, released, wheel = self._pointer()
        if pressed:
            area = self._area_at(mx, my)
            self.press = {"y": my, "area": area, "off": self.scroll.get(area[0], 0) if area else 0, "moved": False}
        elif self.press and held and self.press["area"]:
            p = self.press
            if p["moved"] or abs(my - p["y"]) > 4:
                p["moved"] = True
                key, _ax, _ay, _aw, _ah, maxs = p["area"]
                self.scroll[key] = min(max(p["off"] + p["y"] - my, 0), maxs)
        if released and self.press:
            moved = self.press["moved"]
            self.press = None
            if not moved:
                if self._typing_active():
                    self._skip_typing()
                else:
                    self.tap(mx, my)
        if wheel:
            area = self._area_at(mx, my)
            if area:
                self._scroll_by(area, -wheel * ROW_H)

        keys = self._keys()
        for i, (name, _label) in enumerate(TABS):
            if "KEY_%d" % (i + 1) in keys:
                self.goto(name)
        if self.areas and ("KEY_UP" in keys or "KEY_DOWN" in keys):
            self._scroll_by(self.areas[0], -ROW_H if "KEY_UP" in keys else ROW_H)

    def tap(self, x, y):
        for hx, hy, hw, hh, fn, clip in reversed(self.hits):
            if hx <= x < hx + hw and hy <= y < hy + hh:
                if clip and not (clip[0] <= x < clip[0] + clip[2] and clip[1] <= y < clip[1] + clip[3]):
                    continue
                fn()
                return

    def goto(self, name):
        if name != self.screen:
            self.screen = name
            self.hits, self.areas, self.press = [], [], None

    # ------------------------------------------------------------ 一文字ずつ表示(タイプライター)
    def _typing_active(self):
        return self._log_typing() or not self.toast_tw.done or not self.panel_tw.done

    def _skip_typing(self):
        self._skip_log()
        self.toast_tw.skip()
        self.panel_tw.skip()

    # ------------------------------------------------------------ 更新
    def update(self):
        rep = game.advance(self.state, self.clock())
        if rep["ticks"]:
            if rep["ticks"] <= 3:
                for ev in rep["events"]:
                    self.add_log(event_text(ev))
            else:
                self.add_log("{0}分たちました。猫が{1}回遊びに来たよ".format(rep["ticks"], rep["visits"]))
            self.save()
        self.handle_input()
        self._advance_log_typing()
        self.toast_tw.update(self._play_type_sound)
        self.panel_tw.update(self._play_type_sound)
        if self.toast:
            if self.toast_tw.done:
                self.toast["frames"] -= 1
                if self.toast["frames"] <= 0:
                    self.toast = None

    # ------------------------------------------------------------ 描画の部品
    def hit(self, x, y, w, h, fn, clip=None):
        self.hits.append((x, y, w, h, fn, clip))

    def button(self, x, y, w, h, label, fn, enabled=True, active=False, clip=None):
        fill = C_PANEL if not active else C_DIM
        pyxel.rect(x, y, w, h, fill)
        pyxel.rectb(x, y, w, h, C_ACCENT if active else C_DIM)
        col = C_TEXT if enabled else C_DIM
        tw = self.tw(label)
        self.tx(x + (w - tw) // 2, y + (h - FONT_SIZE) // 2, label, col)
        self.hit(x, y, w, h, fn, clip)

    def list_view(self, key, x, y, w, h, n, draw_row):
        maxs = max(0, n * ROW_H - h)
        off = min(max(self.scroll.get(key, 0), 0), maxs)
        self.scroll[key] = off
        self.areas.append((key, x, y, w, h, maxs))
        pyxel.clip(x, y, w, h)
        first = int(off // ROW_H)
        for i in range(first, min(n, first + h // ROW_H + 2)):
            draw_row(i, y + i * ROW_H - int(off), (x, y, w, h))
        pyxel.clip()
        if maxs > 0:
            bar_h = max(8, h * h // (n * ROW_H))
            bar_y = y + (h - bar_h) * off // maxs
            pyxel.rect(x + w - 2, int(bar_y), 2, bar_h, C_DIM)

    def draw_panel(self, x, y, w, h):
        pyxel.rect(x, y, w, h, C_PANEL)
        pyxel.rectb(x, y, w, h, C_DIM)

    # ------------------------------------------------------------ 描画
    def draw(self):
        self.hits, self.areas = [], []
        pyxel.cls(C_BG)
        self.draw_header()
        getattr(self, "draw_" + self.screen)()
        self.draw_tabs()
        if self.toast:
            self.draw_toast()
        if self.modal:
            self.draw_modal()

    def draw_header(self):
        s = self.state
        pyxel.rect(0, 0, SCREEN_W, HEADER_H, C_PANEL)
        self.tx(6, 3, "銀 {0}".format(s["s_fish"]), C_SILVER)
        self.tx(76, 3, "金 {0}".format(s["g_fish"]), C_GOLD)
        title = dict(TABS)[self.screen]
        self.tx_right(SCREEN_W - 6, 3, title, C_SUB)

    def draw_tabs(self):
        w = SCREEN_W // len(TABS)
        pending = bool(self.state["pending_money"] or self.state["pending_treasures"])
        for i, (name, label) in enumerate(TABS):
            self.button(i * w, TAB_Y, w, TAB_H, label, lambda n=name: self.goto(n), active=(name == self.screen))
            if name == "yard" and pending and self.screen != "yard":
                pyxel.circ(i * w + w - 7, TAB_Y + 6, 3, C_ACCENT)   # 受け取れるものがある印

    def draw_toast(self):
        col = self.toast["col"]
        total_lines = self.toast_tw.text.split("\n")
        h = len(total_lines) * 13 + 8
        self.draw_panel(6, HEADER_H + 4, SCREEN_W - 12, h)
        for i, line in enumerate(self.toast_tw.visible.split("\n")):
            self.tx(12, HEADER_H + 8 + i * 13, line, col)

    def draw_modal(self):
        self.hits, self.areas = [], []          # 背後の操作は無効にする
        m = self.modal
        lines = self.wrap(m["text"], 176)
        h = len(lines) * 13 + 44
        x, y, w = 24, 90, SCREEN_W - 48
        self.draw_panel(x, y, w, h)
        for i, line in enumerate(lines):
            self.tx(x + 10, y + 10 + i * 13, line, C_TEXT)
        by = y + h - 26
        self.button(x + 14, by, 80, 18, "はい", self._modal_yes)
        self.button(x + w - 94, by, 80, 18, "いいえ", self._modal_no)

    def _modal_yes(self):
        fn = self.modal["yes"]
        self.modal = None
        fn()

    def _modal_no(self):
        self.modal = None

    # ---- にわ
    def draw_yard(self):
        s = self.state
        if s["food"]:
            self.tx(8, 22, "エサ: {0} 残り{1}分".format(game.FOODS[s["food"]]["name"], s["food_remaining"]), C_GOOD)
        else:
            self.tx(8, 22, "エサがありません(もちもの→エサ)", C_BAD)

        y = 38
        if not s["yard"]:
            for i, line in enumerate(self.wrap("庭にはおもちゃがありません。ショップで買って、もちものから置こう", SCREEN_W - 16)):
                self.tx(8, y + i * 13, line, C_SUB)
        for i, toy in enumerate(s["yard"]):
            spec = game.TOYS[toy]
            self.tx(8, y + i * ROW_H, spec["name"], C_TEXT)
            occ = game.occupants(s, toy)
            if occ:
                names = "、".join(game.CATS[c]["name"] for c in occ)
                names = self.fit(names, 110, "{0}匹".format(len(occ)))
                self.tx_right(SCREEN_W - 8, y + i * ROW_H, names, C_ACCENT)
            else:
                self.tx_right(SCREEN_W - 8, y + i * ROW_H, "(空き)", C_DIM)

        self.tx(8, 138, "できごと", C_SUB)
        pyxel.line(8, 150 - 2, SCREEN_W - 8, 150 - 2, C_DIM)
        for i, line in enumerate(self.visible_log(3)):
            self.tx(10, 152 + i * 13, line, C_TEXT)

        n_money = len(s["pending_money"])
        n_tre = len(s["pending_treasures"])
        self.button(8, 194, 118, 20, "さかなを受け取る({0})".format(n_money) if n_money else "さかな なし",
                    self.do_collect, enabled=bool(n_money))
        self.button(130, 194, 118, 20, "お宝を受け取る({0})".format(n_tre) if n_tre else "お宝 なし",
                    self.do_treasures, enabled=bool(n_tre))

    def do_collect(self):
        got = game.collect(self.state)
        if not got:
            self.show_toast("猫たちはまだ何も残していきませんでした", C_SUB)
            return
        total = {"s": 0, "g": 0}
        for _cid, amount, cur in got:
            total[cur] += amount
        parts = [fish_text(v, c) for c, v in total.items() if v]
        self.show_toast("やったね! {0}を受け取りました".format("と".join(parts)), C_GOOD)
        self.save()

    def do_treasures(self):
        got = game.collect_treasures(self.state)
        if not got:
            self.show_toast("受け取れるお宝はありません", C_SUB)
            return
        texts = ["{0}が「{1}」をくれました!".format(game.CATS[c]["name"], game.CATS[c]["treasure"]) for c in got]
        self.show_toast(" ".join(texts), C_ACCENT)
        self.save()

    # ---- ショップ
    def sub_tabs(self, screen, y=20):
        for i, label in enumerate(("おもちゃ", "エサ")):
            self.button(8 + i * 68, y, 64, 16, label, lambda i=i: self.set_sub(screen, i), active=(self.sub[screen] == i))

    def set_sub(self, screen, i):
        self.sub[screen] = i
        self.scroll.pop(screen, None)
        self.selected[screen] = None

    def draw_shop(self):
        s = self.state
        self.sub_tabs("shop")
        kind = "toy" if self.sub["shop"] == 0 else "food"
        ids = [k for k, v in game.ITEMS.items() if v["kind"] == kind]

        def row(i, ry, clip):
            item_id = ids[i]
            it = game.ITEMS[item_id]
            sel = self.selected["shop"] == item_id
            if sel:
                pyxel.rect(8, ry, SCREEN_W - 16, ROW_H, C_PANEL)
            owned = kind == "toy" and item_id in s["owned_toys"]
            self.tx(12, ry + 2, it["name"], C_DIM if owned else C_TEXT)
            if owned:
                self.tx_right(SCREEN_W - 14, ry + 2, "もっている", C_DIM)
            else:
                afford = s[it["cur"] + "_fish"] >= it["cost"]
                self.tx_right(SCREEN_W - 14, ry + 2, game.price_text(item_id), C_SUB if afford else C_BAD)
            self.hit(8, ry, SCREEN_W - 16, ROW_H, lambda: self.select("shop", item_id), clip)

        self.list_view("shop" + str(self.sub["shop"]), 8, 40, SCREEN_W - 16, 112, len(ids), row)

        sel = self.selected["shop"]
        self.draw_panel(8, 156, SCREEN_W - 16, 68)
        if sel:
            it = game.ITEMS[sel]
            self.tx(14, 160, "{0}  {1}".format(it["name"], game.price_text(sel)), C_ACCENT)
            info = it["desc"]
            if it["kind"] == "toy" and it["size"] > 1:
                info += "(庭を{0}マス使う)".format(it["size"])
            if it["kind"] == "food":
                info += "(約{0}分もつ)".format(it["size"])
            for i, line in enumerate(self.wrap(info, SCREEN_W - 36)[:3]):
                self.tx(14, 176 + i * 13, line, C_TEXT)
            owned = it["kind"] == "toy" and sel in s["owned_toys"]
            self.button(SCREEN_W - 66, 158, 52, 16, "買う", self.do_buy, enabled=not owned)
        else:
            self.tx(14, 164, "商品をタップすると説明が出ます", C_SUB)

    def select(self, screen, item_id):
        self.selected[screen] = item_id

    def do_buy(self):
        sel = self.selected["shop"]
        if not sel:
            return
        r = game.buy(self.state, sel)
        self.show_toast(r.msg, C_GOOD if r.ok else C_BAD)
        if r.ok:
            self.save()

    # ---- もちもの
    def draw_bag(self):
        s = self.state
        self.sub_tabs("bag")
        self.tx_right(SCREEN_W - 8, 22, "庭 {0}/{1}マス".format(game.space_used(s), game.SPACE), C_SUB)

        if self.sub["bag"] == 0:
            ids = list(s["owned_toys"])
            empty = "おもちゃを持っていません。ショップで買おう"
        else:
            ids = [f for f in game.FOODS if s["food_stock"].get(f, 0) > 0]
            empty = "エサを持っていません。ショップで買おう"

        if not ids:
            self.tx(12, 46, empty, C_SUB)

        def row(i, ry, clip):
            item_id = ids[i]
            it = game.ITEMS[item_id]
            if it["kind"] == "toy":
                placed = item_id in s["yard"]
                extra = "({0}マス)".format(it["size"]) if it["size"] > 1 else ""
                self.tx(12, ry + 2, it["name"] + extra, C_TEXT)
                self.tx_right(SCREEN_W - 14, ry + 2, "置いてある" if placed else "置く", C_GOOD if placed else C_SUB)
                fn = (lambda t=item_id: self.do_toggle_toy(t))
            else:
                self.tx(12, ry + 2, "{0} ×{1}".format(it["name"], s["food_stock"][item_id]), C_TEXT)
                self.tx_right(SCREEN_W - 14, ry + 2, "置く", C_SUB)
                fn = (lambda f=item_id: self.do_set_food(f))
            self.hit(8, ry, SCREEN_W - 16, ROW_H, fn, clip)

        self.list_view("bag" + str(self.sub["bag"]), 8, 40, SCREEN_W - 16, 150, len(ids), row)

        self.draw_panel(8, 196, SCREEN_W - 16, 28)
        if s["food"]:
            self.tx(14, 203, "庭のエサ: {0} 残り{1}分".format(game.FOODS[s["food"]]["name"], s["food_remaining"]), C_GOOD)
        else:
            self.tx(14, 203, "庭のエサ: なし", C_BAD)

    def do_toggle_toy(self, toy_id):
        s = self.state
        if toy_id in s["yard"]:
            r = game.remove_toy(s, toy_id)
        else:
            r = game.place_toy(s, toy_id)
        self.show_toast(r.msg, C_GOOD if r.ok else C_BAD)
        if r.ok:
            self.save()

    def do_set_food(self, food_id):
        r = game.set_food(self.state, food_id)
        if r.code == "need_confirm":
            self.modal = {"text": r.msg, "yes": lambda: self._set_food_force(food_id)}
            return
        self.show_toast(r.msg, C_GOOD if r.ok else C_BAD)
        if r.ok:
            self.save()

    def _set_food_force(self, food_id):
        r = game.set_food(self.state, food_id, force=True)
        self.show_toast(r.msg, C_GOOD if r.ok else C_BAD)
        if r.ok:
            self.save()

    # ---- おたから(猫の図鑑)
    def draw_cats(self):
        s = self.state
        ids = list(game.CATS)
        self.tx(8, 22, "猫たち(タップで詳しく)", C_SUB)

        def row(i, ry, clip):
            cid = ids[i]
            c = s["cats"][cid]
            sel = self.selected["cats"] == cid
            if sel:
                pyxel.rect(8, ry, SCREEN_W - 16, ROW_H, C_PANEL)
            met = c["met"]
            name = game.CATS[cid]["name"] if met else "？？？"
            self.tx(12, ry + 2, ("★ " if c["given_treasure"] else "") + name, C_TEXT if met else C_DIM)
            if met:
                self.tx_right(SCREEN_W - 14, ry + 2, "計{0}分".format(c["total_time"] + c["time_in_yard"]), C_SUB)
            self.hit(8, ry, SCREEN_W - 16, ROW_H, lambda cid=cid: self.select("cats", cid), clip)

        self.list_view("cats", 8, 38, SCREEN_W - 16, 5 * ROW_H, len(ids), row)

        self.draw_panel(8, 124, SCREEN_W - 16, 100)
        sel = self.selected["cats"]
        if not sel:
            self.panel_key = None
            self.tx(14, 130, "猫をタップしてね", C_SUB)
            return

        c = s["cats"][sel]
        key = (sel, c["met"], c["given_treasure"])
        if key != self.panel_key:
            self.panel_key = key
            self.panel_colors = self._build_cat_panel(sel)
        y = 130
        for line, col in zip(self.panel_tw.visible.split("\n"), self.panel_colors):
            self.tx(14, y, line, col)
            y += 13

    def _build_cat_panel(self, sel):
        """図鑑パネルの表示内容を組み立て、タイプライターにセットする。戻り値は行ごとの色。"""
        spec, c = game.CATS[sel], self.state["cats"][sel]
        met = c["met"]
        lines, colors = [], []

        lines.append(spec["name"] if met else "？？？")
        colors.append(C_ACCENT if met else C_DIM)
        lines.append("")
        colors.append(C_TEXT)

        if met:
            desc_lines = self.wrap(spec["desc"], SCREEN_W - 36)[:3]
        else:
            desc_lines = self.wrap("まだ出会っていない猫。庭に遊びに来ると正体がわかるよ。", SCREEN_W - 36)
        for line in desc_lines:
            lines.append(line)
            colors.append(C_TEXT)

        lines.append("")
        colors.append(C_SUB)
        if met:
            now = "{0}で遊んでいる".format(game.TOYS[c["toy"]]["name"]) if c["in_yard"] else "今はいない"
            lines.append("いま: " + now)
        else:
            lines.append("いま: ？？？")
        colors.append(C_SUB)

        lines.append("")
        if met and c["given_treasure"]:
            colors.append(C_ACCENT)
            lines.append("お宝:「{0}」".format(spec["treasure"]))
        elif met:
            colors.append(C_DIM)
            lines.append("お宝: ？？？(累計3000分〜)")
        else:
            colors.append(C_DIM)
            lines.append("お宝: ？？？")

        self.panel_tw.set_text("\n".join(lines))
        return colors

    # ---- ヘルプ
    def draw_help(self):
        y = 24
        for text in HELP_LINES:
            for line in self.wrap(text, SCREEN_W - 16):
                self.tx(8, y, line, C_TEXT)
                y += 13
        y += 6
        if self.save_path:
            self.tx(8, y, "自動でセーブしています", C_GOOD)
        else:
            self.tx(8, y, "この環境ではセーブできません", C_BAD)


if not os.environ.get("NEKOATSUME_NO_AUTORUN"):   # テストから import するときだけ自動起動を止める
    App()
