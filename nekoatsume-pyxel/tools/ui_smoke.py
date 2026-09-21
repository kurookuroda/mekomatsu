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
drawn = []                       # 画面に描いた文字を全部覚えておく
_orig_tx = app.tx


def _tx(x, y, text, col=N.C_TEXT):
    drawn.append(text)
    _orig_tx(x, y, text, col)


app.tx = _tx
CATS_TOP = N.HEADER_H + 6          # 図鑑のリストの上端
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




class _Pos:
    """説明パネルのボタン位置(パネルの高さは説明の長さで変わるので、描画結果から取る)。"""
    def __init__(self, dx):
        self.dx = dx

    def __iter__(self):
        return iter((self.dx, app.shop_panel_y + 10))


BUY = _Pos(N.SHOP_BUY_X + 24)                          # 「買う」ボタン
CLOSE = _Pos(N.SHOP_CLOSE_X + 11)                      # 「×」(説明を閉じる)ボタン
frame()
frame()
shot("01_yard_start")

# ------------------------------------------------------------ ショップ
tab("shop")
# 最初は何も選ばれていない: 種別タブも商品も。説明パネルは無く、一覧が画面いっぱいに使える
assert app.shop_kind is None and app.selected["shop"] is None
assert app._shop_ids(None) == list(game.ITEMS)
frame()
assert not app.pager_regs, "説明パネルは閉じているはず"
assert app.areas[0][4] == N.TAB_Y - 4 - N.SHOP_TOP, "一覧は下端まで使う"
app.toast = None
frame(); shot("02_shop_initial")

click(30, row_y(0, N.SHOP_TOP))                            # 商品をタップ → 説明が開く
assert app.selected["shop"] == "rubber_ball" and app.pager_regs
assert app.areas[0][4] == app.shop_panel_y - 4 - N.SHOP_TOP < N.TAB_Y - 4 - N.SHOP_TOP, "説明が開くと、一覧はそのぶん狭くなる"
settle(); frame(); shot("02b_shop_open")
click(*CLOSE)                                              # × で閉じる
assert app.selected["shop"] is None
frame(); assert not app.pager_regs and app.areas[0][4] == N.TAB_Y - 4 - N.SHOP_TOP
click(30, row_y(0, N.SHOP_TOP)); assert app.selected["shop"] == "rubber_ball"
click(30, row_y(0, N.SHOP_TOP)); assert app.selected["shop"] is None    # 同じ商品をもう一度タップしても閉じる
click(30, row_y(0, N.SHOP_TOP))
click(*BUY)
assert app.state["owned_toys"] == ["rubber_ball"], app.state["owned_toys"]
click(30, row_y(1, N.SHOP_TOP)); click(*BUY)                # キラキラボール(金5)
click(30, row_y(2, N.SHOP_TOP)); click(*BUY)                # 毛糸玉
assert len(app.state["owned_toys"]) == 3

click(126 + 29, 28)                                        # 絞り込み: すべて → 買える
assert app.shop_filter == 1
ids = app._shop_ids(None)
assert "rubber_ball" not in ids and "dry_food" in ids
assert all(game.ITEMS[i]["cost"] <= app.state[game.ITEMS[i]["cur"] + "_fish"] for i in ids)
click(186 + 31, 28)                                        # 並べ替え: 標準 → 安い順
assert app.shop_sort == 1
settle(); frame(); shot("03_shop_filtered_sorted")
click(126 + 29, 28); click(126 + 29, 28)                   # 買える → 未所持 → すべて
click(186 + 31, 28); click(186 + 31, 28)                   # 安い順 → 高い順 → 標準
assert (app.shop_filter, app.shop_sort) == (0, 0)

