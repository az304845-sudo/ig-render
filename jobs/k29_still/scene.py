# k29「客船」— Blender 4.2 で場面を組むだけの Python（描き出しは外から -s/-e/-a で渡る）
# ・ブロック（凸のある四角い部品）で組んだ架空の客船＋ブロックで量子化した夜の荒波＋白いしぶきのブロック
# ・外の素材は使わない（形は numpy で手続き生成、材質はノード）
# ・動きはすべて「時刻の関数」から決める。しぶき・船・カメラ・雷はキーフレームに焼き、
#   波はコマ番号から毎コマ計算し直す（どのチャンクから描いても同じ画になる）
# ・灰色の「Blender の画面」版：同じフォルダに mode.txt（中身 workbench）を置くか、
#   環境変数 K29_MODE=workbench で、同じカメラ・同じ形のままワークベンチ描画に切り替わる
import math
import os
import sys

import numpy as np

try:
    import bpy
except ImportError:  # Mac での検算用（bpy なし）
    bpy = None

FPS = 30
FRAME_END = 450          # 15.0 秒（11/25 運用：450コマ以内）
RES = (720, 1280)        # 軽くする：720×1280 で描き、あとで ffmpeg lanczos で 1080×1920 へ
SEED = 29

# ---- 単位：1 = 1 スタッド（実物 8mm）。高さ：ブロック 1.2・プレート 0.4
BRICK = 1.2
PLATE = 0.4
GAP = 0.03               # 継ぎ目（隣の部品との隙間）
BEV = 0.045              # 角の面取り（ハイライトが乗る）
STUD_R = 0.30
STUD_H = 0.21


# ------------------------------------------------------------------ モード
def _script_dir():
    for i, a in enumerate(sys.argv):
        if a in ("-P", "--python") and i + 1 < len(sys.argv):
            return os.path.dirname(os.path.abspath(sys.argv[i + 1]))
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def _mode():
    m = os.environ.get("K29_MODE", "").strip().lower()
    if not m:
        p = os.path.join(_script_dir(), "mode.txt")
        if os.path.exists(p):
            with open(p) as fh:
                m = fh.read().strip().lower()
    return m or "final"


MODE = _mode()


# ------------------------------------------------------------------ 型紙（numpy）
def tpl_box(b=BEV):
    """面取りした単位立方体 [0,1]^3。24 頂点。UP は伸ばすときに動かす頂点の印。"""
    verts, idx = [], {}
    for sx in (0, 1):
        for sy in (0, 1):
            for sz in (0, 1):
                c = np.array([sx, sy, sz], float)
                inward = np.where(c > 0.5, -b, b)
                for ax in range(3):
                    v = c.copy()
                    for o in range(3):
                        if o != ax:
                            v[o] += inward[o]
                    idx[(sx, sy, sz, ax)] = len(verts)
                    verts.append(v)
    faces = []
    for ax in range(3):
        others = [o for o in range(3) if o != ax]
        for s in (0, 1):
            f = []
            for a, q in ((0, 0), (1, 0), (1, 1), (0, 1)):
                c = [0, 0, 0]
                c[ax] = s
                c[others[0]] = a
                c[others[1]] = q
                f.append(idx[(c[0], c[1], c[2], ax)])
            faces.append(f)
    for e in range(3):
        p, q = [o for o in range(3) if o != e]
        for sp in (0, 1):
            for sq in (0, 1):
                def cid(se, ty):
                    c = [0, 0, 0]
                    c[e] = se
                    c[p] = sp
                    c[q] = sq
                    return idx[(c[0], c[1], c[2], ty)]
                faces.append([cid(0, p), cid(1, p), cid(1, q), cid(0, q)])
    for sx in (0, 1):
        for sy in (0, 1):
            for sz in (0, 1):
                faces.append([idx[(sx, sy, sz, 0)], idx[(sx, sy, sz, 1)], idx[(sx, sy, sz, 2)]])
    V = np.array(verts)
    out = []
    for f in faces:
        P = V[f]
        n = np.cross(P[1] - P[0], P[2] - P[0]) if len(f) == 3 else np.cross(P[2] - P[0], P[3] - P[1])
        if np.dot(n, P.mean(0) - 0.5) < 0:
            f = f[::-1]
        out.append(list(f))
    UP = (V > 0.5).astype(float)
    return V, out, [False] * len(out), UP


def tpl_cyl(n, r, h, c_top=0.0, c_bot=0.0, z0=0.0, cap_top=True, cap_bot=False):
    """円柱（凸・丸いブロック・柱）。側面はなめらか、ふたは平ら（頂点を分ける）。"""
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)

    def ring(rad, z):
        return np.stack([rad * np.cos(ang), rad * np.sin(ang), np.full(n, z)], 1)

    rings = []
    if c_bot > 0:
        rings += [ring(r - c_bot, z0), ring(r, z0 + c_bot)]
    else:
        rings += [ring(r, z0)]
    if c_top > 0:
        rings += [ring(r, z0 + h - c_top), ring(r - c_top, z0 + h)]
    else:
        rings += [ring(r, z0 + h)]
    V = list(rings)
    faces, sm = [], []
    for k in range(len(rings) - 1):
        for i in range(n):
            j = (i + 1) % n
            faces.append([k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i])
            sm.append(True)
    base = len(rings) * n
    if cap_top:
        V.append(rings[-1].copy())
        faces.append(list(range(base, base + n)))
        sm.append(False)
        base += n
    if cap_bot:
        V.append(rings[0].copy())
        faces.append(list(range(base + n - 1, base - 1, -1)))
        sm.append(False)
    return np.concatenate(V), faces, sm, None


BOX = tpl_box()
STUD16 = tpl_cyl(16, STUD_R, STUD_H, c_top=0.035, z0=-0.03)
STUD12 = tpl_cyl(12, STUD_R, STUD_H, c_top=0.035, z0=-0.03)
STUD8 = tpl_cyl(8, STUD_R, STUD_H, c_top=0.0, z0=-0.03)


