"""UI のスモークテスト(タップ操作を再現して、画面遷移・購入・配置・ページ送り・大量データを確認する)。

実行: LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a python3 tools/ui_smoke.py   (画面のない Linux の場合)
      python3 tools/ui_smoke.py                                        (デスクトップ環境の場合)
スクリーンショットは環境変数 SHOT_DIR に出力される。
"""
import os
import shutil
import sys
import tempfile

os.environ["NEKOATSUME_NO_AUTORUN"] = "1"
SAVE_DIR = os.path.join(tempfile.gettempdir(), "nekoatsume_ui_smoke")
shutil.rmtree(SAVE_DIR, ignore_errors=True)
os.environ["NEKOATSUME_SAVE_DIR"] = SAVE_DIR
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pyxel                     # noqa: E402
import catalog                   # noqa: E402
import game                      # noqa: E402
import nekoatsume as N           # noqa: E402

SHOT_DIR = os.environ.get("SHOT_DIR", os.path.join(SAVE_DIR, "shots"))
os.makedirs(SHOT_DIR, exist_ok=True)

app = N.App(run=False)
T = [1_000_000.0]
app.state["last_tick"] = app.state["last_seen"] = T[0]
app.clock = lambda: T[0]

ptr = {"x": 0, "y": 0, "pressed": False, "held": False, "released": False, "wheel": 0}
keys = set()
app._pointer = lambda: (ptr["x"], ptr["y"], ptr["pressed"], ptr["held"], ptr["released"], ptr["wheel"])
app._keys = lambda: set(keys)


def check_layout():
    """どのページも、枠の下端(ページ番号と▼の余白のぶん)に食い込んでいないこと。1行が枠の幅を超えていないこと。"""
    pagers = [p for p, *_ in app.pager_regs]
    if app.message:
        pagers.append(app.message["pager"])
    for p in pagers:
        for page in p.pages:
            assert N.PAD_Y + len(page) * N.LINE_H <= p.h - N.PAD_Y - N.CURSOR_H, (p.key, len(page), p.h)
            for line, _c in page:
                assert app.tw(line) <= p.w - 2 * N.PAD_X, (p.key, line)


def frame():
    app.update()
    app.draw()
    check_layout()


def shot(name):
    pyxel.screen.save(os.path.join(SHOT_DIR, name + ".png"), 2)


def settle():
    app._skip_typing()


def click(x, y, settle_first=True):
    if settle_first:
        settle()
    ptr.update(x=x, y=y, pressed=True, held=True, released=False)
    frame()
    ptr.update(pressed=False, held=False, released=True)
    frame()
    ptr.update(released=False)
    frame()


def drag(x, y0, y1, steps=8):
    settle()
    ptr.update(x=x, y=y0, pressed=True, held=True, released=False)
    frame()
    ptr.update(pressed=False)
    for i in range(1, steps + 1):
        ptr["y"] = y0 + (y1 - y0) * i // steps
        frame()
    ptr.update(held=False, released=True)
    frame()
    ptr.update(released=False)
    frame()


