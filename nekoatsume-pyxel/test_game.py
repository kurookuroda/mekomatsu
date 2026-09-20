"""game.py のテスト。 実行: pytest -q"""
import json
import random
import statistics

import pytest

import game

T0 = 1_000_000.0


def fresh():
    return game.new_state(T0)


def stocked(toys=("rubber_ball", "yarn_ball", "cereal_box", "plastic_bucket", "paper_bag")):
    s = fresh()
    for t in toys:
        s["owned_toys"].append(t)
        assert game.place_toy(s, t).ok
    s["food_stock"]["dry_food"] = 1
    assert game.set_food(s, "dry_food").ok
    return s


# ---------------------------------------------------------------- 買い物・配置
def test_buy_toy_and_food():
    s = fresh()
    assert game.buy(s, "rubber_ball").ok
    assert s["s_fish"] == 295 and s["owned_toys"] == ["rubber_ball"]
    assert game.buy(s, "rubber_ball").code == "owned"          # おもちゃは1個だけ
    assert game.buy(s, "dry_food").ok and game.buy(s, "dry_food").ok
    assert s["food_stock"] == {"dry_food": 2}                  # エサは何個でも買える
    assert game.buy(s, "nothing").code == "unknown"


def test_buy_needs_money():
    s = fresh()
    assert game.buy(s, "laser_pointer").code == "no_money"     # 金125 > 所持10
    assert s["g_fish"] == 10


def test_space_is_really_six():
    """元のコードは < 判定で実質5マスだった。6マスまで使える。"""
    s = fresh()
    six = ["rubber_ball", "yarn_ball", "cereal_box", "plastic_bucket", "paper_bag", "tennis_ball"]
    s["owned_toys"] = list(six)
    for t in six:
        assert game.place_toy(s, t).ok
    assert game.space_used(s) == 6
    s["owned_toys"].append("fruit_box")
    assert game.place_toy(s, "fruit_box").code == "no_room"


def test_large_condo_is_placeable():
    s = fresh()
    s["owned_toys"] = ["large_condo"]
    assert game.place_toy(s, "large_condo").ok


def test_place_remove_and_occupants_pay_out():
    s = stocked(("rubber_ball",))
    rng = random.Random(1)
    s["cats"]["gordo"].update(in_yard=True, toy="rubber_ball", time_in_yard=10)
    s["occ"]["rubber_ball"] = ["gordo"]
    assert game.remove_toy(s, "rubber_ball", rng).ok
    assert not s["cats"]["gordo"]["in_yard"] and s["cats"]["gordo"]["total_time"] == 10
    assert len(s["pending_money"]) == 1                         # 外した猫もさかなを置いて帰る
    assert "rubber_ball" not in s["occ"]


def test_set_food_confirm_before_discarding():
    s = fresh()
    s["food_stock"] = {"dry_food": 2}
    assert game.set_food(s, "dry_food").ok
    s["food_remaining"] = 120
    r = game.set_food(s, "dry_food")
    assert r.code == "need_confirm" and s["food_remaining"] == 120 and s["food_stock"]["dry_food"] == 1
    assert game.set_food(s, "dry_food", force=True).ok
    assert s["food_remaining"] == 300 and "dry_food" not in s["food_stock"]
    assert game.set_food(s, "dry_food", force=True).code == "no_stock"


def test_collect():
    s = fresh()
    s["pending_money"] = [["gordo", 10, "s"], ["pukka", 3, "g"]]
    got = game.collect(s)
    assert got == [("gordo", 10, "s"), ("pukka", 3, "g")]
    assert (s["s_fish"], s["g_fish"]) == (310, 13) and s["pending_money"] == []


# ---------------------------------------------------------------- 時間経過
def test_no_visitors_without_food_or_toys():
    s = stocked()
    s["food"], s["food_remaining"] = "", 0
    game.advance(s, T0 + 3600, random.Random(1))
    assert game.cats_in_yard(s) == [] and s["pending_money"] == []
    s2 = fresh()
    s2["food_stock"]["dry_food"] = 1
    game.set_food(s2, "dry_food")
    game.advance(s2, T0 + 3600, random.Random(1))
    assert game.cats_in_yard(s2) == []                         # おもちゃがなければ来ない


def test_advance_counts_whole_ticks_and_carries_remainder():
    s = stocked()
    assert game.advance(s, T0 + 59)["ticks"] == 0
    assert game.advance(s, T0 + 60)["ticks"] == 1
    assert game.advance(s, T0 + 60 + 150)["ticks"] == 2       # 150秒=2tick+30秒持ち越し
    assert s["last_tick"] == T0 + 60 + 120


def test_clock_rewind_is_safe():
    s = stocked()
    r = game.advance(s, T0 - 5000)
    assert r["ticks"] == 0 and s["last_tick"] == T0 - 5000


def test_catchup_is_capped():
    s = stocked()
    r = game.advance(s, T0 + 10 ** 9, random.Random(1))
    assert r["ticks"] == game.MAX_CATCHUP_TICKS


def test_food_runs_out_after_300_ticks():
    s = stocked()
    r = game.advance(s, T0 + 60 * 300, random.Random(2))
    assert s["food"] == "" and s["food_remaining"] == 0
    assert any(e[0] == "food_out" for e in r["events"]) or r["ticks"] == 300


