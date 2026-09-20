"""
ねこあつめ Pyxel 版 ― ゲームロジック(Pyxel に依存しない純粋な Python)

元のコンソール版(nekoatsume_py)の update.py / yard.py / buy_menu.py の挙動を、
表示や入力から切り離して移植したもの。UI は nekoatsume.py 側が担当する。

時間モデル
    1 tick = 60 秒(実時間)。advance() が「前回から経過した実時間」ぶんの tick を進める。
    起動時の一括計算(離席中の分)も、起動中のリアルタイム進行も、同じ関数で処理する。

元のコードからの意図的な変更点(README にも記載)
    1. 庭の容量判定を `<` から `<=` にした(元は 6 マスあっても 5 マスしか使えなかった)
    2. 大型キャットハウスをサイズ 7 → 6 にした(元は置けず、エサ扱いで購入されるバグがあった)
    3. アイテム種別(toy / food)を size の閾値ではなく kind で判定する
    4. 内部IDと表示名を分離した(セーブデータのキーは ID)
    5. おもちゃを庭から外したとき、遊んでいた猫はさかなを置いて帰る(元は無報酬で追い出していた)

規模への備え(猫が1000匹、商品が数百種類になっても困らないように)
    - アイテムと猫のデータは catalog.py の表にある(コードに埋め込まない)。load_catalog() で差し替えもできる
    - セーブに入る猫の状態は「出会った猫」だけ(未発見の猫は状態を持たない)。出会った順は met_order
    - 猫の来訪判定は、エサとおもちゃがあるときだけ行う。候補が多いときは順番をシャッフルして偏りをなくす
    - ショップの絞り込み・並べ替えは shop_ids() にまとめた(UI は表示だけ)
"""

import json
import random
import time
from collections import namedtuple

import catalog

VERSION = 1

SPACE = 6                      # 庭のマス数
TICK_SECONDS = 60              # 1 tick の実時間
MAX_CATCHUP_TICKS = 60 * 24 * 30   # 極端に長い離席・時計ずれの上限(30日分)
TREASURE_MINUTES = 3000        # 累計滞在がこれを超えるとお宝を持ってくる
GOLD_ONE_IN = 30               # 報酬が金になる確率(1/N)
WEEK_SECONDS = 7 * 24 * 3600

Result = namedtuple("Result", "ok code msg")


# ---------------------------------------------------------------- カタログ
def _toy(name, cost, cur, size, desc):
    return {"kind": "toy", "name": name, "cost": cost, "cur": cur, "size": size, "desc": desc}


def _food(name, cost, cur, minutes, desc):
    return {"kind": "food", "name": name, "cost": cost, "cur": cur, "size": minutes, "desc": desc}


def _cat(name, desc, treasure, strength=5, entry_chance=0.1, time_limit=30, fav_toy="", exclusive=False):
    return {"name": name, "desc": desc, "treasure": treasure, "strength": strength,
            "entry_chance": entry_chance, "time_limit": time_limit,
            "fav_toy": fav_toy, "exclusive": exclusive}


# load_catalog() が埋める。他のモジュールは game.ITEMS のように、使う時に参照すること(差し替えに追従するため)
ITEMS = {}          # アイテムID -> 仕様(おもちゃとエサ。表の並び順)
TOYS = {}
FOODS = {}
IDS_BY_KIND = {}    # 種別 -> アイテムIDのリスト(表の並び順)
CATS = {}           # 猫ID -> 仕様(表の並び順)
CATEGORIES = []     # ショップの種別 [(種別ID, 表示名)]
CATALOG_VERSION = 0     # load_catalog() のたびに増える(UI 側のキャッシュ無効化用)


