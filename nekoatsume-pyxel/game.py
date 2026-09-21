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
"""

import json
import random
import time
from collections import namedtuple

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


ITEMS = {
    "rubber_ball": _toy("ゴムボール", 5, "s", 1, "小さな明るいオレンジ色のゴムボール。ふにふにで、ピコピコ鳴るよ!"),
    "sparkle_ball": _toy("キラキラボール", 5, "g", 1, "きらめくラメが入った、小さな透明のゴムボール!"),
    "yarn_ball": _toy("毛糸玉", 10, "s", 1, "赤い毛糸玉だよ!"),
    "fancy_yarn_ball": _toy("高級毛糸玉", 15, "g", 1, "赤・青・緑に銀色の糸がきらめく、高級な毛糸玉!"),
    "tennis_ball": _toy("テニスボール", 25, "s", 1, "毛羽立った鮮やかな黄色のテニスボール!"),
    "paper_bag": _toy("紙袋", 20, "s", 1, "スーパーの紙袋。ガサガサいい音がするよ!"),
    "scratching_post": _toy("爪とぎポール", 5, "g", 1, "猫がバリバリ爪をとげる、いい感じのポール!"),
    "fancy_scratching_post": _toy("高級爪とぎポール", 15, "g", 1, "硬い木と合成皮革でできた、デラックスな爪とぎポール!"),
    "fishbowl": _toy("金魚鉢", 10, "g", 1, "かわいい金魚が泳ぐ小さな金魚鉢!"),
    "small_condo": _toy("小型キャットハウス", 75, "s", 3, "少しだけカーペット張りの小さなキャットハウス。3匹まで入れるよ!"),
    "medium_condo": _toy("中型キャットハウス", 150, "s", 5, "全面カーペット張りの中くらいのキャットハウス。5匹まで入れるよ!"),
    "large_condo": _toy("大型キャットハウス", 50, "g", 6, "高級ベルベル絨毯に手縫いの仕上げ、6匹まで入れる大きなキャットハウス!"),
    "catnip": _toy("マタタビの袋", 7, "g", 1, "小さなマタタビの袋。においで猫が大興奮!"),
    "plain_pillow": _toy("無地のクッション", 30, "s", 1, "青くてやわらかい、小さな無地のクッション!"),
    "tie_dye_pillow": _toy("絞り染めのクッション", 15, "g", 1, "絞り染めのフリースでできた、ふかふかの厚いクッション!"),
    "plastic_bucket": _toy("プラスチックのバケツ", 20, "s", 1, "白い取っ手のついた小さな緑のバケツ。バケツがあるぞ!"),
    "cereal_box": _toy("シリアルの箱", 15, "s", 1, "「シナモンとろけるゴロゴロ」の空き箱!"),
    "fruit_box": _toy("果物の箱", 75, "s", 1, "小さな段ボールの果物箱。入れそうなら、入っちゃう!"),
    "large_box": _toy("大きな箱", 30, "g", 4, "もとは家電が入っていた大きな段ボール箱。猫が4匹まで入れるよ!"),
    "butterfly_toy": _toy("蝶々のおもちゃ", 15, "g", 1, "長い棒の先の糸に蝶々がぶら下がった、かわいいおもちゃ。ひらひら楽しい!"),
    "laser_pointer": _toy("ロボットレーザーポインター", 125, "g", 1, "レーザーポインターを持った小さなロボットアーム。みんな大好き!"),
    "rainbow_umbrella": _toy("虹色の傘", 25, "g", 5, "虹色もようの大きな傘。猫が5匹まで入れるよ!"),
    "plain_umbrella": _toy("無地の傘", 250, "s", 4, "明るい黄色の大きな無地の傘。猫が4匹まで入れるよ!"),
    "plush_froggy": _toy("カエルのぬいぐるみ", 75, "s", 1, "ぎゅっとすると鳴く、緑のかわいいカエルのぬいぐるみ!"),
    "dry_food": _food("ドライフード", 10, "s", 300, "ごく普通のドライフード。カリカリでシンプルな味。"),
    "wet_food": _food("ウェットフード缶", 2, "g", 300, "ごく普通のウェットフード。においが強烈!"),
    "fancy_food": _food("高級フード缶", 5, "g", 300, "職人が手づくりした、フェアトレードのオーガニック猫ごはん。んー、おいしい!"),
}
TOYS = {k: v for k, v in ITEMS.items() if v["kind"] == "toy"}
FOODS = {k: v for k, v in ITEMS.items() if v["kind"] == "food"}


def _cat(name, desc, treasure, strength=5, entry_chance=0.1, time_limit=30, fav_toy="", exclusive=False):
    return {"name": name, "desc": desc, "treasure": treasure, "strength": strength,
            "entry_chance": entry_chance, "time_limit": time_limit,
            "fav_toy": fav_toy, "exclusive": exclusive}


CATS = {
    "gordo": _cat("ゴードー", "いつもあなたのごはんを食べにくる、いちばん手のかかる猫", "役に立たない木切れ(ゴードーだから)"),
    "pukka": _cat("プッカ", "クリーム色のぶちがある白い短毛で、緑の目の猫。レーザーを追いかけたり、サーフィンをするのが大好き", "サーフワックスのかたまり"),
    "peebles": _cat("ピーブルズ", "青い目の白黒の短毛猫。デスメタルとマタタビの山が好き", "べっ甲のギターピック"),
    "tarawa": _cat("タラワ", "白い筋の入ったグレーの長毛で、灰色の目の猫。のんびりするのと、鳥を追いかけるのが好き", "アオカケスの羽根", strength=6),
    "felix": _cat("フェリックス", "オレンジと白の短毛のトラ猫で、黄色い目。とてもおだやかで、一日中ほとんど瞑想している", "仏像のお香立て"),
}


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
        "cats": {cid: _new_cat() for cid in CATS},
        "pending_money": [],       # [猫ID, 量, "s"/"g"]
        "pending_treasures": [],   # 猫ID
        "last_tick": now,
        "last_seen": now,
    }


def space_used(state):
    return sum(TOYS[t]["size"] for t in state["yard"])


def occupants(state, toy_id):
    return list(state["occ"].get(toy_id, []))


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
    # 「庭にいない猫」は先に確定する(この tick で帰った猫は同 tick に再入場しない)
    candidates = [cid for cid, c in cats.items() if not c["in_yard"]]
    for cid in cats_in_yard(state):
        c = cats[cid]
        c["time_in_yard"] += 1
        if _time_to_leave(c, CATS[cid], rng):
            _leave(state, cid, rng, ev)
    if state["food"]:
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
    c = state["cats"][cid]
    state["occ"][toy].append(cid)
    c["in_yard"] = True
    c["toy"] = toy
    c["met"] = True
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
    for cid in CATS:
        c = _new_cat()
        src = saved_cats.get(cid, {})
        if isinstance(src, dict):
            c["in_yard"] = bool(src.get("in_yard", False))
            c["toy"] = src.get("toy", "") if isinstance(src.get("toy", ""), str) else ""
            c["time_in_yard"] = _int(src.get("time_in_yard", 0))
            c["total_time"] = _int(src.get("total_time", 0))
            c["given_treasure"] = bool(src.get("given_treasure", False))
            # met が無い旧セーブでも、遊んだ形跡があれば「出会い済み」扱いにする
            c["met"] = bool(src.get("met", False)) or c["in_yard"] \
                or c["total_time"] > 0 or c["given_treasure"]
        cats[cid] = c
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