def test_invariants_hold_over_long_random_play():
    s = stocked(("rubber_ball", "small_condo", "yarn_ball"))
    rng = random.Random(7)
    for minute in range(1, 6000):
        if s["food_remaining"] == 0:
            s["food_stock"]["dry_food"] = 1
            game.set_food(s, "dry_food")
        game.tick(s, rng)
        for toy in s["yard"]:
            assert len(s["occ"][toy]) <= game.TOYS[toy]["size"]
        seen = []
        for toy, lst in s["occ"].items():
            assert toy in s["yard"]
            for cid in lst:
                c = s["cats"][cid]
                assert c["in_yard"] and c["toy"] == toy and cid not in seen
                seen.append(cid)
        assert sorted(seen) == sorted(game.cats_in_yard(s))


def test_strong_cat_can_push_weaker():
    s = stocked(("rubber_ball",))
    rng = random.Random(3)
    s["cats"]["gordo"].update(in_yard=True, toy="rubber_ball", time_in_yard=5)
    s["occ"]["rubber_ball"] = ["gordo"]
    events = []
    game._try_push(s, "tarawa", "rubber_ball", rng, events)     # tarawa の強さ 6 > 5
    assert s["occ"]["rubber_ball"] == ["tarawa"]
    assert [e[0] for e in events] == ["leave", "arrive"]
    events = []
    game._try_push(s, "felix", "rubber_ball", rng, events)      # 5 < 6 なので押し出せない
    assert s["occ"]["rubber_ball"] == ["tarawa"] and events == []


def test_treasure_when_joining_after_3000_minutes():
    s = stocked(("rubber_ball",))
    s["cats"]["felix"]["total_time"] = 3001
    ev = []
    game._join(s, "felix", "rubber_ball", ev)
    assert s["pending_treasures"] == ["felix"] and ("treasure", "felix") in ev
    game._join(s, "felix", "rubber_ball", ev)                   # 2回目はもらえない
    assert s["pending_treasures"] == ["felix"]
    assert game.collect_treasures(s) == ["felix"] and s["pending_treasures"] == []


def test_launch_bonus():
    s = fresh()
    assert game.launch_bonus(s, T0, T0 + 999, random.Random(1)) is None   # 誰も遊んでいない
    s["cats"]["pukka"]["total_time"] = 100

    class Always(random.Random):
        def random(self):
            return 0.0
    assert game.launch_bonus(s, T0, T0 + 10, Always()) == "pukka"
    assert s["cats"]["pukka"]["given_treasure"] and s["pending_treasures"] == ["pukka"]


# ---------------------------------------------------------------- 元のコンソール版との経済パリティ
def test_economy_matches_console_version():
    """元の update.tick で実測した値(5個・エサ常時): 銀 約112/時, 来訪 約9.1回/時, 滞在 平均約18分"""
    silver, visits, hours = [], [], 24 * 3
    for seed in range(8):
        s = stocked()
        rng = random.Random(seed)
        ev = []
        for _ in range(60 * hours):
            if s["food_remaining"] == 0:
                s["food_stock"]["dry_food"] = 1
                game.set_food(s, "dry_food")
            game.tick(s, rng, ev)
        silver.append(sum(a for _c, a, cur in s["pending_money"] if cur == "s") / hours)
        visits.append(sum(1 for e in ev if e[0] == "arrive") / hours)
    assert 100 <= statistics.mean(silver) <= 125
    assert 8.3 <= statistics.mean(visits) <= 9.9


def test_stay_time_distribution():
    rng = random.Random(2)
    stays = []
    for _ in range(5000):
        c = {"time_in_yard": 0}
        while True:
            c["time_in_yard"] += 1
            if game._time_to_leave(c, game.CATS["gordo"], rng):
                break
        stays.append(c["time_in_yard"])
    assert 17 <= statistics.mean(stays) <= 19 and min(stays) >= 11 and max(stays) <= 26


# ---------------------------------------------------------------- 保存
def test_roundtrip():
    s = stocked()
    game.advance(s, T0 + 3600, random.Random(5))
    s2 = game.loads(game.dumps(s))
    assert s2 == s


def test_loads_rejects_other_versions_and_garbage():
    with pytest.raises(ValueError):
        game.loads(json.dumps({"version": 99}))
    with pytest.raises(ValueError):
        game.loads("[]")
    with pytest.raises(json.JSONDecodeError):
        game.loads("{broken")


def test_loads_repairs_inconsistent_data():
    s = stocked()
    d = json.loads(game.dumps(s))
    d["yard"] = ["rubber_ball", "no_such_toy", "rubber_ball"]
    d["owned_toys"] = ["rubber_ball", "ghost"]
    d["s_fish"] = "abc"
    d["food"] = "unknown_food"
    d["cats"]["gordo"].update(in_yard=True, toy="paper_bag")   # 庭にないおもちゃで遊んでいる
    d["pending_money"] = [["gordo", 5, "s"], ["ghost", 1, "s"], "bad"]
    r = game.loads(json.dumps(d))
    assert r["yard"] == ["rubber_ball"] and r["owned_toys"] == ["rubber_ball"]
    assert r["s_fish"] == 0 and r["food"] == "" and r["food_remaining"] == 0
    assert not r["cats"]["gordo"]["in_yard"] and r["occ"] == {"rubber_ball": []}
    assert r["pending_money"] == [["gordo", 5, "s"]]


def test_catalog_is_consistent():
    assert len(game.TOYS) == 24 and len(game.FOODS) == 3 and len(game.CATS) == 5
    for it in game.ITEMS.values():
        assert it["cur"] in ("s", "g") and it["cost"] > 0 and it["size"] >= 1
        assert it["size"] <= game.SPACE or it["kind"] == "food"