# 条件を変えて一覧から消える商品の説明は、自動で閉じる
click(126 + 29, 28)                                        # 買える
click(30, row_y(0, N.SHOP_TOP))
sel = app.selected["shop"]
assert sel is not None
click(126 + 29, 28)                                        # 未所持
click(126 + 29, 28)                                        # すべて
app.selected["shop"] = "rubber_ball"                       # 買える に絞ると消える商品(持っている)を開いてから…
frame(); settle()                                          # (開いた直後は文字送り中で、タップは「全部出す」に使われるため)
click(126 + 29, 28)
frame()
assert app.selected["shop"] is None, ("一覧に無い商品の説明は閉じるはず", app.shop_filter, app.selected["shop"], "rubber_ball" in app._shop_ids(None), app.state["owned_toys"])
click(126 + 29, 28); click(126 + 29, 28)                   # 未所持 → すべて に戻す
assert app.shop_filter == 0

drag(100, 120, 60)                                         # リストをドラッグでスクロール(説明が閉じているとき)
assert app.scroll["shop"] > 0
click(8 + 26 + 54, 28)                                     # 「エサ」タブ
assert game.CATEGORIES[app.shop_kind][0] == "food"
click(8 + 26 + 54, 28)                                     # もう一度押すと解除(すべて表示)に戻る
assert app.shop_kind is None
click(8 + 26 + 54, 28)
click(30, row_y(0, N.SHOP_TOP)); click(*BUY)
assert app.state["food_stock"] == {"dry_food": 1}, app.state["food_stock"]
shot("04_shop_food")
click(8 + 26 + 54, 28)                                     # 解除しておく
click(*CLOSE) if app.selected["shop"] else None

# ------------------------------------------------------------ もちもの → 庭
tab("bag")
assert app.sub["bag"] is None                              # 最初は何も押されていない(持っているものぜんぶ: おもちゃ→エサ)
for i in range(3):
    click(30, row_y(i, 40))
