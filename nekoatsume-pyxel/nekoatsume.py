"""
ねこあつめ Pyxel 版(文字だけの UI)

    実行:  pyxel run nekoatsume.py      (または python nekoatsume.py)
    Web :  https://kitao.github.io/pyxel/web/launcher/?run=<ユーザー名>.<リポジトリ名>.nekoatsume

操作は「タップ / クリック」が基本。リストはドラッグ(ホイール・↑↓キーも可)でスクロールし、右端のバーをつかむと一気に動かせる。
文章は1文字ずつ出る。枠に収まらないときはページに分かれ、▼ が点滅したらタップ(Enter / Space)で次へ。
1〜5 キーで下のタブを切り替えられる。ゲームのルールは game.py、アイテムと猫のデータは catalog.py にある。
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
ROW_H = FONT_SIZE + 6           # リストの行の高さ(フォントの実寸に合わせる)
LINE_H = FONT_SIZE + 3          # 複数行テキストの行送り(同上)
LOG_MAX = 30
TOAST_FRAMES = 75              # 30fps で約2.5秒
TOAST_MAX_LINES = 3            # これより長いメッセージは、ページ送りのダイアログで出す

# 文章の枠(ページ送り)まわり
PAD_X = 6                      # 枠の内側の左右の余白
PAD_Y = 4                      # 枠の内側の上下の余白
CURSOR_H = FONT_SIZE           # 枠の下に必ず空ける高さ(ページ番号と「▼」の場所。文章はここに入り込まない)
MSG_X, MSG_Y, MSG_W, MSG_H = 12, 28, SCREEN_W - 24, 192   # 長いメッセージのダイアログ

# リストのスクロールバー
BAR_W = 6                      # 見た目の幅
BAR_HIT_W = 10                 # つかめる幅(右端のこの幅を触るとバーの操作になる)
ROW_RIGHT = SCREEN_W - 20      # リスト行の右側の文字の右端(バーと重ならない位置)

UNMET_KEY = "?unmet"           # 図鑑の「まだ出会っていない猫」の行

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
    "",
    "文章が長いときは、右下で ▼ が点滅します。画面をタップすると、次のページに進みます。",
    "猫やアイテムが増えても、リストの右端(バー)をドラッグすれば、すばやく動かせます。",
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
    if kind == "met":
        return "{0}と はじめて出会った!".format(game.CATS[ev[1]]["name"])
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


class PagedText:
    """長い文章を、決められた大きさの枠に収まるページに分け、1文字ずつ表示する。

    - 枠の下には、ページ番号と「▼」を出すための余白(CURSOR_H)を必ず空ける。文章が枠の下にはみ出すことはない
    - 次のページがあるとき、文字を出し終えると「▼」が点滅する。タップ(クリック)かキーで次のページへ進む
    - 行の位置とページの割り方は set() のときに決まり、key が同じあいだは決め直さない
      (伏せ字のときも、本当の文と同じ長さで組むので、あとで明かされても位置がずれない)
    """

    def __init__(self):
        self.key = None
        self.group = None
        self.pages = [[]]          # [[(行, 色), ...], ...]
        self.page = 0
        self.tw = Typewriter()
        self.w = 0
        self.h = 0

    def set(self, key, blocks, wrap, w, h, group=None):
        """blocks は [(文章, 色), ...]。w, h は枠の大きさ。group が同じなら、ページと表示済みの状態を引き継ぐ。"""
        if key == self.key:
            return
        keep = group is not None and group == self.group
        self.key, self.group = key, group
        self.w, self.h = w, h
        max_lines = max(1, (h - 2 * PAD_Y - CURSOR_H) // LINE_H)
        lines = []
        for text, col in blocks:
            for line in wrap(text, w - 2 * PAD_X - FONT_SIZE):
                lines.append((line, col))
        pages, cur = [], []
        for item in lines:
            if len(cur) >= max_lines:
                pages.append(cur)
                cur = []
            if not cur and pages and item[0] == "":       # ページの頭に来た空行は捨てる
                continue
            cur.append(item)
        if cur or not pages:
            pages.append(cur)
        self.pages = pages
        self.page = min(self.page, len(pages) - 1) if keep else 0
        self._start_page(skip=keep)

    def _start_page(self, skip=False):
        self.tw.text = None                               # 同じ文でも、最初から出し直す
        self.tw.set_text("\n".join(line for line, _c in self.pages[self.page]))
        if skip:
            self.tw.skip()

    @property
    def typing(self):
        return not self.tw.done

    @property
    def has_next(self):
        return self.page < len(self.pages) - 1

    def skip(self):
        self.tw.skip()

    def next_page(self):
        if self.has_next:
            self.page += 1
            self._start_page()

    def advance(self):
        """タップ・キーで呼ぶ。文字送りの途中なら全部出す。出し終えていれば次のページへ。何かしたら True。"""
        if not self.tw.done:
            self.tw.skip()
            return True
        if self.has_next:
            self.next_page()
            return True
        return False

    def update(self, on_char=None):
        self.tw.update(on_char)

    def draw(self, app, x, y):
        """(x, y) は枠の左上。文字は枠の余白の内側に並べる。"""
        cols = [c for _line, c in self.pages[self.page]]
        for i, line in enumerate(self.tw.visible.split("\n")):
            if i < len(cols):
                app.tx(x + PAD_X, y + PAD_Y + i * LINE_H, line, cols[i])
        base = y + self.h - PAD_Y
        if len(self.pages) > 1:
            app.tx(x + PAD_X, base - FONT_SIZE, "{0}/{1}".format(self.page + 1, len(self.pages)), C_DIM)
        if self.tw.done and self.has_next and (pyxel.frame_count // 12) % 2 == 0:
            cx = x + self.w - PAD_X - 8
            pyxel.tri(cx, base - 9, cx + 7, base - 9, cx + 3, base - 3, C_ACCENT)   # 逆三角(▼)の点滅


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
        self.cat_pager = PagedText()           # 図鑑の猫のプロフィール
        self.shop_pager = PagedText()          # ショップの商品説明
        self.help_pager = PagedText()          # ヘルプ
        self.message = None                    # 長いメッセージのダイアログ {"pager": PagedText}
        self.pager_regs = []                   # このフレームに描いたページ送りの枠 [(pager, x, y, w, h)]
        self.modal = None                      # {"text":..., "yes": fn}
        self.hits = []
        self.areas = []
        self.press = None
        # ショップの表示条件(種別・絞り込み・並べ替え)
        self.shop_kind = 0
        self.shop_cat_off = 0                  # 種別タブが多いとき、先頭に出す種別の番号
        self.shop_filter = 0
        self.shop_sort = 0
        self._shop_cache = (None, [])
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
        """幅 max_w で折り返す。行頭に来てはいけない「。」「、」などは、1文字分だけ行末にぶら下げる。
        そのため、行の幅は最大で max_w + FONT_SIZE になる(呼ぶ側は、その分の余白を見込んで max_w を決める)。"""
        lines = []
        for para in s.split("\n"):
            line = ""
            for ch in para:
                hang = ch in NO_LINE_START and self.tw(line + ch) <= max_w + FONT_SIZE
                if self.tw(line + ch) > max_w and line and not hang:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
            lines.append(line)
        return lines

    def add_log(self, text):
        full = "\n".join(self.wrap(text, SCREEN_W - 32))
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
        """短い知らせは画面の上にさっと出す。長いときはページ送りのダイアログにする(はみ出さないように)。"""
        lines = self.wrap(text, SCREEN_W - 36)
        if len(lines) > TOAST_MAX_LINES:
            self.show_message(text, col)
            return
        self.toast = {"col": col, "frames": TOAST_FRAMES}
        self.toast_tw.set_text("\n".join(lines))

    def show_message(self, text, col=C_TEXT):
        """長い文章のダイアログ。ページに分け、▼ が点滅したらタップで進み、最後のページでタップすると閉じる。"""
        pager = PagedText()
        pager.set(("msg", text), [(text, col)], self.wrap, MSG_W, MSG_H)
        self.message = {"pager": pager}
        self.toast = None

    def _advance_message(self):
        if not self.message["pager"].advance():
            self.message = None

    # ------------------------------------------------------------ 入力
    def _pointer(self):
        """(x, y, 押した瞬間, 押している, 離した瞬間, ホイール)。テストでは差し替える。"""
        return (pyxel.mouse_x, pyxel.mouse_y,
                pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT), pyxel.btn(pyxel.MOUSE_BUTTON_LEFT),
                pyxel.btnr(pyxel.MOUSE_BUTTON_LEFT), pyxel.mouse_wheel)

    def _keys(self):
        """キーボード入力(押した瞬間の集合)。テストでは差し替える。"""
        keys = set()
        for name in ("KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_UP", "KEY_DOWN",
                     "KEY_PAGEUP", "KEY_PAGEDOWN", "KEY_HOME", "KEY_END", "KEY_RETURN", "KEY_SPACE"):
            if hasattr(pyxel, name) and pyxel.btnp(getattr(pyxel, name)):
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

    def _drag_bar(self, area, y):
        """スクロールバーをつかんで動かす(押した位置にバーが来る)。猫や商品が何百あっても、すぐ目的の場所へ行ける。"""
        key, _ax, ay, _aw, ah, maxs = area
        total = maxs + ah
        thumb = max(10, ah * ah // total)
        ratio = (y - ay - thumb / 2) / max(1, ah - thumb)
        self.scroll[key] = int(min(max(ratio, 0), 1) * maxs)

    def handle_input(self):
        mx, my, pressed, held, released, wheel = self._pointer()
        if pressed:
            area = self._area_at(mx, my)
            bar = bool(area and area[5] > 0 and mx >= area[1] + area[3] - BAR_HIT_W)
            self.press = {"y": my, "area": area, "off": self.scroll.get(area[0], 0) if area else 0,
                          "moved": bar, "bar": bar}
            if bar:
                self._drag_bar(area, my)
        elif self.press and held and self.press["area"]:
            p = self.press
            if p["bar"]:
                self._drag_bar(p["area"], my)
            elif p["moved"] or abs(my - p["y"]) > 4:
                p["moved"] = True
                key, _ax, _ay, _aw, _ah, maxs = p["area"]
                self.scroll[key] = min(max(p["off"] + p["y"] - my, 0), maxs)
        if released and self.press:
            moved = self.press["moved"]
            self.press = None
            if not moved:
                self._on_tap(mx, my)
        if wheel:
            area = self._area_at(mx, my)
            if area:
                self._scroll_by(area, -wheel * ROW_H)

        keys = self._keys()
        if self.message:
            if keys & {"KEY_RETURN", "KEY_SPACE"}:
                self._advance_message()
            return
        for i, (name, _label) in enumerate(TABS):
            if "KEY_%d" % (i + 1) in keys:
                self.goto(name)
        if keys & {"KEY_RETURN", "KEY_SPACE"}:
            self._advance_key()
        if self.areas:
            area = self.areas[0]
            page = max(1, area[4] // ROW_H) * ROW_H
            for name, dy in (("KEY_UP", -ROW_H), ("KEY_DOWN", ROW_H), ("KEY_PAGEUP", -page),
                             ("KEY_PAGEDOWN", page), ("KEY_HOME", -10 ** 9), ("KEY_END", 10 ** 9)):
                if name in keys:
                    self._scroll_by(area, dy)

    def _on_tap(self, x, y):
        """タップの振り分け。長いメッセージ > 文字送り中(全部出す) > ページ送りの枠(次のページ) > ふつうのボタン"""
        if self.message:
            self._advance_message()
            return
        if self._typing_active():
            self._skip_typing()
            return
        for pager, rx, ry, rw, rh in reversed(self.pager_regs):
            if rx <= x < rx + rw and ry <= y < ry + rh and pager.has_next:
                pager.next_page()
                return
        self.tap(x, y)

    def _advance_key(self):
        """Enter / Space: タップと同じ(位置は問わない)。"""
        if self._typing_active():
            self._skip_typing()
            return
        for pager, _x, _y, _w, _h in reversed(self.pager_regs):
            if pager.has_next:
                pager.next_page()
                return

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
            self.hits, self.areas, self.pager_regs, self.press = [], [], [], None
            if name == "help":
                self.help_pager.key = None          # ヘルプは開くたびに、はじめから読み上げる

    # ------------------------------------------------------------ 一文字ずつ表示(タイプライター)
    def _visible_pagers(self):
        pagers = [p for p, _x, _y, _w, _h in self.pager_regs]
        if self.message:
            pagers.append(self.message["pager"])
        return pagers

    def _typing_active(self):
        return (self._log_typing() or not self.toast_tw.done
                or any(p.typing for p in self._visible_pagers()))

    def _skip_typing(self):
        self._skip_log()
        self.toast_tw.skip()
        for p in self._visible_pagers():
            p.skip()

    # ------------------------------------------------------------ 更新
    def update(self):
        rep = game.advance(self.state, self.clock())
        if rep["ticks"]:
            if rep["ticks"] <= 3:
                for ev in rep["events"]:
                    text = event_text(ev)
                    if text:
                        self.add_log(text)
            else:
                self.add_log("{0}分たちました。猫が{1}回遊びに来たよ".format(rep["ticks"], rep["visits"]))
            self.save()
        self.handle_input()
        self._advance_log_typing()
        self.toast_tw.update(self._play_type_sound)
        for pager in self._visible_pagers():
            pager.update(self._play_type_sound)
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
        """縦に並べるリスト。見えている行だけ描くので、行が何千あっても軽い。右端のバーはドラッグで動かせる。"""
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
            total = maxs + h
            bar_h = max(10, h * h // total)
            bar_y = y + (h - bar_h) * off // maxs
            pyxel.rect(x + w - BAR_W, y, BAR_W, h, C_PANEL)                    # 溝
            pyxel.rect(x + w - BAR_W, int(bar_y), BAR_W, bar_h, C_DIM)         # つまみ

    def draw_panel(self, x, y, w, h):
        pyxel.rect(x, y, w, h, C_PANEL)
        pyxel.rectb(x, y, w, h, C_DIM)

    # ------------------------------------------------------------ 描画
    def draw(self):
        self.hits, self.areas, self.pager_regs = [], [], []
        pyxel.cls(C_BG)
        self.draw_header()
        getattr(self, "draw_" + self.screen)()
        self.draw_tabs()
        if self.toast:
            self.draw_toast()
        if self.modal:
            self.draw_modal()
        if self.message:
            self.draw_message()

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
        h = len(total_lines) * LINE_H + 8
        self.draw_panel(6, HEADER_H + 4, SCREEN_W - 12, h)
        for i, line in enumerate(self.toast_tw.visible.split("\n")):
            self.tx(12, HEADER_H + 8 + i * LINE_H, line, col)

    def draw_message(self):
        self.hits, self.areas, self.pager_regs = [], [], []     # 背後の操作は無効にする
        self.draw_panel(MSG_X, MSG_Y, MSG_W, MSG_H)
        pager = self.message["pager"]
        pager.draw(self, MSG_X, MSG_Y)
        if pager.tw.done and not pager.has_next:
            self.tx_right(MSG_X + MSG_W - PAD_X, MSG_Y + MSG_H - PAD_Y - FONT_SIZE, "タップで閉じる", C_DIM)

    def draw_modal(self):
        self.hits, self.areas, self.pager_regs = [], [], []     # 背後の操作は無効にする
        m = self.modal
        lines = self.wrap(m["text"], 164)
        h = len(lines) * LINE_H + 44
        x, y, w = 24, 90, SCREEN_W - 48
        self.draw_panel(x, y, w, h)
        for i, line in enumerate(lines):
            self.tx(x + 10, y + 10 + i * LINE_H, line, C_TEXT)
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
        yard_bottom = y
        if not s["yard"]:
            for i, line in enumerate(self.wrap("庭にはおもちゃがありません。ショップで買って、もちものから置こう", SCREEN_W - 16)):
                self.tx(8, y + i * LINE_H, line, C_SUB)
                yard_bottom = y + (i + 1) * LINE_H
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
            yard_bottom = y + (i + 1) * ROW_H

        # 「できごと」見出し→区切り線→ログ、の順に、フォントの実寸に合わせて積み上げる
        # (ボタン行の上で必ず収まるよう、はみ出したらログの行数を減らす)
        buttons_y = 194
        label_y = yard_bottom + 6
        line_y = label_y + FONT_SIZE + 3
        log_y = line_y + 5
        max_log_lines = max(1, (buttons_y - 4 - log_y) // LINE_H)

        self.tx(8, label_y, "できごと", C_SUB)
        pyxel.line(8, line_y, SCREEN_W - 8, line_y, C_DIM)
        for i, line in enumerate(self.visible_log(max_log_lines)):
            self.tx(10, log_y + i * LINE_H, line, C_TEXT)

        n_money = len(s["pending_money"])
        n_tre = len(s["pending_treasures"])
        self.button(8, buttons_y, 118, 20, "さかなを受け取る({0})".format(n_money) if n_money else "さかな なし",
                    self.do_collect, enabled=bool(n_money))
        self.button(130, buttons_y, 118, 20, "お宝を受け取る({0})".format(n_tre) if n_tre else "お宝 なし",
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
        self.show_toast("\n".join(texts), C_ACCENT)
        self.save()

    # ---- ショップ
    def sub_tabs(self, screen, y=20):
        for i, label in enumerate(("おもちゃ", "エサ")):
            self.button(8 + i * 68, y, 64, 16, label, lambda i=i: self.set_sub(screen, i), active=(self.sub[screen] == i))

    def set_sub(self, screen, i):
        self.sub[screen] = i
        self.scroll.pop(screen, None)
        self.selected[screen] = None

    def arrow_button(self, x, y, w, h, direction, fn, enabled=True):
        """◀ ▶ のボタン(フォントに依存しないよう、三角を自分で描く)。"""
        self.button(x, y, w, h, "", fn, enabled=enabled)
        col = C_TEXT if enabled else C_DIM
        cx, cy = x + w // 2, y + h // 2
        if direction < 0:
            pyxel.tri(cx + 2, cy - 4, cx + 2, cy + 4, cx - 3, cy, col)
        else:
            pyxel.tri(cx - 2, cy - 4, cx - 2, cy + 4, cx + 3, cy, col)

    def _shop_set_kind(self, i):
        self.shop_kind = i
        self.scroll.pop("shop", None)

    def _shop_page_kinds(self, d):
        n = len(game.CATEGORIES)
        self.shop_cat_off = min(max(self.shop_cat_off + d, 0), max(0, n - 2))

    def _shop_cycle(self, what):
        if what == "filter":
            self.shop_filter = (self.shop_filter + 1) % len(game.SHOP_FILTERS)
        else:
            self.shop_sort = (self.shop_sort + 1) % len(game.SHOP_SORTS)
        self.scroll.pop("shop", None)

    def _shop_strip(self):
        """種別タブ(種別が3つ以上なら ◀ ▶ でめくる)と、絞り込み・並べ替えのボタン。"""
        cats = game.CATEGORIES
        n = len(cats)
        self.shop_kind = min(self.shop_kind, n - 1)
        y, h = 20, 16
        if n <= 2:
            slots, x0, w = list(range(n)), 8, 52
        else:
            off = min(self.shop_cat_off, n - 2)
            slots, x0, w = [off, off + 1], 24, 40
            self.arrow_button(8, y, 14, h, -1, lambda: self._shop_page_kinds(-1), enabled=off > 0)
            self.arrow_button(x0 + 2 * (w + 2), y, 14, h, 1, lambda: self._shop_page_kinds(1), enabled=off + 2 < n)
        for k, idx in enumerate(slots):
            label = self.fit(cats[idx][1], w - 4)
            self.button(x0 + k * (w + 2), y, w, h, label, lambda idx=idx: self._shop_set_kind(idx),
                        active=(idx == self.shop_kind))
        self.button(126, y, 58, h, game.SHOP_FILTERS[self.shop_filter][1], lambda: self._shop_cycle("filter"),
                    active=self.shop_filter != 0)
        self.button(186, y, 62, h, game.SHOP_SORTS[self.shop_sort][1], lambda: self._shop_cycle("sort"),
                    active=self.shop_sort != 0)

    def _shop_ids(self, kind):
        """表示するアイテムID。条件と持ち物が変わったときだけ作り直す(商品が何千あっても毎フレームは数えない)。"""
        s = self.state
        filt = game.SHOP_FILTERS[self.shop_filter][0]
        sort = game.SHOP_SORTS[self.shop_sort][0]
        key = (game.CATALOG_VERSION, kind, filt, sort, s["s_fish"], s["g_fish"],
               len(s["owned_toys"]), sum(s["food_stock"].values()))
        if self._shop_cache[0] != key:
            self._shop_cache = (key, game.shop_ids(s, kind, filt, sort))
        return self._shop_cache[1]

    def draw_shop(self):
        s = self.state
        self._shop_strip()
        kind = game.CATEGORIES[self.shop_kind][0]
        ids = self._shop_ids(kind)
        owned_set = set(s["owned_toys"])

        def row(i, ry, clip):
            item_id = ids[i]
            it = game.ITEMS[item_id]
            if self.selected["shop"] == item_id:
                pyxel.rect(8, ry, SCREEN_W - 16, ROW_H, C_PANEL)
            owned = kind == "toy" and item_id in owned_set
            self.tx(12, ry + 2, it["name"], C_DIM if owned else C_TEXT)
            if owned:
                self.tx_right(ROW_RIGHT, ry + 2, "もっている", C_DIM)
            else:
                afford = s[it["cur"] + "_fish"] >= it["cost"]
                self.tx_right(ROW_RIGHT, ry + 2, game.price_text(item_id), C_SUB if afford else C_BAD)
            self.hit(8, ry, SCREEN_W - 16, ROW_H, lambda: self.select("shop", item_id), clip)

        list_h = 96
        if not ids:
            self.tx(12, 46, "条件に合う商品はありません", C_SUB)
        self.list_view("shop", 8, 40, SCREEN_W - 16, list_h, len(ids), row)

        sel = self.selected["shop"]
        panel_y = 40 + list_h + 4
        panel_h = TAB_Y - 4 - panel_y
        self.draw_panel(8, panel_y, SCREEN_W - 16, panel_h)
        if sel in game.ITEMS:
            it = game.ITEMS[sel]
            self.tx(14, panel_y + 4, "{0}  {1}".format(it["name"], game.price_text(sel)), C_ACCENT)
            info = it["desc"]
            if it["kind"] == "toy" and it["size"] > 1:
                info += "(庭を{0}マス使う)".format(it["size"])
            if it["kind"] == "food":
                info += "(約{0}分もつ)".format(it["size"])
            # 説明の枠: 見出しの下から、パネルの下端まで。長い説明はページに分かれる
            ty = panel_y + 4 + LINE_H
            th = panel_y + panel_h - ty
            self.shop_pager.set(("shop", sel), [(info, C_TEXT)], self.wrap, SCREEN_W - 16, th, group=None)
            self.shop_pager.draw(self, 8, ty)
            self.pager_regs.append((self.shop_pager, 8, ty, SCREEN_W - 16, th))
            owned = it["kind"] == "toy" and sel in owned_set
            self.button(SCREEN_W - 66, panel_y + 2, 52, 16, "買う", self.do_buy, enabled=not owned)
        else:
            self.tx(14, panel_y + 6, "商品をタップすると説明が出ます", C_SUB)
            self.tx(14, panel_y + 6 + LINE_H, "({0}件)".format(len(ids)), C_DIM)

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
                self.tx_right(ROW_RIGHT, ry + 2, "置いてある" if placed else "置く", C_GOOD if placed else C_SUB)
                fn = (lambda t=item_id: self.do_toggle_toy(t))
            else:
                self.tx(12, ry + 2, "{0} ×{1}".format(it["name"], s["food_stock"][item_id]), C_TEXT)
                self.tx_right(ROW_RIGHT, ry + 2, "置く", C_SUB)
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
        """図鑑は「出会った順」に並ぶ。猫がはじめて庭に来たときに、その順番の位置が決まる。
        未発見の猫は1行(あと◯匹)にまとめるので、猫が何匹いても一覧は長くならない。"""
        s = self.state
        met = game.met_list(s)
        total = len(game.CATS)
        unmet = total - len(met)
        n_rows = len(met) + (1 if unmet > 0 else 0)
        self.tx(8, 22, "出会った猫 {0}/{1}".format(len(met), total), C_SUB)

        def row(i, ry, clip):
            if i < len(met):
                cid = met[i]
                c = s["cats"][cid]
                if self.selected["cats"] == cid:
                    pyxel.rect(8, ry, SCREEN_W - 16, ROW_H, C_PANEL)
                self.tx(12, ry + 2, ("★ " if c["given_treasure"] else "") + game.CATS[cid]["name"], C_TEXT)
                self.tx_right(ROW_RIGHT, ry + 2, "計{0}分".format(c["total_time"] + c["time_in_yard"]), C_SUB)
                self.hit(8, ry, SCREEN_W - 16, ROW_H, lambda cid=cid: self.select("cats", cid), clip)
            else:
                if self.selected["cats"] == UNMET_KEY:
                    pyxel.rect(8, ry, SCREEN_W - 16, ROW_H, C_PANEL)
                self.tx(12, ry + 2, "？？？", C_DIM)
                self.tx_right(ROW_RIGHT, ry + 2, "あと{0}匹".format(unmet), C_DIM)
                self.hit(8, ry, SCREEN_W - 16, ROW_H, lambda: self.select("cats", UNMET_KEY), clip)

        list_h = 4 * ROW_H
        self.list_view("cats", 8, 38, SCREEN_W - 16, list_h, n_rows, row)

        panel_y = 38 + list_h + 6
        panel_h = TAB_Y - 4 - panel_y
        self.draw_panel(8, panel_y, SCREEN_W - 16, panel_h)
        sel = self.selected["cats"]
        if sel == UNMET_KEY and unmet > 0:
            blocks = [("？？？", C_DIM),
                      ("まだ出会っていない猫が、あと{0}匹いる。庭に遊びに来ると、ここに載るよ。".format(unmet), C_TEXT)]
            self.cat_pager.set(("unmet", unmet), blocks, self.wrap, SCREEN_W - 16, panel_h, group="unmet")
        elif sel in s["cats"] and s["cats"][sel]["met"]:
            c = s["cats"][sel]
            key = ("cat", sel, c["given_treasure"], c["in_yard"], c["toy"])
            self.cat_pager.set(key, self._cat_blocks(sel), self.wrap, SCREEN_W - 16, panel_h, group=sel)
        else:
            self.tx(14, panel_y + 6, "猫をタップしてね", C_SUB)
            return
        self.cat_pager.draw(self, 8, panel_y)
        self.pager_regs.append((self.cat_pager, 8, panel_y, SCREEN_W - 16, panel_h))

    def _cat_blocks(self, cid):
        """プロフィールの中身。伏せ字(まだ明かされていないお宝)は、本当の文と同じ長さの「？」で組む。
        こうすると、あとで明かされても行の数や位置が変わらない。"""
        spec, c = game.CATS[cid], self.state["cats"][cid]
        now = "{0}で遊んでいる".format(game.TOYS[c["toy"]]["name"]) if c["in_yard"] else "今はいない"
        treasure = spec["treasure"] if c["given_treasure"] else "？" * len(spec["treasure"])
        return [(spec["name"], C_ACCENT),
                (spec["desc"], C_TEXT),
                ("いま: " + now, C_SUB),
                ("お宝:「{0}」".format(treasure), C_ACCENT if c["given_treasure"] else C_DIM)]

    # ---- ヘルプ
    def draw_help(self):
        """ヘルプもタイプライターで読み上げる。長いぶんはページに分かれ、▼ が点滅したらタップで次へ。"""
        x, y, w = 0, HEADER_H + 2, SCREEN_W
        h = TAB_Y - 4 - y
        blocks = [(text, C_TEXT) for text in HELP_LINES]
        blocks.append(("", C_TEXT))
        blocks.append(("自動でセーブしています", C_GOOD) if self.save_path else ("この環境ではセーブできません", C_BAD))
        self.help_pager.set(("help", bool(self.save_path)), blocks, self.wrap, w, h)
        self.help_pager.draw(self, x, y)
        self.pager_regs.append((self.help_pager, x, y, w, h))


if not os.environ.get("NEKOATSUME_NO_AUTORUN"):   # テストから import するときだけ自動起動を止める
    App()