class Acc:
    """部品をまとめて1つのメッシュにする入れ物。attrs は部品ごとの値（N, c）。"""

    def __init__(self, attr_dims):
        self.attr_dims = attr_dims
        self.V, self.L, self.S, self.SM = [], [], [], []
        self.A = {k: [] for k in attr_dims}
        self.nv = 0
        self.items = 0

    def add(self, tpl, origins, sizes=None, rot=None, attrs=None):
        tV, tF, tSm, UP = tpl
        origins = np.asarray(origins, float).reshape(-1, 3)
        N, k = len(origins), len(tV)
        if N == 0:
            return
        V = np.broadcast_to(tV, (N, k, 3)).copy()
        if sizes is not None:
            V += UP[None] * (np.asarray(sizes, float).reshape(-1, 3)[:, None, :] - 1.0)
        if rot is not None:
            V = V @ np.asarray(rot).T
        V += origins[:, None, :]
        self.V.append(V.reshape(-1, 3))
        flat = np.concatenate([np.asarray(f) for f in tF])
        lens = np.array([len(f) for f in tF])
        self.L.append((flat[None, :] + (self.nv + np.arange(N) * k)[:, None]).ravel())
        self.S.append(np.tile(lens, N))
        self.SM.append(np.tile(np.asarray(tSm, bool), N))
        attrs = attrs or {}
        for name, dim in self.attr_dims.items():
            val = np.asarray(attrs.get(name, np.zeros((N, dim))), np.float32).reshape(N, dim)
            self.A[name].append(np.repeat(val, k, axis=0))
        self.nv += N * k
        self.items += N

    def arrays(self):
        V = np.concatenate(self.V).astype(np.float32)
        L = np.concatenate(self.L).astype(np.int32)
        S = np.concatenate(self.S).astype(np.int32)
        SM = np.concatenate(self.SM)
        A = {k: np.concatenate(v).astype(np.float32) for k, v in self.A.items()}
        return V, L, S, SM, A


def add_bricks(acc, x0, y0, z0, sx, sy, sz, col, extra=None):
    x0, y0, z0, sx, sy, sz = (np.asarray(a, float) for a in (x0, y0, z0, sx, sy, sz))
    org = np.stack([x0 + GAP / 2, y0 + GAP / 2, z0 + 0.004], 1)
    size = np.stack([sx - GAP, sy - GAP, sz - 0.008], 1)
    attrs = {"col": col}
    if extra:
        attrs.update(extra)
    acc.add(BOX, org, size, attrs=attrs)


def add_studs(acc, px, py, pz, col, tpl=STUD16, extra=None):
    attrs = {"col": col}
    if extra:
        attrs.update(extra)
    acc.add(tpl, np.stack([px, py, pz], 1), attrs=attrs)


# ------------------------------------------------------------------ 船の形
HULL_HALF = 6.0
STERN_X = -32.0


def hull_hw(x, k=0):
    """船体の半幅（スタッド）。k は段（上の段ほど船首が前へ出る＝反り）。"""
    x = np.asarray(x, float)
    tip = 33.0 + (0.45 * k if k > 0 else 0.9 * k)
    t = np.clip((x - 12.0) / (tip - 12.0), 0, 1)
    w = np.where(x > 12.0, HULL_HALF * np.clip(1 - t ** 1.7, 0, 1) ** 0.8, HULL_HALF)
    ts = np.clip((STERN_X + 3.0 - x) / 3.2, 0, 1)
    w = np.where(x < STERN_X + 3.0, w * np.sqrt(np.clip(1 - ts * ts, 0, 1)), w)
    if k < 0:
        w = w - 0.7 * (-k)
    return np.where((x > tip) | (x < STERN_X), 0.0, w)


def partition(cells, parity, maxlen=4, first=(3, 2)):
    """セルの集合を 1×N のブロックに分ける（段ごとに継ぎ目をずらす）。"""
    cells = set(cells)
    out, used = [], set()
    rows = {}
    for (i, j) in cells:
        rows.setdefault(j, []).append(i)
    for j, xs in rows.items():
        xs.sort()
        runs, cur = [], [xs[0]]
        for a in xs[1:]:
            if a == cur[-1] + 1:
                cur.append(a)
            else:
                runs.append(cur)
                cur = [a]
        runs.append(cur)
        for run in runs:
            if len(run) < 2:
                continue
            pos, end = run[0], run[-1] + 1
            L = min(first[(parity + j) % 2], end - pos)
            while pos < end:
                out.append((pos, j, L, 1))
                used.update((pos + q, j) for q in range(L))
                pos += L
                L = min(maxlen, end - pos)
    rest = cells - used
    cols = {}
    for (i, j) in rest:
        cols.setdefault(i, []).append(j)
    for i, ys in cols.items():
        ys.sort()
        runs, cur = [], [ys[0]]
        for a in ys[1:]:
            if a == cur[-1] + 1:
                cur.append(a)
            else:
                runs.append(cur)
                cur = [a]
        runs.append(cur)
        for run in runs:
            pos, end = run[0], run[-1] + 1
            L = min(first[(parity + i) % 2], end - pos)
            while pos < end:
                out.append((i, pos, 1, L))
                pos += L
                L = min(maxlen, end - pos)
    return out


# 色（リニア RGB）
WHITE = (0.74, 0.74, 0.71)
NAVY = (0.010, 0.020, 0.058)
TAN = (0.40, 0.29, 0.16)
LGREY = (0.36, 0.37, 0.38)
DGREY = (0.045, 0.047, 0.05)
SOOT = (0.012, 0.012, 0.013)

RNG = np.random.default_rng(SEED)


def jit(c, n=1, amt=0.03):
    c = np.asarray(c, float)[None, :] * RNG.normal(1.0, amt, (n, 1))
    return np.concatenate([np.clip(c, 0, 1), np.ones((n, 1))], 1)


def neigh4(c):
    i, j = c
    return ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1))


def build_stack(acc, accw, inside, irange, jrange, z0, nlayers, col_fn, win_fn,
                roof_col=None, roof_studs=True, wall_studs=True, lit_p=0.88):
    occ = [{(i, j) for i in irange for j in jrange if inside(i, j, L)} for L in range(nlayers)]
    B = {k: [] for k in ("x", "y", "z", "sx", "sy", "sz", "col")}
    S = {k: [] for k in ("x", "y", "z", "col")}
    W = {k: [] for k in ("x", "y", "z", "lit")}
    rings = []
    for L in range(nlayers):
        cells = occ[L]
        ring = {c for c in cells if any(n not in cells for n in neigh4(c))}
        rings.append(ring)
        wins = {c for c in ring if win_fn(c[0], c[1], L)}
        above = occ[L + 1] if L + 1 < nlayers else set()
        z = z0 + L * BRICK
        for (i, j, li, lj) in partition(ring - wins, L):
            col = jit(col_fn(i, j, L))[0]
            B["x"].append(i); B["y"].append(j); B["z"].append(z)
            B["sx"].append(li); B["sy"].append(lj); B["sz"].append(BRICK); B["col"].append(col)
            if wall_studs:
                for a in range(li):
                    for b in range(lj):
                        if (i + a, j + b) not in above:
                            S["x"].append(i + a + 0.5); S["y"].append(j + b + 0.5)
                            S["z"].append(z + BRICK); S["col"].append(col)
        for (i, j) in wins:
            W["x"].append(i); W["y"].append(j); W["z"].append(z)
            W["lit"].append(1.0 if RNG.random() < lit_p else 0.0)
    if roof_col is not None:
        top = nlayers - 1
        interior = occ[top] - rings[top]
        zt = z0 + nlayers * BRICK - PLATE
        for (i, j, li, lj) in partition(interior, 1, maxlen=6, first=(4, 6)):
            col = jit(roof_col, amt=0.05)[0]
            B["x"].append(i); B["y"].append(j); B["z"].append(zt)
            B["sx"].append(li); B["sy"].append(lj); B["sz"].append(PLATE); B["col"].append(col)
            if roof_studs:
                for a in range(li):
                    for b in range(lj):
                        S["x"].append(i + a + 0.5); S["y"].append(j + b + 0.5)
                        S["z"].append(zt + PLATE); S["col"].append(col)
    add_bricks(acc, B["x"], B["y"], B["z"], B["sx"], B["sy"], B["sz"], np.array(B["col"]))
    if S["x"]:
        add_studs(acc, np.array(S["x"]), np.array(S["y"]), np.array(S["z"]), np.array(S["col"]))
    if W["x"]:
        n = len(W["x"])
        add_bricks(accw, W["x"], W["y"], W["z"], np.ones(n), np.ones(n), np.full(n, BRICK),
                   np.tile([[1.0, 0.55, 0.22, 1.0]], (n, 1)),
                   extra={"lit": np.array(W["lit"])[:, None]})
    return occ, rings