assert len(app.state["yard"]) == 3
click(30, row_y(3, 40))                                    # 4行目は、エサ(ドライフード)
assert app.state["food"] == "dry_food"
click(8 + 32, 28); assert app.sub["bag"] == 0              # おもちゃのタブ
click(8 + 32 + 68, 28); assert app.sub["bag"] == 1         # エサのタブ
click(8 + 32 + 68, 28); assert app.sub["bag"] is None      # もう一度押すと解除
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
click(30, row_y(0, CATS_TOP))
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
    assert p.page == 1 and p.back_rect is None or p.page == 1
    settle(); frame(); shot("09_help_p2")
    assert p.back_rect is not None, "2ページ目には ◀ が出るはず"
    bx, by, bw, bh = p.back_rect
    click(bx + bw // 2, by + bh // 2)                      # ◀ をタップ: 前のページへ
    assert p.page == 0 and not p.typing, (p.page, p.typing)  # 読んだページは、すぐ全部出る
    frame(); assert p.back_rect is None, "1ページ目には ◀ は出ない"
    keys.add("KEY_RIGHT"); frame(); keys.clear()           # → キー: 次のページへ
    assert p.page == 1
    keys.add("KEY_LEFT"); frame(); keys.clear()            # ← キー: 前のページへ
    assert p.page == 0
    click(100, 100)                                        # もう一度進んで、次の確認へ
    assert p.page == 1
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
click(30, row_y(idx, CATS_TOP, app.scroll["cats"]))
assert app.selected["cats"] == "longcat", app.selected
settle(); frame()
pg = app.cat_pager
print("long cat pages:", len(pg.pages))
assert len(pg.pages) >= 3
shot("10_cats_long_p1")
before = pg.page
pg.seen = pg.page - 1                                      # まだ読んでいないページとして、
pg._start_page()                                           # 1文字ずつ出ている最中にする
assert pg.typing
click(100, 130, settle_first=False)                        # 文字送り中のタップ: 全部出す(ページは進まない)
assert pg.page == before and not pg.typing
click(100, 130)                                            # 出し終え: 次のページ
assert pg.page == before + 1
settle(); frame(); shot("11_cats_long_p2")
click(100, 130)                                            # さらに次のページ(3/5)
assert pg.page == before + 2
settle(); frame(); shot("11b_cats_long_p3")
bx, by, bw, bh = pg.back_rect
click(bx + bw // 2, by + bh // 2)                          # ◀: 2/5 に戻る
assert pg.page == before + 1 and not pg.typing
click(bx + bw // 2, by + bh // 2)                          # ◀: 1/5 に戻る
assert pg.page == before and pg.back_rect is None or pg.page == before
click(100, 130)                                            # 読んだページをまた進む: すぐ全部出る
assert pg.page == before + 1 and not pg.typing

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
mp = app.message["pager"]
click(100, 100)                                            # 2ページ目へ
assert mp.page == 1 and app.message is not None
settle(); frame()
bx, by, bw, bh = mp.back_rect
click(bx + bw // 2, by + bh // 2)                          # ◀ で1ページ目へ戻る(閉じない)
assert mp.page == 0 and app.message is not None
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
n_rows = len(game.met_list(app.state))
maxs = n_rows * N.ROW_H - 4 * N.ROW_H
shot("13_cats_many_top")
drag(244, CATS_TOP + 2, CATS_TOP + 4 * N.ROW_H - 2)         # 右端のバーをつかんで一気に下へ
print("dex scroll:", app.scroll["cats"], "/", maxs)
assert app.scroll["cats"] > maxs * 0.9
frame(); shot("14_cats_many_bottom")
click(30, row_y(n_rows - 1, CATS_TOP, app.scroll["cats"]))    # いちばん下の猫(出会った順の最後)
assert app.selected["cats"] == "cat0299"
settle(); frame()

tab("shop")
app.shop_kind = 0
app.scroll.clear()
app.selected["shop"] = None
app.shop_filter = app.shop_sort = 0
frame()
ids = app._shop_ids("toy")
assert len(ids) == 600
app.toast = None
frame(); shot("15_shop_many_top")
full_h = N.TAB_Y - 4 - N.SHOP_TOP
drag(244, N.SHOP_TOP + 2, N.TAB_Y - 6)                      # 右端のバーをつかんで一気に下へ(説明は閉じている)
maxs = 600 * N.ROW_H - full_h
print("shop scroll:", app.scroll["shop"], "/", maxs)
assert app.scroll["shop"] > maxs * 0.9
frame(); shot("16_shop_many_bottom")
# 下のほうの商品を選ぶと、説明が開いて一覧が狭くなる。それでも選んだ行は見える位置に寄る
click(30, row_y(599, N.SHOP_TOP, app.scroll["shop"]))
assert app.selected["shop"] == "toy599", app.selected["shop"]
frame(); frame()
narrow_h = app.shop_panel_y - 4 - N.SHOP_TOP
top, off = 599 * N.ROW_H, app.scroll["shop"]
assert off <= top and top + N.ROW_H <= off + narrow_h, (off, top, narrow_h)
settle(); frame(); shot("16b_shop_many_open")
click(*CLOSE)
assert app.selected["shop"] is None
# 種別が多いときは ◀ ▶ でめくる
click(24 + 2 * 42 + 7, 28)                                   # ▶
assert app.shop_cat_off == 1
app.toast = None
frame(); shot("17_shop_categories_paged")
click(15, 28)                                                # ◀
assert app.shop_cat_off == 0
app.shop_kind = None
game.load_catalog(catalog.TOYS, catalog.FOODS, catalog.CATS, catalog.CATEGORIES)

# ------------------------------------------------------------ ネタバレになる表示が出ていないこと
FORBIDDEN = ["3000", "累計", "あと", "未発見", "出会った猫", "全部で", "匹いる", "？？？(", "0/5", "/1000"]
bad = sorted({t for t in drawn if any(w in t for w in FORBIDDEN)})
assert not bad, bad

# ------------------------------------------------------------ 保存
app.state["met_order"] = [m for m in app.state["met_order"] if m in game.CATS]
app.state["cats"] = {k: v for k, v in app.state["cats"].items() if k in game.CATS}
app.save()
assert os.path.exists(os.path.join(SAVE_DIR, "save.json"))
print("ALL UI CHECKS PASSED")