def load_catalog(toys, foods, cats, categories):
    """アイテムと猫のデータ表を読み込む(既定は catalog.py)。ID の重複や不正な値は ValueError。"""
    global ITEMS, TOYS, FOODS, IDS_BY_KIND, CATS, CATEGORIES, CATALOG_VERSION
    items, cat_specs = {}, {}
    for row in toys:
        iid = row[0]
        if iid in items:
            raise ValueError("duplicate item id: %s" % iid)
        items[iid] = _toy(*row[1:])
    for row in foods:
        iid = row[0]
        if iid in items:
            raise ValueError("duplicate item id: %s" % iid)
        items[iid] = _food(*row[1:])
    for row in cats:
        cid, name, desc, treasure = row[:4]
        if cid in cat_specs:
            raise ValueError("duplicate cat id: %s" % cid)
        cat_specs[cid] = _cat(name, desc, treasure, **(row[4] if len(row) > 4 else {}))
    for iid, it in items.items():
        if it["cur"] not in ("s", "g") or it["cost"] <= 0 or it["size"] < 1:
            raise ValueError("bad item: %s" % iid)
        if it["kind"] == "toy" and it["size"] > SPACE:
            raise ValueError("toy does not fit in the yard: %s" % iid)
    kinds = [k for k, _label in categories]
    ids_by_kind = {k: [] for k in kinds}
    for iid, it in items.items():
        if it["kind"] not in ids_by_kind:
            raise ValueError("item %s has no category" % iid)
        ids_by_kind[it["kind"]].append(iid)
    ITEMS = items
    TOYS = {k: v for k, v in items.items() if v["kind"] == "toy"}
    FOODS = {k: v for k, v in items.items() if v["kind"] == "food"}
    IDS_BY_KIND = ids_by_kind
    CATS = cat_specs
    CATEGORIES = list(categories)
    CATALOG_VERSION += 1


load_catalog(catalog.TOYS, catalog.FOODS, catalog.CATS, catalog.CATEGORIES)


def cur_name(cur):
    return "銀" if cur == "s" else "金"


def price_text(item_id):
    it = ITEMS[item_id]
    return "{0}{1}".format(cur_name(it["cur"]), it["cost"])


# ---------------------------------------------------------------- 状態
def _new_cat():
    return {"in_yard": False, "toy": "", "time_in_yard": 0, "total_time": 0,
            "given_treasure": False, "met": False}


def new_state(now=None):
    now = time.time() if now is None else now
    return {
        "version": VERSION,
        "s_fish": 300,
        "g_fish": 10,
        "owned_toys": [],          # 持っているおもちゃID
        "yard": [],                # 庭に置いてあるおもちゃID(置いた順)
        "occ": {},                 # おもちゃID -> 遊んでいる猫ID(入った順)
        "food_stock": {},          # エサID -> 個数
        "food": "",                # 庭に出ているエサID
        "food_remaining": 0,       # 残り分(tick)
        "cats": {},                # 出会った猫だけ(猫ID -> 状態)。猫が何匹いても、セーブは出会った分だけで済む
        "met_order": [],           # 出会った順(図鑑の並び)
        "pending_money": [],       # [猫ID, 量, "s"/"g"]
        "pending_treasures": [],   # 猫ID
        "last_tick": now,
        "last_seen": now,
    }


def space_used(state):
    return sum(TOYS[t]["size"] for t in state["yard"])


def occupants(state, toy_id):
    return list(state["occ"].get(toy_id, []))


def ensure_cat(state, cid):
    """猫の状態を返す。まだ無ければ既定値で作る(出会い済みにはしない)。"""
    c = state["cats"].get(cid)
    if c is None:
        c = state["cats"][cid] = _new_cat()
    return c


def met_list(state):
    """出会った猫を、出会った順に返す(図鑑の並び)。"""
    return list(state["met_order"])


def cats_in_yard(state):
    return [cid for cid, c in state["cats"].items() if c["in_yard"]]


def fish(state, cur):
    return state[cur + "_fish"]