HULL_K0 = -2
HULL_LAYERS = 9            # 段 -2〜6、甲板の高さ = 7*1.2 = 8.4
DECK_Z = (HULL_K0 + HULL_LAYERS) * BRICK


def build_ship():
    acc = Acc({"col": 4})
    accw = Acc({"col": 4, "lit": 1})
    I = range(-33, 37)
    J = range(-7, 7)

    def h_in(i, j, L):
        k = HULL_K0 + L
        return abs(j + 0.5) < float(hull_hw(i + 0.5, k))

    def h_col(i, j, L):
        k = HULL_K0 + L
        if k <= 0 or k == 5:
            return NAVY
        return WHITE

    def h_win(i, j, L):
        k = HULL_K0 + L
        return k in (2, 4) and j in (-6, 5) and -27 <= i <= 15 and i % 2 == 0

    occ, rings = build_stack(acc, accw, h_in, I, J, HULL_K0 * BRICK, HULL_LAYERS, h_col, h_win,
                             roof_col=TAN, roof_studs=False)

    # 手すり：甲板のふちに柱、横の直線部に横棒
    top_ring = sorted(rings[-1])
    px = np.array([i + 0.5 for (i, j) in top_ring if (i + j) % 2 == 0 and i < 32])
    py = np.array([j + 0.5 for (i, j) in top_ring if (i + j) % 2 == 0 and i < 32])
    post = tpl_cyl(8, 0.11, 1.05, c_top=0.02)
    acc.add(post, np.stack([px, py, np.full(len(px), DECK_Z + 0.1)], 1), attrs={"col": jit(WHITE, len(px))})
    for j in (-6, 5):
        add_bricks(acc, [-31.0], [j + 0.5 - 0.09], [DECK_Z + 1.12], [45.0], [0.18 + GAP], [0.16], jit(WHITE))

    # 上部構造 3 段
    def t1_in(i, j, L):
        x = i + 0.5
        if x < -24 or x > 14.2:
            return False
        w = 4.5 if x < 10 else 4.5 * math.sqrt(max(1 - ((x - 10) / 4.2) ** 2, 0))
        return abs(j + 0.5) < w

    build_stack(acc, accw, t1_in, range(-25, 16), range(-6, 6), DECK_Z, 2,
                lambda i, j, L: WHITE,
                lambda i, j, L: L == 1 and j in (-4, 3) and -23 <= i <= 9 and i % 2 == 1,
                roof_col=LGREY)
    Z1 = DECK_Z + 2 * BRICK

    def t2_in(i, j, L):
        x = i + 0.5
        if x < -18 or x > 7.5:
            return False
        w = 3.5 if x < 4 else 3.5 * math.sqrt(max(1 - ((x - 4) / 3.5) ** 2, 0))
        return abs(j + 0.5) < w

    build_stack(acc, accw, t2_in, range(-19, 9), range(-5, 5), Z1, 2,
                lambda i, j, L: NAVY if L == 1 else WHITE, lambda i, j, L: False, roof_col=LGREY)
    Z2 = Z1 + 2 * BRICK

    def t3_in(i, j, L):
        x = i + 0.5
        return 2 < x < 9 and abs(j + 0.5) < 3.5

    build_stack(acc, accw, t3_in, range(1, 10), range(-5, 5), Z2, 1,
                lambda i, j, L: WHITE, lambda i, j, L: i == 8 and -3 <= j <= 2,
                roof_col=WHITE, lit_p=0.7)

    # 煙突 2 本（丸いブロックを積む・後ろへ傾ける）
    rake = math.radians(-9.0)
    R = np.array([[math.cos(rake), 0, math.sin(rake)], [0, 1, 0], [-math.sin(rake), 0, math.cos(rake)]])
    axis = R @ np.array([0, 0, 1.0])
    # 3周目：輪を積んだ形がタイヤに見えたので、なめらかな丸い筒＋上の縁にだけ黒い帯
    body_h = 7 * BRICK - 0.9
    body = tpl_cyl(48, 1.9, body_h, c_top=0.0, c_bot=0.03)
    band = tpl_cyl(48, 1.93, 0.9, c_top=0.05, c_bot=0.02)
    disk = tpl_cyl(48, 1.6, 0.06)
    for fx in (-12.0, -2.0):
        base = np.array([fx, 0.0, Z2])
        acc.add(body, [base], rot=R, attrs={"col": jit(WHITE)})
        acc.add(band, [base + axis * body_h], rot=R, attrs={"col": jit(SOOT)})
        acc.add(disk, [base + axis * (body_h + 0.86)], rot=R, attrs={"col": jit((0.004, 0.004, 0.004))})

    # マスト 2 本と横木
    for mx, mh in ((24.5, 13.0), (-27.5, 11.5)):
        acc.add(tpl_cyl(12, 0.18, mh, c_top=0.03), [[mx, 0.0, DECK_Z]], attrs={"col": jit(DGREY)})
    add_bricks(acc, [24.3], [-3.0], [DECK_Z + 9.5], [0.4], [6.0], [0.3], jit(DGREY))

    # 救命ボート（白い船体＋紺の覆い）
    bx = np.array([-22.0, -16.0, -9.0, -3.0] * 2)
    by = np.array([3.0] * 4 + [-4.0] * 4)
    n = len(bx)
    add_bricks(acc, bx, by + 0.05, np.full(n, Z1), np.full(n, 3.2), np.full(n, 0.9), np.full(n, 0.8), jit(WHITE, n))
    add_bricks(acc, bx + 0.15, by + 0.1, np.full(n, Z1 + 0.8), np.full(n, 2.9), np.full(n, 0.8),
               np.full(n, 0.22), jit(NAVY, n))
    # 船首の巻き上げ機
    acc.add(tpl_cyl(16, 0.9, 0.5, c_top=0.05), [[27.0, -1.2, DECK_Z], [27.0, 1.2, DECK_Z]],
            attrs={"col": jit(DGREY, 2)})
    return acc, accw


