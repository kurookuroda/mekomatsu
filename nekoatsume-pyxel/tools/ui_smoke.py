"""UI のスモークテスト(タップ操作を再現して画面遷移・購入・配置・保存を確認する)。

実行: LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a python3 tools/ui_smoke.py   (画面のない Linux の場合)
      python3 tools/ui_smoke.py                                        (デスクトップ環境の場合)
スクリーンショットは環境変数 SHOT_DIR に出力される。
"""
import os, sys, shutil, time
os.environ["NEKOATSUME_NO_AUTORUN"] = "1"
os.environ["SDL_AUDIODRIVER"] = "dummy"
SAVE_DIR = os.path.join(__import__('tempfile').gettempdir(), 'nekoatsume_ui_smoke')
shutil.rmtree(SAVE_DIR, ignore_errors=True)
os.environ["NEKOATSUME_SAVE_DIR"] = SAVE_DIR
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import pyxel, nekoatsume, game
SHOT_DIR = os.environ.get('SHOT_DIR', os.path.join(SAVE_DIR, 'shots'))

app = nekoatsume.App(run=False)
T = [1_000_000.0]
app.state["last_tick"] = app.state["last_seen"] = T[0]
app.clock = lambda: T[0]

ptr = {"x": 0, "y": 0, "pressed": False, "held": False, "released": False, "wheel": 0}
keys = set()
app._pointer = lambda: (ptr["x"], ptr["y"], ptr["pressed"], ptr["held"], ptr["released"], ptr["wheel"])
app._keys = lambda: set(keys)

def frame():
    app.update(); app.draw()

def shot(name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    pyxel.screen.save(os.path.join(SHOT_DIR, "%s.png" % name), 2)

def click(x, y):
    ptr.update(x=x, y=y, pressed=True, held=True, released=False); frame()
    ptr.update(pressed=False, held=False, released=True); frame()
    ptr.update(released=False); frame()

def drag(x, y0, y1, steps=6):
    ptr.update(x=x, y=y0, pressed=True, held=True, released=False); frame()
    ptr.update(pressed=False)
    for i in range(1, steps + 1):
        ptr["y"] = y0 + (y1 - y0) * i // steps; frame()
    ptr.update(held=False, released=True); frame()
    ptr.update(released=False); frame()

frame(); frame()
shot("01_yard_start")

# ショップ
click(64, 240)                       # タブ「ショップ」
assert app.screen == "shop", app.screen
frame(); shot("02_shop")
click(100, 48)                       # 1行目=ゴムボール
assert app.selected["shop"] == "rubber_ball"
click(SCREEN := 256 - 66 + 10, 166)  # 買う
assert app.state["owned_toys"] == ["rubber_ball"], app.state["owned_toys"]
click(100, 48 + 16); click(256 - 56, 166)   # キラキラボール(金5)
click(100, 48 + 32); click(256 - 56, 166)   # 毛糸玉
print("owned:", app.state["owned_toys"], "silver", app.state["s_fish"], "gold", app.state["g_fish"])
shot("03_shop_bought")
# ドラッグでスクロール
before = app.scroll.get("shop0", 0)
drag(100, 120, 60)
after = app.scroll.get("shop0", 0)
print("scroll", before, "->", after); assert after > before
shot("04_shop_scrolled")
# エサタブ
click(8 + 68 + 10, 28)
assert app.sub["shop"] == 1
click(100, 48)                       # ドライフード
click(256 - 56, 166)
assert app.state["food_stock"] == {"dry_food": 1}, app.state["food_stock"]
shot("05_shop_food")

# もちもの
click(3 * 51 // 2 * 2 + 90, 240) if False else click(2 * 51 + 20, 240)
assert app.screen == "bag", app.screen
click(100, 48); click(100, 64); click(100, 80)   # 3個置く
print("yard:", app.state["yard"])
assert len(app.state["yard"]) == 3
click(8 + 68 + 10, 28)                # エサ
click(100, 48)                        # ドライフードを置く
assert app.state["food"] == "dry_food"
shot("06_bag_food")

# 経過時間 → 猫が来る
click(20, 240)
for step in range(90):
    T[0] += 60
    frame()
shot("07_yard_playing")
print("cats in yard:", game.cats_in_yard(app.state), "pending", len(app.state["pending_money"]))
print("log:", app.log[-3:])
n = len(app.state["pending_money"])
click(60, 204)                        # さかなを受け取る
print("wallet after collect: silver", app.state["s_fish"], "gold", app.state["g_fish"], "pending", len(app.state["pending_money"]))
assert app.state["pending_money"] == [] or n == 0
shot("08_collected")

# エサの置き換え確認モーダル
app.state["food_stock"]["dry_food"] = 1
click(2 * 51 + 20, 240); click(8 + 68 + 10, 28); click(100, 48)
assert app.modal, "確認モーダルが出るはず"
shot("09_modal")
click(78, 142)                        # モーダルの「はい」
assert app.modal is None and app.state['food_remaining'] == 300, (app.modal, app.state['food_remaining'])
frame(); shot("10_after_modal")

# 猫
click(3 * 51 + 20, 240); click(100, 46)
assert app.screen == "cats" and app.selected["cats"] == "gordo"
shot("11_cats")
click(4 * 51 + 20, 240); shot("12_help")

# セーブ・ロード
assert os.path.exists("/tmp/savetest/save.json")
s2 = game.loads(open("/tmp/savetest/save.json", encoding="utf-8").read())
assert s2["owned_toys"] == app.state["owned_toys"]
print("save OK, bytes:", os.path.getsize("/tmp/savetest/save.json"))
print("ALL UI CHECKS PASSED")