# ---------------------------------------------------------------- 時間経過
def advance(state, now, rng=random):
    """実時間 now に合わせて tick を進める。

    戻り値: {"ticks": 進めたtick数, "visits": 来訪回数, "events": 直近のイベント(最大50件)}
    経過が 1 tick 未満なら何も起きない(端数は次回に持ち越す)。
    """
    elapsed = now - state["last_tick"]
    if elapsed < 0:                      # 時計が巻き戻された
        state["last_tick"] = now
        elapsed = 0
    n = int(elapsed // TICK_SECONDS)
    events = []
    if n > MAX_CATCHUP_TICKS:
        n = MAX_CATCHUP_TICKS
        state["last_tick"] = now
    else:
        state["last_tick"] += n * TICK_SECONDS
    for _ in range(n):
        tick(state, rng, events)
    state["last_seen"] = now
    visits = sum(1 for e in events if e[0] == "arrive")
    return {"ticks": n, "visits": visits, "events": events[-50:]}


def resume(state, now, rng=random):
    """アプリ起動時の処理。離席中の分を進め、起動ボーナスのお宝抽選を行う。"""
    prev_seen = state["last_seen"]
    report = advance(state, now, rng)
    report["bonus_treasure"] = launch_bonus(state, prev_seen, now, rng)
    return report


def tick(state, rng=random, events=None):
    """1 分ぶん進める(元の update.tick と同じ順序)。"""
    ev = events if events is not None else []
    cats = state["cats"]
    # 「庭にいる猫」を先に確定する(この tick で帰った猫は同 tick に再入場しない)
    in_yard = set(cats_in_yard(state))
    for cid in list(in_yard):
        c = cats[cid]
        c["time_in_yard"] += 1
        if _time_to_leave(c, CATS[cid], rng):
            _leave(state, cid, rng, ev)
    if state["food"]:
        if state["yard"]:                      # おもちゃが無ければ、誰も来ないので判定しない
            candidates = [cid for cid in CATS if cid not in in_yard]
            if len(candidates) > 8:            # 猫が多いとき、先頭の猫ばかり席を取らないように順番を混ぜる
                rng.shuffle(candidates)
            for cid in candidates:
                if rng.random() < CATS[cid]["entry_chance"]:
                    toy = _pick_toy(state, cid, rng)
                    if toy is None:
                        continue
                    if len(state["occ"][toy]) < TOYS[toy]["size"]:
                        _join(state, cid, toy, ev)
                    else:
                        _try_push(state, cid, toy, rng, ev)
        _reduce_food(state, ev)


def _time_to_leave(cat, spec, rng):
    upper = rng.randint(10, 20)
    lower = rng.randint(2, 7)
    return rng.randint(lower, upper) + cat["time_in_yard"] > spec["time_limit"]


def _pick_toy(state, cid, rng):
    toys = state["yard"]
    if not toys:
        return None
    spec = CATS[cid]
    if spec["exclusive"]:
        return spec["fav_toy"] if spec["fav_toy"] in toys else None
    return rng.choice(toys)


def _join(state, cid, toy, events):
    c = ensure_cat(state, cid)
    state["occ"][toy].append(cid)
    c["in_yard"] = True
    c["toy"] = toy
    if not c["met"]:                       # 図鑑での位置は「はじめて庭に来た順」で、このとき決まる
        c["met"] = True
        state["met_order"].append(cid)
        events.append(("met", cid))
    events.append(("arrive", cid, toy))
    if c["total_time"] > TREASURE_MINUTES and not c["given_treasure"]:
        c["given_treasure"] = True
        state["pending_treasures"].append(cid)
        events.append(("treasure", cid))


def _try_push(state, cid, toy, rng, events):
    for other in list(state["occ"][toy]):
        if CATS[other]["strength"] < CATS[cid]["strength"]:
            _leave(state, other, rng, events)
            _join(state, cid, toy, events)
            return


def _leave(state, cid, rng, events):
    c = state["cats"][cid]
    toy = c["toy"]
    if cid in state["occ"].get(toy, []):
        state["occ"][toy].remove(cid)
    amount = int(round(c["time_in_yard"] * (rng.randint(5, 10) / 10.0)))
    cur = "g" if rng.randint(1, GOLD_ONE_IN) == 1 else "s"
    state["pending_money"].append([cid, amount, cur])
    events.append(("leave", cid, toy, amount, cur))
    c["total_time"] += c["time_in_yard"]
    c["time_in_yard"] = 0
    c["in_yard"] = False
    c["toy"] = ""


def _reduce_food(state, events):
    if state["food_remaining"] > 0:
        state["food_remaining"] = max(state["food_remaining"] - 1, 0)
        if state["food_remaining"] == 0:
            state["food"] = ""
            events.append(("food_out",))
    else:
        state["food"] = ""


def launch_bonus(state, prev_seen, now, rng=random):
    """起動時のお宝抽選(元の bestow_treasures)。離席が長いほど当たりやすい(5%〜10%)。"""
    not_given = [cid for cid, c in state["cats"].items()
                 if c["total_time"] > 0 and not c["given_treasure"]]
    if not not_given:
        return None
    absent = max(0.0, now - prev_seen) / WEEK_SECONDS
    prob = 0.05 + 0.05 * min(1.0, absent)
    if rng.random() >= prob:
        return None
    giver = rng.choice(not_given)
    state["cats"][giver]["given_treasure"] = True
    state["pending_treasures"].append(giver)
    return giver


# ---------------------------------------------------------------- プレイヤー操作
def buy(state, item_id):
    it = ITEMS.get(item_id)
    if it is None:
        return Result(False, "unknown", "そんな商品はありません")
    if it["kind"] == "toy" and item_id in state["owned_toys"]:
        return Result(False, "owned", "もう持っています")
    key = it["cur"] + "_fish"
    if state[key] < it["cost"]:
        return Result(False, "no_money", "ごめんなさい、お金が足りません!")
    state[key] -= it["cost"]
    if it["kind"] == "toy":
        state["owned_toys"].append(item_id)
    else:
        state["food_stock"][item_id] = state["food_stock"].get(item_id, 0) + 1
    return Result(True, "ok", "まいど! すばらしい選択です!")


def place_toy(state, toy_id):
    if toy_id not in state["owned_toys"]:
        return Result(False, "not_owned", "そのおもちゃは持っていません")
    if toy_id in state["yard"]:
        return Result(False, "placed", "もう庭に置いてあります")
    if space_used(state) + TOYS[toy_id]["size"] > SPACE:
        return Result(False, "no_room", "庭がいっぱいです。先にどれかを外してください")
    state["yard"].append(toy_id)
    state["occ"][toy_id] = []
    return Result(True, "ok", "{0}を庭に置きました".format(TOYS[toy_id]["name"]))


def remove_toy(state, toy_id, rng=random, events=None):
    if toy_id not in state["yard"]:
        return Result(False, "not_placed", "庭に置いていません")
    ev = events if events is not None else []
    for cid in list(state["occ"].get(toy_id, [])):
        _leave(state, cid, rng, ev)
    state["yard"].remove(toy_id)
    state["occ"].pop(toy_id, None)
    return Result(True, "ok", "{0}を庭から外しました".format(TOYS[toy_id]["name"]))


def set_food(state, food_id, force=False):
    if food_id not in FOODS or state["food_stock"].get(food_id, 0) <= 0:
        return Result(False, "no_stock", "そのエサは持っていません")
    if state["food_remaining"] > 0 and not force:
        return Result(False, "need_confirm",
                      "庭のエサ(残り{0}分)は捨てられます。置き換えますか?".format(state["food_remaining"]))
    state["food_stock"][food_id] -= 1
    if state["food_stock"][food_id] <= 0:
        del state["food_stock"][food_id]
    state["food"] = food_id
    state["food_remaining"] = FOODS[food_id]["size"]
    return Result(True, "ok", "{0}を置きました(残り{1}分)".format(FOODS[food_id]["name"], state["food_remaining"]))


SHOP_FILTERS = (("all", "すべて"), ("buyable", "買える"), ("unowned", "未所持"))
SHOP_SORTS = (("catalog", "標準"), ("price_asc", "安い順"), ("price_desc", "高い順"))


def shop_ids(state, kind, filt="all", sort="catalog"):
    """ショップに並べるアイテムIDを、絞り込み・並べ替え済みで返す。
    filt: all=すべて / buyable=いま買える(所持金が足り、持っていない) / unowned=持っていない
    sort: catalog=表の順 / price_asc=安い順 / price_desc=高い順(銀→金の順に、値段で比べる)
    """
    ids = list(IDS_BY_KIND.get(kind, []))
    if filt != "all":
        owned = set(state["owned_toys"])
        stock = state["food_stock"]

        def have(i):
            return (i in owned) if kind == "toy" else stock.get(i, 0) > 0

        if filt == "unowned":
            ids = [i for i in ids if not have(i)]
        elif filt == "buyable":
            ids = [i for i in ids
                   if not (kind == "toy" and have(i)) and state[ITEMS[i]["cur"] + "_fish"] >= ITEMS[i]["cost"]]
    if sort in ("price_asc", "price_desc"):
        ids.sort(key=lambda i: (0 if ITEMS[i]["cur"] == "s" else 1, ITEMS[i]["cost"]),
                 reverse=(sort == "price_desc"))
    return ids


def collect(state):
    """猫たちが置いていったさかなを受け取る。[(猫ID, 量, 通貨)] を返す。"""
    got = [tuple(m) for m in state["pending_money"]]
    state["pending_money"] = []
    for _cid, amount, cur in got:
        state[cur + "_fish"] += amount
    return got


def collect_treasures(state):
    got = list(state["pending_treasures"])
    state["pending_treasures"] = []
    return got


def treasures_owned(state):
    return [cid for cid, c in state["cats"].items() if c["given_treasure"]]


# ---------------------------------------------------------------- 保存・読み込み
def dumps(state):
    return json.dumps(state, ensure_ascii=False)


def loads(text, now=None):
    """JSON 文字列から状態を復元する。壊れた値は補正し、形式が違えば ValueError。"""
    raw = json.loads(text)
    if not isinstance(raw, dict) or raw.get("version") != VERSION:
        raise ValueError("unsupported save data")
    state = new_state(now)
    for k in state:
        if k in raw:
            state[k] = raw[k]
    _sanitize(state, raw)
    return state


def _int(v, default=0):
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return default


def _float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _sanitize(state, raw):
    for key in ("s_fish", "g_fish", "food_remaining"):
        state[key] = _int(state[key])
    now = time.time()
    state["last_tick"] = _float(state["last_tick"], now)
    state["last_seen"] = _float(state["last_seen"], now)

    owned = []
    for t in state["owned_toys"] if isinstance(state["owned_toys"], list) else []:
        if t in TOYS and t not in owned:
            owned.append(t)
    state["owned_toys"] = owned

    yard = []
    for t in state["yard"] if isinstance(state["yard"], list) else []:
        if t in owned and t not in yard and sum(TOYS[x]["size"] for x in yard) + TOYS[t]["size"] <= SPACE:
            yard.append(t)
    state["yard"] = yard

    stock = {}
    if isinstance(state["food_stock"], dict):
        for k, v in state["food_stock"].items():
            if k in FOODS and _int(v) > 0:
                stock[k] = _int(v)
    state["food_stock"] = stock
    if state["food"] not in FOODS or state["food_remaining"] <= 0:
        state["food"], state["food_remaining"] = "", 0

    saved_cats = state["cats"] if isinstance(state["cats"], dict) else {}
    saved_occ = state["occ"] if isinstance(state["occ"], dict) else {}
    cats = {}
    for cid, src in saved_cats.items():
        if cid not in CATS or not isinstance(src, dict):
            continue
        c = _new_cat()
        c["in_yard"] = bool(src.get("in_yard", False))
        c["toy"] = src.get("toy", "") if isinstance(src.get("toy", ""), str) else ""
        c["time_in_yard"] = _int(src.get("time_in_yard", 0))
        c["total_time"] = _int(src.get("total_time", 0))
        c["given_treasure"] = bool(src.get("given_treasure", False))
        # met が無い旧セーブでも、遊んだ形跡があれば「出会い済み」扱いにする
        c["met"] = bool(src.get("met", False)) or c["in_yard"] \
            or c["total_time"] > 0 or c["given_treasure"]
        if c["met"]:                       # 出会っていない猫の状態は持たない(旧セーブの全員分の既定値は捨てる)
            cats[cid] = c
    met_order = []
    for cid in (state["met_order"] if isinstance(state["met_order"], list) else []):
        if cid in cats and cid not in met_order:
            met_order.append(cid)
    met_order.extend(cid for cid in cats if cid not in met_order)   # 順番が不明な旧セーブ分は、後ろに足す
    state["met_order"] = met_order
    occ = {t: [] for t in yard}
    order = []
    for t in yard:
        lst = saved_occ.get(t, [])
        if isinstance(lst, list):
            order.extend(cid for cid in lst if cid in cats)
    order.extend(cid for cid in cats if cid not in order)
    for cid in order:
        c = cats[cid]
        t = c["toy"]
        if c["in_yard"] and t in occ and cid not in occ[t] and len(occ[t]) < TOYS[t]["size"]:
            occ[t].append(cid)
        elif not (c["in_yard"] and t in occ and cid in occ[t]):
            c["in_yard"], c["toy"], c["time_in_yard"] = False, "", 0
    state["occ"] = occ
    state["cats"] = cats

    money = []
    for m in state["pending_money"] if isinstance(state["pending_money"], list) else []:
        if isinstance(m, (list, tuple)) and len(m) == 3 and m[0] in CATS and m[2] in ("s", "g"):
            money.append([m[0], _int(m[1]), m[2]])
    state["pending_money"] = money
    state["pending_treasures"] = [c for c in (state["pending_treasures"]
                                              if isinstance(state["pending_treasures"], list) else [])
                                  if c in CATS]