# ------------------------------------------------------------------ 波（ブロックで量子化）
SWELLS = [  # 振幅, 波長, 進む向き(度), 位相, とがり
    (1.45, 72.0, 205.0, 0.3, 1.6),
    (0.85, 34.0, 238.0, 1.9, 1.5),
    (0.55, 17.0, 172.0, 4.1, 1.3),
    (0.30, 9.0, 255.0, 2.6, 1.2),
]


def hull_dist(x, y):
    hw = hull_hw(x, 0)
    d_side = np.abs(y) - hw
    d_bow = np.hypot(np.maximum(x - 33.0, 0), y)
    d_st = np.hypot(np.maximum(STERN_X - x, 0), y)
    return np.where(hw > 0, d_side, np.where(x > 0, d_bow, d_st))


def swell(x, y, t):
    h = np.zeros_like(x, dtype=float)
    for A, lam, ang, ph, sh in SWELLS:
        k = 2 * np.pi / lam
        c = 0.9 * math.sqrt(lam)
        a = math.radians(ang)
        s = np.sin(k * (x * math.cos(a) + y * math.sin(a) - c * t) + ph)
        s = ((s + 1) * 0.5) ** sh * 2 - 1
        h += A * s
    return h


def water_raw(x, y, t):
    """海面の高さ（量子化の前）と、泡になりやすさ。"""
    sw = swell(x, y, t)
    d = np.maximum(hull_dist(x, y), 0)
    bow_crest = 5.4 * np.exp(-((x - 28.0) / 6.0) ** 2) * np.exp(-(np.maximum(np.abs(y) - 4, 0) / 20.0) ** 2)
    ramp = np.clip((x + 10) / 35.0, 0, 1)
    pile = 2.4 * np.exp(-(d / 2.4) ** 2) * ramp
    trough = -1.3 * np.exp(-((x - 10.0) / 8.0) ** 2) * np.exp(-(d / 6.0) ** 2)
    h = sw + bow_crest + pile + trough
    foam = np.clip(
        np.clip((h - 2.0) / 1.6, 0, 1)
        + 0.85 * np.exp(-(d / 1.8) ** 2) * np.clip((x - 5) / 17.0, 0, 1)
        + 0.7 * np.clip((sw - 1.15) / 0.9, 0, 1), 0, 1)
    return h, foam


WATER_COLS = np.array([   # 2周目：真っ黒に沈んだので明るい紺青へ
    [0.012, 0.050, 0.120],
    [0.018, 0.075, 0.170],
    [0.010, 0.085, 0.130],
    [0.008, 0.035, 0.085],
])

# カメラ（船首の斜め前・海面すれすれ・望遠ぎみ）
CAM_POS = np.array([181.0, 103.0, 7.0])
CAM_TGT = np.array([4.0, 2.0, 12.0])
CAM_LENS = 85.0
FOCUS_PT = np.array([27.0, 4.0, 6.0])
TOY_FSTOP = 5.6                    # 実物の模型を f/5.6 で撮った想定
FAR_R = 520.0                      # ここから先の海は1枚の面
UNIT_M = 0.008                     # 1 スタッド = 8mm


class WaterLevel:
    def __init__(self, s, cx, cy):
        self.s = s
        self.cx, self.cy = cx, cy
        self.N = len(cx)
        self.jit = RNG.uniform(-0.25, 0.25, self.N)
        self.rnd = RNG.random(self.N)
        self.shade = WATER_COLS[RNG.integers(0, len(WATER_COLS), self.N)]
        self.stud = STUD12 if s == 1 else None      # 遠い柱はぼけて凸が見えないので省く
        g = np.arange(s) + 0.5 - s / 2.0
        self.soff = np.array([(a, b) for a in g for b in g]) if self.stud is not None else None

    def state(self, t):
        s = self.s
        h, foam = water_raw(self.cx, self.cy, t)
        h = h + self.jit
        hq = np.round(h / PLATE) * PLATE
        nb = []
        for dx, dy in ((s, 0), (-s, 0), (0, s), (0, -s)):
            hn, _ = water_raw(self.cx + dx, self.cy + dy, t)
            nb.append(np.round(hn / PLATE) * PLATE)
        base = np.minimum(np.min(nb, axis=0), hq) - BRICK * (1.0 if s == 1 else 1.5)
        isfoam = (self.rnd < foam * (1.0 if s <= 2 else 0.6)).astype(np.float32)
        return hq, base, isfoam

    def verts(self, t):
        hq, base, isfoam = self.state(t)
        s = self.s
        org = np.stack([self.cx - s / 2 + GAP / 2, self.cy - s / 2 + GAP / 2, base], 1)
        size = np.stack([np.full(self.N, s - GAP), np.full(self.N, s - GAP), hq - base], 1)
        tV, _, _, UP = BOX
        V = tV[None] + UP[None] * (size[:, None, :] - 1.0) + org[:, None, :]
        out = [V.reshape(-1, 3)]
        foam_v = [np.repeat(isfoam, len(tV))]
        if self.stud is not None:
            sV = self.stud[0]
            px = (self.cx[:, None] + self.soff[None, :, 0]).ravel()
            py = (self.cy[:, None] + self.soff[None, :, 1]).ravel()
            pz = np.repeat(hq, len(self.soff))
            Vs = sV[None] + np.stack([px, py, pz], 1)[:, None, :]
            out.append(Vs.reshape(-1, 3))
            foam_v.append(np.repeat(np.repeat(isfoam, len(self.soff)), len(sV)))
        return np.concatenate(out).astype(np.float32), np.concatenate(foam_v).astype(np.float32)

    def topology(self):
        acc = Acc({"col": 4})
        col = np.concatenate([self.shade, np.ones((self.N, 1))], 1)
        acc.add(BOX, np.zeros((self.N, 3)), np.ones((self.N, 3)), attrs={"col": col})
        if self.stud is not None:
            ns = len(self.soff)
            acc.add(self.stud, np.zeros((self.N * ns, 3)), attrs={"col": np.repeat(col, ns, axis=0)})
        return acc