def tab(name):
    i = [n for n, _l in N.TABS].index(name)
    click(i * (N.SCREEN_W // len(N.TABS)) + 25, N.TAB_Y + 10)
    assert app.screen == name, (app.screen, name)


def row_y(i, top, scroll=0):
    return top + i * N.ROW_H + N.ROW_H // 2 - scroll


BUY = (N.SCREEN_W - 66 + 26, 40 + 96 + 4 + 10)      # ショップの「買う」ボタン
frame()
frame()
shot("01_yard_start")

# ------------------------------------------------------------ ショップ
tab("shop")
click(30, row_y(0, 40))
assert app.selected["shop"] == "rubber_ball"
settle(); frame(); shot("02_shop")
click(*BUY)
assert app.state["owned_toys"] == ["rubber_ball"], app.state["owned_toys"]
click(30, row_y(1, 40)); click(*BUY)                       # キラキラボール(金5)
click(30, row_y(2, 40)); click(*BUY)                       # 毛糸玉
assert len(app.state["owned_toys"]) == 3

click(126 + 29, 28)                                        # 絞り込み: すべて → 買える
assert app.shop_filter == 1
ids = app._shop_ids("toy")
assert "rubber_ball" not in ids and all(game.ITEMS[i]["cost"] <= app.state[game.ITEMS[i]["cur"] + "_fish"] for i in ids)
click(186 + 31, 28)                                        # 並べ替え: 標準 → 安い順
assert app.shop_sort == 1
settle(); frame(); shot("03_shop_filtered_sorted")
click(126 + 29, 28); click(126 + 29, 28)                   # 買える → 未所持 → すべて
click(186 + 31, 28); click(186 + 31, 28)                   # 安い順 → 高い順 → 標準
assert (app.shop_filter, app.shop_sort) == (0, 0)

drag(100, 120, 60)                                         # リストをドラッグでスクロール
assert app.scroll["shop"] > 0
click(8 + 26 + 54, 28)                                     # 「エサ」タブ
assert game.CATEGORIES[app.shop_kind][0] == "food"
click(30, row_y(0, 40)); click(*BUY)
assert app.state["food_stock"] == {"dry_food": 1}, app.state["food_stock"]
shot("04_shop_food")

# ------------------------------------------------------------ もちもの → 庭
tab("bag")
for i in range(3):
    click(30, row_y(i, 40))
assert len(app.state["yard"]) == 3
click(8 + 32 + 68, 28)                                     # エサのタブ
click(30, row_y(0, 40))
assert app.state["food"] == "dry_food"
shot("05_bag")
tab("yard")
for _ in range(120):
    T[0] += 60
    frame()
settle(); frame(); shot("06_yard_playing")
assert game.met_list(app.state), "猫が来ているはず"
n = len(app.state["pending_money"])
click(8 + 59, 194 + 10)                                    # さかなを受け取る
assert app.state["pending_money"] == [] or n == 0

# ------------------------------------------------------------ 図鑑(出会った順)
tab("cats")
met = game.met_list(app.state)
click(30, row_y(0, 38))
assert app.selected["cats"] == met[0]
settle(); frame(); shot("07_cats")
assert app.cat_pager.pages and app.cat_pager.key[1] == met[0]

# ------------------------------------------------------------ ヘルプ(タイプライター + ページ送り)
tab("help")
p = app.help_pager
assert p.typing, "ヘルプは1文字ずつ出るはず"
click(100, 100, settle_first=False)                        # 文字送り中のタップ: 全部出す(ページはそのまま)
assert not p.typing and p.page == 0
n_pages = len(p.pages)
print("help pages:", n_pages)
frame(); shot("08_help_p1")
if n_pages > 1:
    click(100, 100, settle_first=False)                    # 出し終えたあとのタップ: 次のページ
    assert p.page == 1
    settle(); frame(); shot("09_help_p2")
tab("yard")
tab("help")
assert p.page == 0 and p.typing                            # 開き直すと、また最初から

# ------------------------------------------------------------ 長い文章でも、枠からはみ出さない
tab("cats")
long_desc = "とても長い紹介文。" * 40
game.load_catalog(catalog.TOYS, catalog.FOODS, catalog.CATS + [("longcat", "ながいねこ", long_desc, "お" * 60)], catalog.CATEGORIES)
c = game.ensure_cat(app.state, "longcat")
c.update(met=True, total_time=5)
app.state["met_order"].append("longcat")
frame()
area = [a for a in app.areas if a[0] == "cats"][0]
app.scroll["cats"] = area[5]                                 # いちばん下までスクロールしておく
frame()
idx = game.met_list(app.state).index("longcat")
click(30, row_y(idx, 38, app.scroll["cats"]))
assert app.selected["cats"] == "longcat", app.selected
settle(); frame()
pg = app.cat_pager
print("long cat pages:", len(pg.pages))
assert len(pg.pages) >= 3
shot("10_cats_long_p1")
before = pg.page
pg._start_page()                                           # 1文字ずつ出ている最中にする
assert pg.typing
click(100, 130, settle_first=False)                        # 文字送り中のタップ: 全部出す(ページは進まない)
assert pg.page == before and not pg.typing
click(100, 130)                                            # 出し終え: 次のページ
assert pg.page == before + 1
settle(); frame(); shot("11_cats_long_p2")

# 伏せ字(お宝未取得)と明かした後で、行数・位置が同じ
lines_masked = [len(pg_) for pg_ in app.cat_pager.pages]
c["given_treasure"] = True
frame()
lines_revealed = [len(pg_) for pg_ in app.cat_pager.pages]
assert lines_masked == lines_revealed, (lines_masked, lines_revealed)

# ------------------------------------------------------------ 長いメッセージ
app.show_toast("とても長いお知らせ。" * 30)
assert app.message is not None and app.toast is None
frame(); settle(); frame(); shot("12_message_p1")
guard = 0
while app.message and guard < 30:
    click(100, 100)
    guard += 1
assert app.message is None, "最後のページのタップで閉じるはず"
app.show_toast("短いお知らせ")
assert app.message is None and app.toast is not None

# ------------------------------------------------------------ 猫1000匹・商品数百種類
toys = [("toy%03d" % i, "おもちゃ%d" % i, 5 + i % 90, "s" if i % 3 else "g", 1, "説明%d" % i) for i in range(600)]
cats = [("cat%04d" % i, "猫%d" % i, "紹介文%d" % i, "お宝%d" % i) for i in range(1000)]
categories = [("toy", "おもちゃ"), ("food", "エサ"), ("toy2", "とても長い種別名"), ("toy3", "種別4"), ("toy4", "種別5")]
game.load_catalog(toys, catalog.FOODS, cats, categories)
for i in range(300):
    cid = "cat%04d" % i
    game.ensure_cat(app.state, cid).update(met=True, total_time=i * 7)
    app.state["met_order"].append(cid)
app.state["met_order"] = [m for m in app.state["met_order"] if m.startswith("cat")]
for m in [k for k in list(app.state["cats"]) if not k.startswith("cat")]:
    del app.state["cats"][m]
app.selected["cats"] = None
app.scroll.clear()
frame()
n_rows = len(game.met_list(app.state)) + 1
maxs = n_rows * N.ROW_H - 4 * N.ROW_H
shot("13_cats_many_top")
drag(244, 40, 108)                                          # 右端のバーをつかんで一気に下へ
print("dex scroll:", app.scroll["cats"], "/", maxs)
assert app.scroll["cats"] > maxs * 0.9
frame(); shot("14_cats_many_bottom")
click(30, row_y(n_rows - 1, 38, app.scroll["cats"]))        # いちばん下は「あと◯匹」
assert app.selected["cats"] == N.UNMET_KEY
settle(); frame()
assert any("700" in line for pg_ in app.cat_pager.pages for line, _c in pg_)
click(30, row_y(n_rows - 2, 38, app.scroll["cats"]))
assert app.selected["cats"] == "cat0299"

tab("shop")
app.shop_kind = 0
app.scroll.clear()
frame()
ids = app._shop_ids("toy")
assert len(ids) == 600
app.toast = None
frame(); shot("15_shop_many_top")
drag(244, 42, 130)
print("shop scroll:", app.scroll["shop"])
assert app.scroll["shop"] > 600 * N.ROW_H * 0.85 - 96
frame(); shot("16_shop_many_bottom")
# 種別が多いときは ◀ ▶ でめくる
click(24 + 2 * 42 + 7, 28)                                   # ▶
assert app.shop_cat_off == 1
app.toast = None
frame(); shot("17_shop_categories_paged")
click(15, 28)                                                # ◀
assert app.shop_cat_off == 0
game.load_catalog(catalog.TOYS, catalog.FOODS, catalog.CATS, catalog.CATEGORIES)

# ------------------------------------------------------------ 保存
app.state["met_order"] = [m for m in app.state["met_order"] if m in game.CATS]
app.state["cats"] = {k: v for k, v in app.state["cats"].items() if k in game.CATS}
app.save()
assert os.path.exists(os.path.join(SAVE_DIR, "save.json"))
print("ALL UI CHECKS PASSED")