def water_cells():
    """カメラからの距離で 1/2/4/8 スタッドの柱に分け、写る扇形の中だけ置く。"""
    view = CAM_TGT[:2] - CAM_POS[:2]
    az0 = math.atan2(view[1], view[0])
    half = math.radians(10.5)
    # 軽くする：柱は 520 まで。その先は「遠い海」の1枚の面（凹凸はノード）
    rings = [(1, 8.0, 265.0), (2, 265.0, FAR_R)]
    levels = []
    for s, r0, r1 in rings:
        xs = np.arange(CAM_POS[0] - r1, CAM_POS[0] + r1, s)
        ys = np.arange(CAM_POS[1] - r1, CAM_POS[1] + r1, s)
        # 扇形の外接矩形だけに絞ってから格子を作る
        corners = []
        for rr in (r0, r1):
            for a in np.linspace(az0 - half, az0 + half, 9):
                corners.append(CAM_POS[:2] + rr * np.array([math.cos(a), math.sin(a)]))
        corners = np.array(corners)
        lo, hi = corners.min(0) - s, corners.max(0) + s
        xs = xs[(xs >= lo[0]) & (xs <= hi[0])]
        ys = ys[(ys >= lo[1]) & (ys <= hi[1])]
        X, Y = np.meshgrid(xs + s / 2, ys + s / 2)
        X, Y = X.ravel(), Y.ravel()
        dx, dy = X - CAM_POS[0], Y - CAM_POS[1]
        d = np.hypot(dx, dy)
        da = np.abs((np.arctan2(dy, dx) - az0 + np.pi) % (2 * np.pi) - np.pi)
        keep = (d >= r0) & (d < r1) & (da < half + np.arctan2(s, np.maximum(d, 1)))
        if s == 1:
            keep &= ~(np.abs(Y) < hull_hw(X, 0) + 0.2)
        levels.append(WaterLevel(s, X[keep], Y[keep]))
    return levels


# ------------------------------------------------------------------ 動き（時刻の関数）
def frame_t(f):
    return (f - 1) / FPS


def ship_pose(t):
    """船の縦揺れ・横揺れ・上下（船首が波に突っ込むところから始まる）。"""
    pitch = math.radians(5.0 - 3.5 * (1 - math.cos(2 * math.pi * t / 3.4)))   # + で船首が下がる
    roll = math.radians(2.5 * math.sin(2 * math.pi * t / 4.3 + 0.6))
    z = -0.5 + 0.45 * (1 - math.cos(2 * math.pi * t / 3.4))
    return (roll, pitch, 0.0), (0.0, 0.0, z)


def look_euler(cam, tgt):
    f = tgt - cam
    f = f / np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    Rm = np.stack([r, u, -f], 1)
    x = math.atan2(Rm[2, 1], Rm[2, 2])
    y = math.asin(-Rm[2, 0])
    z = math.atan2(Rm[1, 0], Rm[0, 0])
    return np.array([x, y, z])


def cam_shake(t):
    a = math.radians(0.06)
    return np.array([
        a * (math.sin(7.1 * t + 0.4) + 0.6 * math.sin(13.3 * t + 2.0)),
        a * 0.5 * math.sin(5.3 * t + 1.1),
        a * (math.sin(6.2 * t + 2.7) + 0.5 * math.sin(17.9 * t + 0.3)),
    ])


SPRAY_N = 1500
SPRAY_FRAMES = 62
SPRAY_SCALE = 0.62       # 3周目：小さく平たい粒に
GRAV = 42.0


def spray_plan():
    """3周目：波頭から縦に噴き上がる細かい粒の幕（横へはあまり広がらない）。"""
    r = np.random.default_rng(SEED + 1)
    n = SPRAY_N
    t0 = np.concatenate([r.uniform(-1.15, 0.0, int(n * 0.6)), r.uniform(0.0, 2.0, n - int(n * 0.6))])
    at_hull = r.random(n) < 0.7
    side = np.where(r.random(n) < 0.45, 1.0, -1.0)
    ox = np.where(at_hull, r.uniform(17.0, 34.0, n), r.uniform(22.0, 36.0, n))
    oy = np.where(at_hull, side * (hull_hw(ox, 0) + r.uniform(0.2, 1.4, n)), r.uniform(-14.0, 14.0, n))
    hw_o, _ = water_raw(ox, oy, np.zeros(n))
    oz = np.maximum(hw_o, 1.5) + r.uniform(0.0, 0.8, n)
    vy = np.where(at_hull, side * r.uniform(0.5, 5.0, n), r.uniform(-3.0, 3.0, n))
    v = np.stack([r.uniform(-1, 5, n), vy, r.uniform(20, 46, n)], 1)
    kind = r.choice(5, n, p=[0.50, 0.20, 0.18, 0.07, 0.05])
    rot0 = r.uniform(0, 2 * np.pi, (n, 3))
    spin = r.normal(0, 7.0, (n, 3))
    frames = np.arange(0, SPRAY_FRAMES + 2)
    T = frame_t(frames)
    age = T[None, :] - t0[:, None]
    P = (np.stack([ox, oy, oz], 1)[:, None, :] + v[:, None, :] * age[..., None])
    P[..., 2] -= 0.5 * GRAV * age ** 2
    hw_, _ = water_raw(P[..., 0].ravel(), P[..., 1].ravel(), np.repeat(T[None], n, 0).ravel())
    under = (P[..., 2] < hw_.reshape(n, -1) - 0.4) & (age > 0.12)
    landed = np.cumsum(under, axis=1) > 0
    alive = (age >= 0) & ~landed
    ROT = rot0[:, None, :] + spin[:, None, :] * np.maximum(age, 0)[..., None]
    P = np.where(alive[..., None], P, np.stack([ox, oy, np.full(n, -30.0)], 1)[:, None, :])
    return frames, P, ROT, alive, kind


# ------------------------------------------------------------------ ここから Blender
def _set(obj, name, val):
    try:
        setattr(obj, name, val)
        return True
    except Exception:
        return False


def _inp(node, name, val):
    if name in node.inputs:
        node.inputs[name].default_value = val


def make_mesh(name, V, L, S, SM, A, mat, coll, parent=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    me.loops.add(len(L))
    me.loops.foreach_set("vertex_index", L)
    me.polygons.add(len(S))
    starts = np.zeros(len(S), np.int32)
    starts[1:] = np.cumsum(S)[:-1]
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    try:
        me.polygons.foreach_set("use_smooth", SM.astype(bool))
    except Exception:
        a = me.attributes.new("sharp_face", "BOOLEAN", "FACE")
        a.data.foreach_set("value", ~SM.astype(bool))
    for k, arr in A.items():
        if arr.shape[1] == 4:
            ca = me.color_attributes.new(k, "FLOAT_COLOR", "POINT")
            ca.data.foreach_set("color", arr.ravel())
        else:
            a = me.attributes.new(k, "FLOAT", "POINT")
            a.data.foreach_set("value", arr.ravel())
    me.validate(verbose=False)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def bake(idblock, path, index, frames, values, interp="LINEAR"):
    ad = idblock.animation_data or idblock.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(idblock.name + "_act")
    fc = ad.action.fcurves.new(path, index=index)
    n = len(frames)
    fc.keyframe_points.add(n)
    co = np.empty(2 * n, np.float32)
    co[0::2] = frames
    co[1::2] = values
    fc.keyframe_points.foreach_set("co", co)
    for kp in fc.keyframe_points:
        kp.interpolation = interp
    fc.update()


# ---- 材質
def mat_plastic(name, use_attr=True, color=(0.8, 0.8, 0.8)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    bs = N.new("ShaderNodeBsdfPrincipled")
    _inp(bs, "IOR", 1.46)
    _inp(bs, "Specular IOR Level", 0.5)
    if use_attr:
        at = N.new("ShaderNodeAttribute")
        at.attribute_name = "col"
        Lk.new(at.outputs["Color"], bs.inputs["Base Color"])
    else:
        _inp(bs, "Base Color", (*color, 1))
    tc = N.new("ShaderNodeTexCoord")
    # 指の跡・くすみ（大きなむら）
    smudge = N.new("ShaderNodeTexNoise")
    _inp(smudge, "Scale", 0.35)
    _inp(smudge, "Detail", 4.0)
    Lk.new(tc.outputs["Object"], smudge.inputs["Vector"])
    # 細かい擦り傷（一方向に伸ばしたノイズ）
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    mp.inputs["Rotation"].default_value = (0.3, 0.9, 0.2)
    Lk.new(tc.outputs["Object"], mp.inputs["Vector"])
    mp2 = N.new("ShaderNodeMapping")
    mp2.inputs["Scale"].default_value = (60.0, 2.0, 2.0)
    Lk.new(mp.outputs["Vector"], mp2.inputs["Vector"])
    scr = N.new("ShaderNodeTexNoise")
    _inp(scr, "Scale", 6.0)
    _inp(scr, "Detail", 2.0)
    Lk.new(mp2.outputs["Vector"], scr.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.60
    ramp.color_ramp.elements[1].position = 0.66
    Lk.new(scr.outputs["Fac"], ramp.inputs["Fac"])
    m1 = N.new("ShaderNodeMath")
    m1.operation = "MULTIPLY_ADD"
    m1.inputs[1].default_value = 0.16
    m1.inputs[2].default_value = 0.17
    Lk.new(smudge.outputs["Fac"], m1.inputs[0])
    m2 = N.new("ShaderNodeMath")
    m2.operation = "MULTIPLY_ADD"
    m2.inputs[1].default_value = 0.22
    Lk.new(ramp.outputs["Color"], m2.inputs[0])
    Lk.new(m1.outputs["Value"], m2.inputs[2])
    Lk.new(m2.outputs["Value"], bs.inputs["Roughness"])
    bump = N.new("ShaderNodeBump")
    _inp(bump, "Strength", 0.05)
    _inp(bump, "Distance", 0.004)
    Lk.new(ramp.outputs["Color"], bump.inputs["Height"])
    Lk.new(bump.outputs["Normal"], bs.inputs["Normal"])
    Lk.new(bs.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat_trans(name, color, rough=0.05, trans=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N = m.node_tree.nodes
    bs = N.get("Principled BSDF")
    _inp(bs, "Base Color", (*color, 1))
    _inp(bs, "Roughness", rough)
    _inp(bs, "Transmission Weight", trans)
    _inp(bs, "IOR", 1.5)
    return m


def mat_water(name, trans):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    at = N.new("ShaderNodeAttribute")
    at.attribute_name = "col"
    fo = N.new("ShaderNodeAttribute")
    fo.attribute_name = "foam"
    w = N.new("ShaderNodeBsdfPrincipled")
    Lk.new(at.outputs["Color"], w.inputs["Base Color"])
    _inp(w, "Roughness", 0.11)
    _inp(w, "Transmission Weight", trans)
    _inp(w, "IOR", 1.5)
    _inp(w, "Specular IOR Level", 0.55)
    f = N.new("ShaderNodeBsdfPrincipled")
    _inp(f, "Base Color", (0.78, 0.84, 0.88, 1))
    _inp(f, "Roughness", 0.28)
    _inp(f, "Transmission Weight", 0.25 if trans > 0 else 0.0)
    _inp(f, "IOR", 1.5)
    mix = N.new("ShaderNodeMixShader")
    Lk.new(fo.outputs["Fac"], mix.inputs[0])
    Lk.new(w.outputs["BSDF"], mix.inputs[1])
    Lk.new(f.outputs["BSDF"], mix.inputs[2])
    Lk.new(mix.outputs["Shader"], out.inputs["Surface"])
    return m


def mat_window(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    bs = N.get("Principled BSDF")
    _inp(bs, "Base Color", (0.9, 0.55, 0.2, 1))
    _inp(bs, "Roughness", 0.12)
    _inp(bs, "Emission Color", (1.0, 0.56, 0.22, 1))
    lit = N.new("ShaderNodeAttribute")
    lit.attribute_name = "lit"
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 3.2
    Lk.new(lit.outputs["Fac"], mul.inputs[0])
    Lk.new(mul.outputs["Value"], bs.inputs["Emission Strength"])
    return m


# ---- 場面
WATER_OBJS = []
_LAST = {"f": None}


def update_water(scene, *args):
    f = scene.frame_current
    if _LAST["f"] == f:
        return
    _LAST["f"] = f
    t = frame_t(f)
    for lvl, ob in WATER_OBJS:
        V, foam = lvl.verts(t)
        me = ob.data
        me.vertices.foreach_set("co", V.ravel())
        me.attributes["foam"].data.foreach_set("value", foam)
        me.update()


def build_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    sc = bpy.context.scene
    coll = sc.collection
    sc.render.fps = FPS
    sc.frame_start = 1
    sc.frame_end = FRAME_END
    sc.render.resolution_x = RES[0]
    sc.render.resolution_y = RES[1]
    sc.render.resolution_percentage = 100

    m_ship = mat_plastic("ブロック")
    m_win = mat_window("窓")
    m_water = mat_water("波・近", 0.3)
    m_water_far = mat_water("波・遠", 0.0)
    m_white = mat_plastic("しぶき・白", use_attr=False, color=WHITE)
    m_clear = mat_trans("しぶき・透明", (0.70, 0.84, 0.97), 0.10, 0.80)

    # 船
    root = bpy.data.objects.new("船", None)
    coll.objects.link(root)
    acc, accw = build_ship()
    make_mesh("船体", *acc.arrays(), m_ship, coll, root)
    make_mesh("窓", *accw.arrays(), m_win, coll, root)
    frames = np.arange(0, FRAME_END + 2)
    poses = [ship_pose(frame_t(f)) for f in frames]
    for i in range(3):
        bake(root, "rotation_euler", i, frames, [p[0][i] for p in poses])
        bake(root, "location", i, frames, [p[1][i] for p in poses])

    # 波
    for lvl in water_cells():
        acc_w = lvl.topology()
        V, L, S, SM, A = acc_w.arrays()
        V, foam = lvl.verts(0.0)
        A["foam"] = foam[:, None]
        ob = make_mesh(f"波_{lvl.s}", V, L, S, SM, A, m_water if lvl.s == 1 else m_water_far, coll)
        for nm in ("use_deform_motion",):
            _set(ob, nm, False)
            try:
                _set(ob.cycles, nm, False)
            except Exception:
                pass
        WATER_OBJS.append((lvl, ob))
    # 海の底（透ける波の向こうを暗く）
    me = bpy.data.meshes.new("海の底")
    me.from_pydata([(-3000, -3000, -9), (3000, -3000, -9), (3000, 3000, -9), (-3000, 3000, -9)], [], [(0, 1, 2, 3)])
    m_floor = bpy.data.materials.new("海の底")
    m_floor.use_nodes = True
    _inp(m_floor.node_tree.nodes.get("Principled BSDF"), "Base Color", (0.002, 0.006, 0.012, 1))
    me.materials.append(m_floor)
    coll.objects.link(bpy.data.objects.new("海の底", me))

    # 遠い海：柱の代わりに1枚の扇形の面（ぼけて見えない所に柱は要らない）
    az0 = math.atan2(*(CAM_TGT[:2] - CAM_POS[:2])[::-1])
    pts = []
    for rr, a in ((FAR_R - 15, -1), (6000.0, -1), (6000.0, 1), (FAR_R - 15, 1)):
        ang = az0 + a * math.radians(16.0)
        pts.append((CAM_POS[0] + rr * math.cos(ang), CAM_POS[1] + rr * math.sin(ang), -0.6))
    me = bpy.data.meshes.new("遠い海")
    me.from_pydata(pts, [], [(0, 1, 2, 3)])
    m_far = bpy.data.materials.new("遠い海")
    m_far.use_nodes = True
    fnt = m_far.node_tree
    fb = fnt.nodes.get("Principled BSDF")
    _inp(fb, "Base Color", (0.010, 0.040, 0.095, 1))
    _inp(fb, "Roughness", 0.16)
    fn = fnt.nodes.new("ShaderNodeTexNoise")
    _inp(fn, "Scale", 0.06)
    _inp(fn, "Detail", 6.0)
    fbump = fnt.nodes.new("ShaderNodeBump")
    _inp(fbump, "Strength", 0.35)
    fnt.links.new(fn.outputs["Fac"], fbump.inputs["Height"])
    fnt.links.new(fbump.outputs["Normal"], fb.inputs["Normal"])
    me.materials.append(m_far)
    coll.objects.link(bpy.data.objects.new("遠い海", me))

    # しぶき（部品ごとのオブジェクト、放物線を焼く）
    # 3周目：さいころ・瓦礫に見えたので、平たい 1×1 プレート中心・半透明の青白に
    kinds = []
    for k, (sx, sy, sz) in enumerate(((1, 1, PLATE), (1, 1, PLATE), (0, 0, PLATE), (2, 1, PLATE), (1, 1, PLATE))):
        a = Acc({"col": 4})
        if sx == 0:   # 丸い 1×1 プレート
            a.add(tpl_cyl(16, 0.48, PLATE - 0.01, c_top=0.03, c_bot=0.03, z0=-PLATE / 2, cap_bot=True),
                  [[0.0, 0.0, 0.0]], attrs={"col": jit(WHITE)})
            add_studs(a, np.zeros(1), np.zeros(1), np.full(1, PLATE / 2), jit(WHITE))
        else:
            add_bricks(a, [-sx / 2], [-sy / 2], [-sz / 2], [sx], [sy], [sz], jit(WHITE))
            if k != 4:   # 4 はタイル（凸なし）
                px = np.array([-sx / 2 + 0.5 + q for q in range(sx)])
                add_studs(a, px, np.zeros(sx), np.full(sx, sz / 2), jit(WHITE, sx))
        kinds.append(a.arrays())
    kind_mat = [m_clear, m_white, m_clear, m_clear, m_white]
    meshes = []
    for k, arrs in enumerate(kinds):
        tmp = make_mesh(f"しぶき型{k}", *arrs, kind_mat[k], coll)
        meshes.append(tmp.data)
        bpy.data.objects.remove(tmp, do_unlink=True)
    sp_coll = bpy.data.collections.new("しぶき")
    coll.children.link(sp_coll)
    fr, P, ROT, alive, kind = spray_plan()
    for n in range(SPRAY_N):
        ob = bpy.data.objects.new(f"しぶき{n:04d}", meshes[kind[n]])
        sp_coll.objects.link(ob)
        for i in range(3):
            bake(ob, "location", i, fr, P[n, :, i])
            bake(ob, "rotation_euler", i, fr, ROT[n, :, i])
        sc_v = np.append(alive[n].astype(float) * SPRAY_SCALE, 0.0)
        fr2 = np.append(fr, fr[-1] + 1)
        for i in range(3):
            bake(ob, "scale", i, fr2, sc_v, interp="CONSTANT")

    # カメラ
    cd = bpy.data.cameras.new("カメラ")
    cam = bpy.data.objects.new("カメラ", cd)
    coll.objects.link(cam)
    sc.camera = cam
    cd.lens = CAM_LENS
    cd.sensor_width = 36.0
    cd.sensor_fit = "AUTO"
    cd.clip_start = 1.0
    cd.clip_end = 6000.0
    cam.location = CAM_POS.tolist()
    base_rot = look_euler(CAM_POS, CAM_TGT)
    for i in range(3):
        bake(cam, "rotation_euler", i, frames, [base_rot[i] + cam_shake(frame_t(f))[i] for f in frames])
    fe = bpy.data.objects.new("ピント", None)
    fe.location = FOCUS_PT.tolist()
    coll.objects.link(fe)
    cd.dof.use_dof = not MODE.startswith("workbench")
    cd.dof.focus_object = fe
    cd.dof.aperture_fstop = (CAM_LENS * 1e-3) / ((CAM_LENS / TOY_FSTOP) * 1e-3 / UNIT_M)
    _set(cd.dof, "aperture_blades", 7)

    # 光：月（前上から）・逆光（奥から＝しぶきと波頭の縁）・弱い起こし・雷
    def sun(name, d, energy, color, angle):
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.color = color
        ld.angle = math.radians(angle)
        ob = bpy.data.objects.new(name, ld)
        coll.objects.link(ob)
        d = np.asarray(d, float)
        ob.rotation_euler = look_euler(np.zeros(3), -d).tolist()
        return ob

    sun("月", (1.0, 0.35, 0.95), 2.2, (0.62, 0.74, 1.0), 4.0)
    sun("逆光", (-0.85, -0.75, 0.30), 3.2, (0.55, 0.68, 1.0), 2.0)
    sun("起こし", (0.6, 0.8, 0.25), 0.12, (0.7, 0.78, 1.0), 20.0)
    ld = bpy.data.lights.new("雷", "AREA")
    ld.shape = "RECTANGLE"
    ld.size = 90.0
    ld.size_y = 40.0
    ld.color = (0.78, 0.86, 1.0)
    lo = bpy.data.objects.new("雷", ld)
    coll.objects.link(lo)
    lo.location = (130.0, 190.0, 110.0)
    lo.rotation_euler = look_euler(np.array(lo.location), np.array([5.0, 0.0, 6.0])).tolist()
    bake(ld, "energy", -1 if False else 0, [1, 18, 19, 20, 21], [0, 0, 6.0e5, 2.2e5, 0], interp="CONSTANT")

    # 空：嵐の夜（ほぼ黒の紺、地平線だけわずかに明るい）
    w = bpy.data.worlds.new("夜")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    # 3周目：平たい紺だったので、水平線の明るみ＋低い雲の濃淡（筋は作らない）
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.060, 0.074, 0.100, 1)
    ramp.color_ramp.elements[1].position = 0.30
    ramp.color_ramp.elements[1].color = (0.0025, 0.0035, 0.007, 1)
    e = ramp.color_ramp.elements.new(0.05)
    e.color = (0.026, 0.035, 0.056, 1)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2.2, 2.2, 5.0)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    cn = nt.nodes.new("ShaderNodeTexNoise")
    _inp(cn, "Scale", 2.6)
    _inp(cn, "Detail", 6.0)
    _inp(cn, "Roughness", 0.62)
    nt.links.new(mp.outputs["Vector"], cn.inputs["Vector"])
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.38
    cr.color_ramp.elements[1].position = 0.62
    nt.links.new(cn.outputs["Fac"], cr.inputs["Fac"])
    bandr = nt.nodes.new("ShaderNodeValToRGB")   # 雲は低い所だけ
    bandr.color_ramp.elements[0].position = 0.0
    bandr.color_ramp.elements[0].color = (0, 0, 0, 1)
    bandr.color_ramp.elements[1].position = 0.04
    bandr.color_ramp.elements[1].color = (1, 1, 1, 1)
    e2 = bandr.color_ramp.elements.new(0.22)
    e2.color = (1, 1, 1, 1)
    e3 = bandr.color_ramp.elements.new(0.40)
    e3.color = (0, 0, 0, 1)
    nt.links.new(sep.outputs["Z"], bandr.inputs["Fac"])
    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY_ADD"
    m1.inputs[1].default_value = 1.0
    m1.inputs[2].default_value = -0.45
    nt.links.new(cr.outputs["Color"], m1.inputs[0])
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    nt.links.new(m1.outputs["Value"], m2.inputs[0])
    nt.links.new(bandr.outputs["Color"], m2.inputs[1])
    m3 = nt.nodes.new("ShaderNodeMath")
    m3.operation = "ADD"
    m3.inputs[1].default_value = 1.0
    nt.links.new(m2.outputs["Value"], m3.inputs[0])
    vs = nt.nodes.new("ShaderNodeVectorMath")
    vs.operation = "SCALE"
    nt.links.new(ramp.outputs["Color"], vs.inputs[0])
    nt.links.new(m3.outputs["Value"], vs.inputs["Scale"])
    nt.links.new(vs.outputs["Vector"], bg.inputs["Color"])
    _inp(bg, "Strength", 1.0)
    w.color = (0.23, 0.23, 0.23)

    # 描き方
    # workbench：クラウド（GitHub Actions）では Workbench/EEVEE が libEGL 不足で落ちるので、
    #            Cycles に灰色の材質を上書きして「ソリッド表示」と同じ見た目で描く（ぼけ・ぶれ・窓の光なし）
    # workbench_engine：GPU のある機械で本物のワークベンチを使うとき
    if MODE == "workbench":
        g = bpy.data.materials.new("灰色")
        g.use_nodes = True
        gb = g.node_tree.nodes.get("Principled BSDF")
        _inp(gb, "Base Color", (0.55, 0.55, 0.55, 1))
        _inp(gb, "Roughness", 0.6)
        _inp(gb, "Specular IOR Level", 0.25)
        bpy.context.view_layer.material_override = g
        for ob in bpy.data.objects:
            if ob.type == "LIGHT":
                ob.hide_render = True
        nt.links.clear()
        _inp(bg, "Color", (0.23, 0.23, 0.23, 1))
        _inp(bg, "Strength", 2.5)
        sc.render.engine = "CYCLES"
        _set(sc.cycles, "device", "CPU")
        sc.cycles.samples = 16
        _set(sc.cycles, "use_denoising", True)
        _set(sc.cycles, "max_bounces", 2)
        sc.render.use_motion_blur = False
        _set(sc.view_settings, "view_transform", "Standard")
    elif MODE == "workbench_engine":
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        _set(sh, "light", "STUDIO")
        _set(sh, "color_type", "SINGLE")
        _set(sh, "single_color", (0.8, 0.8, 0.8))
        _set(sh, "show_cavity", True)
        _set(sh, "cavity_type", "BOTH")
        _set(sh, "show_shadows", False)
        _set(sh, "background_type", "WORLD")
        _set(sc.display, "render_aa", "8")
        _set(sc.render, "use_motion_blur", False)
        _set(sc.view_settings, "view_transform", "Standard")
    else:
        sc.render.engine = "CYCLES"
        cy = sc.cycles
        _set(cy, "device", "CPU")
        cy.samples = 16                      # 3周目：64→16（デノイズは残す）
        _set(cy, "use_adaptive_sampling", True)
        _set(cy, "adaptive_threshold", 0.04)
        _set(cy, "use_denoising", True)
        _set(cy, "denoiser", "OPENIMAGEDENOISE")
        _set(cy, "denoising_input_passes", "RGB_ALBEDO_NORMAL")
        _set(cy, "denoising_prefilter", "ACCURATE")
        _set(cy, "max_bounces", 6)
        _set(cy, "diffuse_bounces", 2)
        _set(cy, "glossy_bounces", 2)
        _set(cy, "transmission_bounces", 4)
        _set(cy, "transparent_max_bounces", 4)
        _set(cy, "volume_bounces", 0)
        _set(cy, "caustics_reflective", False)
        _set(cy, "caustics_refractive", False)
        _set(cy, "blur_glossy", 1.0)
        _set(cy, "sample_clamp_indirect", 4.0)
        _set(cy, "use_light_tree", True)
        sc.render.use_motion_blur = True
        _set(sc.render, "motion_blur_shutter", 0.5)
        _set(cy, "motion_blur_position", "CENTER")
        _set(sc.render, "motion_blur_position", "CENTER")
        _set(sc.view_settings, "view_transform", "AgX")
        _set(sc.view_settings, "look", "AgX - Medium High Contrast")
        _set(sc.view_settings, "exposure", 0.35)
    sc.render.image_settings.file_format = "PNG"

    bpy.app.handlers.frame_change_pre.append(update_water)
    update_water(sc)


if bpy is not None:
    build_scene()
