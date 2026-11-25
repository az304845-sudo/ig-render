# k32「城」冒頭の1コマ（Blender 4.2 / Cycles）。場面を組むだけ。描き出しは外から（-o -F -s -e -a）。
# 外の素材は使わない：石・漆喰・下見板・瓦・縄・草・空は全部この中の手続きで作る。
# 乱数は固定の種。時計は使わない。
# 手元（bpy なし）で `python3 scene.py --dry 出力.png` とすると、形だけ作って構図を点で投影して確かめる。
import math, sys, time
import numpy as np

try:
    import bpy
    from mathutils import Vector
    DRY = False
except ImportError:
    bpy = None
    DRY = True

T0 = time.time()
def log(*a):
    print('[k32]', f'{time.time()-T0:6.1f}s', *a, flush=True)

W, H = 1080, 1920
LENS, SENSOR_H = 35.0, 36.0
TAN_V = (SENSOR_H / 2) / LENS
TAN_H = TAN_V * W / H

# ---------------------------------------------------------------- ノイズ（numpy・固定の種）
def _h(ix, iy, iz, seed):
    h = (ix.astype(np.uint32) * np.uint32(0x8da6b343)) ^ (iy.astype(np.uint32) * np.uint32(0xd8163841)) \
        ^ (iz.astype(np.uint32) * np.uint32(0xcb1ab31f)) ^ np.uint32((seed * 0x9e3779b1) & 0xffffffff)
    h ^= h >> np.uint32(13); h *= np.uint32(0x5bd1e995); h ^= h >> np.uint32(15)
    return h.astype(np.float64) / 4294967296.0

def vnoise(P, seed):
    I = np.floor(P); F = P - I; S = F * F * (3 - 2 * F); I = I.astype(np.int64)
    out = np.zeros(len(P))
    for dx in (0, 1):
        wx = S[:, 0] if dx else 1 - S[:, 0]
        for dy in (0, 1):
            wy = S[:, 1] if dy else 1 - S[:, 1]
            for dz in (0, 1):
                wz = S[:, 2] if dz else 1 - S[:, 2]
                out += wx * wy * wz * _h(I[:, 0] + dx, I[:, 1] + dy, I[:, 2] + dz, seed)
    return out

def fbm(P, seed, oct=4):
    v = np.zeros(len(P)); a = 1.0; t = 0.0; Q = P.copy()
    for i in range(oct):
        v += a * vnoise(Q, seed + i * 17); t += a; Q = Q * 2.03 + 0.37; a *= 0.5
    return v / t

def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

def nrm(v):
    v = np.asarray(v, float); return v / np.linalg.norm(v)

# ---------------------------------------------------------------- 形を集める（Blender では物体に、dry では配列に）
OBJS = []
def emit(name, V, F, mat, attrs=None, smooth=False, bevel=None, anim=None):
    V = np.asarray(V, float)
    OBJS.append((name, mat, V, F))
    if DRY:
        return
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], [list(map(int, f)) for f in F])
    me.update(calc_edges=True)
    if attrs:
        for k, arr in attrs.items():
            a = me.attributes.new(k, 'FLOAT', 'POINT'); a.data.foreach_set('value', np.asarray(arr, np.float32))
    me.polygons.foreach_set('use_smooth', np.full(len(me.polygons), smooth, dtype=bool))
    me.update()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(MATS[mat])
    if bevel:
        m = ob.modifiers.new('bev', 'BEVEL'); m.width = bevel; m.segments = 2; m.limit_method = 'ANGLE'
    if anim:
        anim(ob)
    return ob

class Builder:
    def __init__(self):
        self.V = []; self.F = []; self.n = 0
    def add(self, V, F):
        V = np.asarray(V, float); self.V.append(V); self.F.extend([[i + self.n for i in f] for f in F]); self.n += len(V)
    def beam(self, p0, p1, up, w, h, seg=1, dz=None):
        # p0→p1 を軸にした角材（断面 w×h）。seg で軸方向に分ける（反りを付けるため）
        p0 = np.asarray(p0, float); p1 = np.asarray(p1, float); a = nrm(p1 - p0)
        s = nrm(np.cross(a, up)); u = np.cross(s, a)
        corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        V = []
        for i in range(seg + 1):
            c = p0 + (p1 - p0) * i / seg
            for cx, cy in corners:
                V.append(c + s * cx * w / 2 + u * cy * h / 2)
        F = []
        for i in range(seg):
            for k in range(4):
                a0 = i * 4 + k; a1 = i * 4 + (k + 1) % 4
                F.append([a0, a1, a1 + 4, a0 + 4])
        F.append([3, 2, 1, 0]); last = seg * 4; F.append([last, last + 1, last + 2, last + 3])
        self.add(V, F)
    def sheet(self, fn, nu, nv):
        V = [fn(i / nu, j / nv) for j in range(nv + 1) for i in range(nu + 1)]
        F = [[j * (nu + 1) + i, j * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i] for j in range(nv) for i in range(nu)]
        self.add(V, F)
    def tube(self, pts, r, k=8, cap=False):
        pts = np.asarray(pts, float); n = len(pts)
        T = np.gradient(pts, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)
        ref = np.array([0, 0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0, 0])
        N = nrm(np.cross(T[0], ref)); V = []
        for i in range(n):
            if i > 0:
                N = N - T[i] * np.dot(N, T[i]); N = nrm(N)
            B = np.cross(T[i], N)
            rr = r[i] if hasattr(r, '__len__') else r
            for j in range(k):
                th = 2 * math.pi * j / k
                V.append(pts[i] + rr * (math.cos(th) * N + math.sin(th) * B))
        F = [[i * k + j, i * k + (j + 1) % k, (i + 1) * k + (j + 1) % k, (i + 1) * k + j] for i in range(n - 1) for j in range(k)]
        if cap:
            c0 = len(V); V.append(pts[0]); c1 = len(V); V.append(pts[-1])
            for j in range(k):
                F.append([c0, (j + 1) % k, j]); F.append([c1, (n - 1) * k + j, (n - 1) * k + (j + 1) % k])
        self.add(V, F)
    def deform(self, fn):
        self.V = [fn(v) for v in self.V]
    def emit(self, name, mat, **kw):
        if not self.V: return
        return emit(name, np.concatenate(self.V), self.F, mat, **kw)

# ---------------------------------------------------------------- 石垣の形（扇の勾配）と角
A_SLOPE, HT = 0.72, 12.0
def d(z): return A_SLOPE * z - A_SLOPE / (2 * HT) * z * z
def dp(z): return A_SLOPE - A_SLOPE * z / HT
ZS = np.linspace(0, HT, 2401); SS = np.concatenate([[0], np.cumsum(np.sqrt(1 + dp(ZS[:-1]) ** 2) * (ZS[1] - ZS[0]))])
def z_of_s(s): return float(np.interp(s, SS, ZS))
# 面A：正面（-Y を向く）。y = d(z)、角から左（-X）へ u。面B：右の側面（+X を向く）。x = -d(z)、角から奥（+Y）へ u
def frame(face, z):
    g = dp(z)
    if face == 'A':
        Hh = np.array([1.0, 0, 0]); T = nrm([0, g, 1]); N = nrm([0, -1, g])
    else:
        Hh = np.array([0, 1.0, 0]); T = nrm([-g, 0, 1]); N = nrm([1, 0, g])
    return Hh, T, N
def surf(face, u, z):
    return np.array([-d(z) - u, d(z), z]) if face == 'A' else np.array([-d(z), d(z) + u, z])

# 細かく割った立方体（頂点を共有）
def cube_template(m):
    idx = -np.ones((m + 1, m + 1, m + 1), int); V = []
    for i in range(m + 1):
        for j in range(m + 1):
            for k in range(m + 1):
                if i in (0, m) or j in (0, m) or k in (0, m):
                    idx[i, j, k] = len(V); V.append((i / m - 0.5, j / m - 0.5, k / m - 0.5))
    F = []
    for a, (b, c) in ((0, (1, 2)), (1, (2, 0)), (2, (0, 1))):
        for side in (0, m):
            for p in range(m):
                for q in range(m):
                    def at(pp, qq):
                        co = [0, 0, 0]; co[a] = side; co[b] = pp; co[c] = qq; return idx[tuple(co)]
                    quad = [at(p, q), at(p + 1, q), at(p + 1, q + 1), at(p, q + 1)]
                    F.append(quad if side == m else quad[::-1])
    return np.array(V), F
TPL = {m: cube_template(m) for m in (4, 7, 10)}

def stone_local(w, h, dd, rng, seed, corner=False, m=7, rough=1.0):
    TV, TF = TPL[m]
    P = TV * np.array([w, h, dd]); hw, hh, hd = w / 2, h / 2, dd / 2; sz = min(w, h)
    rad = sz * (0.01 if corner else 0.01 + 0.025 * rng.random())
    inner = np.array([hw - rad, hh - rad, hd - min(rad, hd * 0.7)])
    Q = np.clip(P, -inner, inner); D = P - Q; L = np.linalg.norm(D, axis=1, keepdims=True)
    Dn = D / np.maximum(L, 1e-9); P = Q + Dn * rad
    if not corner:
        shear = (rng.random() - 0.5) * 0.3; taper = (rng.random() - 0.5) * 0.25
        P[:, 0] = P[:, 0] * (1 + taper * P[:, 1] / hh) + shear * P[:, 1]
    fz = sstep(0, hd, P[:, 2])
    dome = sz * (0.005 + 0.025 * rng.random())
    P[:, 2] += fz * (dome * (1 - 0.6 * (P[:, 0] / hw) ** 2 - 0.6 * (P[:, 1] / hh) ** 2) + (rng.random() - 0.5) * 0.05 * P[:, 0] + (rng.random() - 0.5) * 0.05 * P[:, 1])
    off = np.array([seed * 3.17, seed * 1.31, seed * 2.07])
    disp = (fbm(P * 2.0 + off, seed, 4) - 0.5) * 0.06 * sz * rough + (fbm(P * 9.0 + off, seed + 5, 3) - 0.5) * 0.02 * rough
    P += Dn * disp[:, None]
    nc = (1 + rng.integers(0, 2)) if corner else (3 + rng.integers(0, 4))
    for _ in range(nc):
        cx = (1 if rng.random() < 0.5 else -1) * hw * (0.4 + 0.6 * rng.random())
        cy = (1 if rng.random() < 0.5 else -1) * hh * (0.4 + 0.6 * rng.random())
        n = nrm([cx / hw * (0.6 + rng.random() * 0.5), cy / hh * (0.6 + rng.random() * 0.5), 0.5 + rng.random() * 0.9])
        o = np.dot(n, [cx, cy, hd]) - sz * ((0.03 + 0.06 * rng.random()) if corner else (0.05 + 0.12 * rng.random()))
        e = P @ n - o; P -= np.outer(np.maximum(e, 0), n)
    return P, TF

class StoneSet:
    def __init__(self):
        self.V = []; self.F = []; self.R = []; self.n = 0
    def put(self, P, TF, origin, Hh, T, N, rot, rv):
        c, s = math.cos(rot), math.sin(rot)
        x = P[:, 0] * c - P[:, 1] * s; y = P[:, 0] * s + P[:, 1] * c
        Wd = origin + np.outer(x, Hh) + np.outer(y, T) + np.outer(P[:, 2], N)
        self.V.append(Wd); self.F.extend([[i + self.n for i in f] for f in TF]); self.R.append(np.full(len(Wd), rv)); self.n += len(Wd)
    def emit(self, name, mat):
        return emit(name, np.concatenate(self.V), self.F, mat, attrs={'srand': np.concatenate(self.R)}, smooth=True)

GRASS = Builder()
def tuft(base, N, rng, scale=1.0):
    k = 6 + rng.integers(0, 9)
    for _ in range(k):
        L = (0.05 + 0.16 * rng.random()) * scale; wid = 0.006 + 0.004 * rng.random()
        dirv = nrm(N + np.array([rng.normal() * 0.5, rng.normal() * 0.5, 0.35 + rng.normal() * 0.3]))
        side = nrm(np.cross(dirv, [0, 0, 1]) + 1e-6)
        b0 = base + side * (rng.random() - 0.5) * 0.05
        V = []
        for t in (0, 0.33, 0.66):
            p = b0 + dirv * L * t + np.array([0, 0, -0.5 * L * t * t * (0.6 + rng.random())])
            ww = wid * (1 - t * 0.8)
            V += [p - side * ww, p + side * ww]
        V.append(b0 + dirv * L + np.array([0, 0, -0.45 * L * (0.6 + rng.random())]))
        F = [[0, 1, 3, 2], [2, 3, 5, 4], [4, 5, 6]]
        GRASS.add(V, F)

def build_wall():
    rng = np.random.default_rng(32032)
    sets = {'A': StoneSet(), 'B': StoneSet()}
    s_top = SS[-1]; s = 0.0; course = 0; seed = 1
    UMAX = float(os.environ.get('K32_UMAX', '14'))
    while s < s_top - 0.05:
        ch = 0.36 + rng.random() * 0.32
        if s + ch > s_top - 0.15: ch = s_top - s
        zc = z_of_s(s + ch / 2)
        L = 1.1 + rng.random() * 0.35; S_ = 0.52 + rng.random() * 0.1
        long_on = 'A' if course % 2 == 0 else 'B'
        for face in ('A', 'B'):
            Hh, T, N = frame(face, zc); ss = sets[face]
            sgn = 1 if face == 'A' else -1          # 面A は +H が角向き、面B は -H が角向き
            if face == long_on:
                w, dd = L, S_; u0 = L
            else:
                w, dd = S_, L; u0 = S_
            prot = 0.02 + rng.random() * 0.012
            P, TF = stone_local(w - 0.012, ch - 0.014, dd, rng, seed, corner=True, m=10); seed += 1
            # 角の石：外の端を他方の面の外に合わせる
            org = surf(face, w / 2 - prot, zc) + N * (prot - dd / 2)
            ss.put(P, TF, org, Hh, T, N, 0.0, rng.random())
            u = u0
            while u < UMAX:
                w = 0.38 + rng.random() * 0.7 * (1.5 if rng.random() < 0.2 else 1)
                gap = 0.014 + rng.random() * 0.02
                hh = ch - gap - rng.random() * 0.06
                dd = 0.45 + rng.random() * 0.3
                zz = z_of_s(s + ch / 2 + (rng.random() - 0.5) * 0.03)
                Hh2, T2, N2 = frame(face, zz)
                prot = -0.02 + rng.random() * 0.05
                far = u > 6.5
                P, TF = stone_local(w - gap, hh, dd, rng, seed, m=4 if far else 7); seed += 1
                org = surf(face, u + w / 2, zz) + N2 * (prot - dd / 2)
                ss.put(P, TF, org, Hh2, T2, N2, (rng.random() - 0.5) * 0.06 * sgn, rng.random())
                # 間詰め石と草
                if rng.random() < 0.7 and not far:
                    for _ in range(1 + rng.integers(0, 2)):
                        q = 0.07 + rng.random() * 0.1
                        zf = z_of_s(s + (0.03 if rng.random() < 0.5 else ch - 0.03) + (rng.random() - 0.5) * 0.04)
                        Hf, Tf, Nf = frame(face, zf)
                        P, TF = stone_local(q * (1 + rng.random() * 0.6), q, 0.2, rng, seed, m=4); seed += 1
                        org = surf(face, u + w + (rng.random() - 0.5) * 0.05, zf) + Nf * (-0.05 - rng.random() * 0.03 - 0.1)
                        ss.put(P, TF, org, Hf, Tf, Nf, (rng.random() - 0.5) * 1.2, rng.random())
                if not far and rng.random() < (0.32 if zc < 4 or zc > 10 else 0.16):
                    zg = z_of_s(s + (0.02 if rng.random() < 0.6 else ch / 2))
                    Hg, Tg, Ng = frame(face, zg)
                    tuft(surf(face, u + w + (rng.random() - 0.5) * 0.06, zg) - Ng * 0.03, Ng, rng)
                u += w
        s += ch; course += 1
    log('stones', sets['A'].n + sets['B'].n, 'verts')
    sets['A'].emit('wallA', 'stone'); sets['B'].emit('wallB', 'stone')
    # 石の裏の土（目地から見える）
    for face in ('A', 'B'):
        b = Builder()
        def fn(a, v, face=face):
            z = v * HT; Hh, T, N = frame(face, z); return surf(face, a * UMAX, z) - N * 0.11
        b.sheet(fn, 30, 60)
        b.emit('soil' + face, 'soil')
    # 地面（照り返しのため・画面には入らない）
    g = Builder(); g.sheet(lambda a, v: np.array([-40 + 80 * a, -40 + 80 * v, -0.02]), 4, 4); g.emit('ground', 'ground')

# ---------------------------------------------------------------- 櫓
D_TOP = d(HT)
XY, YY = -D_TOP - 0.25, D_TOP + 0.25            # 櫓の角
OV = 1.4; XE, YE = XY + OV, YY - OV               # 軒先の角
ZE = 16.0; PITCH = math.tan(math.radians(28))     # 軒先の瓦の上の高さ・屋根の勾配
EXT = 11.0                                        # 角からの長さ
def lift(V):
    V = V.copy()
    u = np.maximum(np.maximum(XE - V[:, 0], 0), np.maximum(V[:, 1] - YE, 0))
    V[:, 2] += 0.75 * np.clip(1 - u / 4.5, 0, None) ** 2
    return V
BAY = dict(x0=XY - 2.35, x1=XY - 0.55, yo=YY - 0.78, z0=12.4, z1=14.05)

def build_yagura():
    rng = np.random.default_rng(1601)
    pl = Builder(); bd = Builder(); dk = Builder(); wd = Builder()
    # 天端（石垣の上の平ら）
    dk.beam([-D_TOP - EXT, D_TOP + 0.2, 11.98], [-D_TOP + 0.03, D_TOP + 0.2, 11.98], [0, 0, 1], 0.45, 0.05)
    dk.beam([-D_TOP - 0.2, D_TOP - 0.03, 11.98], [-D_TOP - 0.2, D_TOP + EXT, 11.98], [0, 0, 1], 0.45, 0.05)
    # 壁：面A（y=YY）と面B（x=XY）。下は下見板、上は漆喰
    zb0, zb1, zw1 = 12.0, 13.65, 16.75
    pl.beam([XY - EXT, YY + 0.15, (zb1 + zw1) / 2], [XY, YY + 0.15, (zb1 + zw1) / 2], [0, 0, 1], 0.3, zw1 - zb1)
    pl.beam([XY - 0.15, YY + 0.31, (zb1 + zw1) / 2], [XY - 0.15, YY + EXT, (zb1 + zw1) / 2], [0, 0, 1], 0.3, zw1 - zb1)
    dk.beam([XY - EXT, YY + 0.2, (zb0 + zb1) / 2], [XY - 0.05, YY + 0.2, (zb0 + zb1) / 2], [0, 0, 1], 0.35, zb1 - zb0)
    dk.beam([XY - 0.2, YY + 0.4, (zb0 + zb1) / 2], [XY - 0.2, YY + EXT, (zb0 + zb1) / 2], [0, 0, 1], 0.35, zb1 - zb0)
    # 下見板（横板を下へ少しずつ重ね、下の縁を外へ出す）と押縁
    bh, step = 0.24, 0.205
    for face in ('A', 'B'):
        k = 0; z = zb1 - bh / 2
        while z - bh / 2 > zb0 - 0.02:
            tilt = 0.022
            if face == 'A':
                xa, xb = XY - EXT, XY + 0.01
                y = YY - 0.005 - k * 0.0
                p0 = [xa, y, z]; p1 = [xb, y, z]; up = nrm([0, -tilt / bh * 1.0, 1])
                # 下の縁を外（-Y）へ：軸まわりに傾ける
                bd.beam(p0, p1, nrm([0, tilt / bh, 1]), 0.022, bh)
            else:
                xa = XY + 0.005
                bd.beam([xa, YY - 0.01, z], [xa, YY + EXT, z], nrm([-tilt / bh, 0, 1]), 0.022, bh)
            z -= step; k += 1
        # 押縁（縦の細い木）
        for i in range(int(EXT / 0.9)):
            o = 0.25 + i * 0.9 + (rng.random() - 0.5) * 0.02
            if face == 'A':
                if XY - o < BAY['x1'] + 0.05 and XY - o > BAY['x0'] - 0.05: continue
                bd.beam([XY - o, YY - 0.03, zb0], [XY - o, YY - 0.03, zb1], [0, -1, 0], 0.045, 0.03)
            else:
                bd.beam([XY + 0.03, YY + o, zb0], [XY + 0.03, YY + o, zb1], [1, 0, 0], 0.045, 0.03)
    # 水切り（板の上の小さな庇）
    bd.beam([XY - EXT, YY - 0.04, zb1 + 0.02], [XY + 0.06, YY - 0.04, zb1 + 0.02], [0, 0, 1], 0.1, 0.035)
    bd.beam([XY + 0.04, YY - 0.06, zb1 + 0.02], [XY + 0.04, YY + EXT, zb1 + 0.02], [0, 0, 1], 0.1, 0.035)
    # 窓（面B）：塗り込めの太い格子と暗い中
    wy0, wy1, wz0, wz1 = YY + 1.1, YY + 2.4, 14.25, 15.35
    dk.beam([XY + 0.012, wy0, (wz0 + wz1) / 2], [XY + 0.012, wy1, (wz0 + wz1) / 2], [0, 0, 1], 0.02, wz1 - wz0)
    for i in range(9):
        yb = wy0 + 0.07 + i * (wy1 - wy0 - 0.14) / 8
        pl.beam([XY + 0.06, yb, wz0], [XY + 0.06, yb, wz1], [1, 0, 0], 0.075, 0.075)
    pl.beam([XY + 0.07, wy0 - 0.08, wz0 - 0.05], [XY + 0.07, wy1 + 0.08, wz0 - 0.05], [0, 0, 1], 0.12, 0.1)
    pl.beam([XY + 0.07, wy0 - 0.08, wz1 + 0.05], [XY + 0.07, wy1 + 0.08, wz1 + 0.05], [0, 0, 1], 0.12, 0.1)
    # 狭間（面B・小さな四角と丸）
    for yb, kind in ((YY + 3.2, 0), (YY + 3.8, 1)):
        if kind == 0:
            dk.beam([XY + 0.01, yb - 0.1, 14.3], [XY + 0.01, yb + 0.1, 14.3], [0, 0, 1], 0.015, 0.2)
        else:
            dk.tube([[XY + 0.0, yb, 14.3], [XY + 0.02, yb, 14.3]], 0.09, k=16, cap=True)
    # ---- 石落とし（壁から張り出した箱。底板が1枚開く）
    b = BAY; th = 0.1
    pl.beam([b['x0'], b['yo'] + 0.06, (13.2 + b['z1']) / 2], [b['x1'], b['yo'] + 0.06, (13.2 + b['z1']) / 2], [0, 0, 1], 0.12, b['z1'] - 13.2)
    dk.beam([b['x0'] - 0.01, b['yo'] + 0.08, (b['z0'] + 13.2) / 2], [b['x1'] + 0.01, b['yo'] + 0.08, (b['z0'] + 13.2) / 2], [0, 0, 1], 0.14, 13.2 - b['z0'])
    for xs in (b['x0'] + 0.06, b['x1'] - 0.06):
        pl.beam([xs, b['yo'] + 0.125, (13.2 + b['z1']) / 2], [xs, YY - 0.01, (13.2 + b['z1']) / 2], [0, 0, 1], 0.12, b['z1'] - 13.2 - 0.004)
        dk.beam([xs, b['yo'] + 0.155, (b['z0'] + 13.2) / 2], [xs, YY - 0.01, (b['z0'] + 13.2) / 2], [0, 0, 1], 0.14, 13.2 - b['z0'] - 0.004)
    # 板の段（張り出しの下見板）
    z = 13.2 - 0.12
    while z > b['z0'] + 0.05:
        bd.beam([b['x0'] - 0.02, b['yo'] - 0.005, z], [b['x1'] + 0.02, b['yo'] - 0.005, z], nrm([0, 0.09, 1]), 0.02, 0.24); z -= 0.2
    # 底：奥の固定の板と、手前の縁。間が開いた穴
    hy0, hy1 = YY - 0.3, b['yo'] + 0.1           # 穴の奥と手前
    wd.beam([b['x0'], (YY + hy0) / 2, b['z0']], [b['x1'], (YY + hy0) / 2, b['z0']], [0, 0, 1], YY - hy0, th)
    wd.beam([b['x0'], (hy1 + b['yo']) / 2, b['z0']], [b['x1'], (hy1 + b['yo']) / 2, b['z0']], [0, 0, 1], hy1 - b['yo'], th)
    wd.beam([b['x0'] + 0.06, (hy0 + hy1) / 2, b['z0']], [b['x0'] + 0.14, (hy0 + hy1) / 2, b['z0']], [0, 0, 1], hy0 - hy1, th)
    wd.beam([b['x1'] - 0.14, (hy0 + hy1) / 2, b['z0']], [b['x1'] - 0.06, (hy0 + hy1) / 2, b['z0']], [0, 0, 1], hy0 - hy1, th)
    # 開いた底板：奥の縁を軸に、下へ 72 度
    ang = math.radians(72); Ld = hy0 - hy1 - 0.02
    pa = np.array([0, hy0, b['z0'] - th / 2]); tip = pa + np.array([0, -math.cos(ang) * Ld, -math.sin(ang) * Ld])
    for xs in np.linspace(b['x0'] + 0.2, b['x1'] - 0.2, 4):
        wd.beam([xs, pa[1], pa[2]], [xs, tip[1], tip[2]], [1, 0, 0], 0.03, (b['x1'] - b['x0'] - 0.4) / 4 + 0.01)
    # 腕木（持ち送り）
    for xs in (b['x0'] + 0.25, (b['x0'] + b['x1']) / 2, b['x1'] - 0.25):
        pl.beam([xs, YY + 0.05, b['z0'] - 0.2], [xs, b['yo'] + 0.05, b['z0'] - 0.13], [0, 0, 1], 0.13, 0.2)
    # 中の暗がり
    dk.beam([b['x0'] + 0.15, (YY + b['yo']) / 2, 12.9], [b['x1'] - 0.15, (YY + b['yo']) / 2, 12.9], [0, 0, 1], YY - b['yo'] - 0.3, 0.9)
    # 張り出しの屋根（片流れ）と瓦の端
    bz, bf = b['z1'] + 0.05, b['yo'] - 0.28
    rf = Builder()
    rf.sheet(lambda a, v: np.array([b['x0'] - 0.3 + a * (b['x1'] - b['x0'] + 0.6), bf + v * (YY - bf), bz + 0.12 + v * (YY - bf) * 0.55]), 8, 4)
    rf.emit('bayRoof', 'tile')
    pl.sheet(lambda a, v: np.array([b['x0'] - 0.3 + a * (b['x1'] - b['x0'] + 0.6), bf + v * (YY - bf), bz - 0.02 + v * (YY - bf) * 0.55]), 8, 4)
    for xs in np.arange(b['x0'] - 0.22, b['x1'] + 0.3, 0.26):
        pl.beam([xs, bf + 0.03, bz], [xs, YY, bz + (YY - bf) * 0.55], [0, 0, 1], 0.06, 0.08)
    tl = Builder()
    for xs in np.arange(b['x0'] - 0.2, b['x1'] + 0.3, 0.26):
        tl.tube([[xs, bf - 0.02, bz + 0.17], [xs, bf + 0.5, bz + 0.17 + 0.28]], 0.06, k=12, cap=True)
    tl.emit('bayTiles', 'tile', smooth=True)
    # ---- 大きな軒（垂木・軒裏・茅負・瓦の端・隅棟・鬼瓦）。角で反り上がる
    def zr(q):  # 軒先からの奥行き q での垂木の上
        return ZE - 0.16 + q * PITCH
    eave_pl = Builder(); eave_tl = Builder()
    for side in ('A', 'B'):
        def P(sv, q):  # sv=角からの長さ, q=軒先から奥
            return np.array([XE - sv, YE + q, 0.0]) if side == 'A' else np.array([XE - q, YE + sv, 0.0])
        # 軒裏の板（垂木の上）
        def soffit(a, v, P=P):
            sv = a * EXT; q = min(sv, OV) * v; p = P(sv, q); p[2] = zr(q) + 0.01; return p
        eave_pl.sheet(soffit, 60, 6)
        # 垂木
        sv = 0.12
        while sv < EXT:
            qe = min(sv, OV + 0.05)
            p0 = P(sv, 0.03); p1 = P(sv, qe)
            p0[2] = zr(0.03) - 0.06; p1[2] = zr(qe) - 0.06
            eave_pl.beam(p0, p1, [0, 0, 1], 0.09, 0.12, seg=3)
            sv += 0.31 + (rng.random() - 0.5) * 0.015
        # 茅負（軒先の横木）と瓦の層の前の面
        p0 = P(0, 0); p1 = P(EXT, 0); p0[2] = p1[2] = zr(0) + 0.05
        eave_pl.beam(p0, p1, [0, 0, 1], 0.12, 0.13, seg=60)
        # 屋根の面（上から見えないが、影と縁のため）
        def roof(a, v, P=P):
            sv = a * EXT; q = min(sv, 6.0) * v; p = P(sv, q); p[2] = ZE + q * PITCH; return p
        eave_tl.sheet(roof, 60, 10)
        # 軒先の丸瓦の列（端は少し前へ出す）＋平瓦の端
        sv = 0.18
        while sv < EXT:
            qe = min(sv - 0.05, 1.2)
            if qe > 0.1:
                p0 = P(sv, -0.04); p1 = P(sv, qe); p0[2] = ZE + 0.06; p1[2] = ZE + 0.06 + qe * PITCH
                eave_tl.tube([p0, (p0 + p1) / 2, p1], 0.078 * (0.97 + 0.06 * rng.random()), k=12, cap=True)
                # 瓦当（丸い端の盛り上がり）
                e0 = P(sv, -0.06); e0[2] = ZE + 0.06; e1 = P(sv, -0.035); e1[2] = ZE + 0.06
                eave_tl.tube([e0, e1], 0.06, k=12, cap=True)
            # 平瓦の端（波打つ縁）
            f0 = P(sv + 0.13, -0.02); f0[2] = ZE - 0.02
            f1 = P(sv + 0.13, 0.5); f1[2] = ZE - 0.02 + 0.5 * PITCH
            eave_tl.beam(f0, f1, [0, 0, 1], 0.2, 0.045)
            sv += 0.27 + (rng.random() - 0.5) * 0.01
    # 隅木と隅棟と鬼瓦
    diag = nrm([-1, 1, 0])
    c0 = np.array([XE + 0.15, YE - 0.15, zr(0) - 0.1]); c1 = np.array([XY, YY, zr(OV) - 0.12])
    eave_pl.beam(c0, c1, [0, 0, 1], 0.12, 0.17, seg=6)
    for i in range(22):
        t0, t1 = i * 0.3, i * 0.3 + 0.28
        p0 = np.array([XE - t0, YE + t0, ZE + t0 * PITCH + 0.08]); p1 = np.array([XE - t1, YE + t1, ZE + t1 * PITCH + 0.08])
        eave_tl.beam(p0, p1, [0, 0, 1], 0.38, 0.26, seg=2)
        eave_tl.tube([p0 + [0, 0, 0.16], p1 + [0, 0, 0.16]], 0.11, k=12)
    oni = np.array([XE + 0.1, YE - 0.1, ZE + 0.25])
    eave_tl.beam(oni - diag * 0.06, oni + diag * 0.06, [0, 0, 1], 0.34, 0.34)
    eave_tl.tube([oni + [0, 0, 0.12] - diag * 0.07, oni + [0, 0, 0.12] + diag * 0.07], 0.16, k=16, cap=True)
    eave_pl.deform(lift); eave_tl.deform(lift)
    eave_pl.emit('eavePlaster', 'plaster', bevel=0.01)
    eave_tl.emit('eaveTiles', 'tile', smooth=False)
    pl.emit('plaster', 'plaster', bevel=0.012)
    bd.emit('boards', 'board', bevel=0.004)
    dk.emit('dark', 'dark')
    wd.emit('wood', 'wood', bevel=0.005)

# ---------------------------------------------------------------- 落ちてくる石（頭大1・拳大3）
FALL = []
def build_falling():
    rng = np.random.default_rng(777)
    cx = (BAY['x0'] + BAY['x1']) / 2; cy = (YY - 0.3 + BAY['yo'] + 0.1) / 2
    specs = [(0.36, 0.0, -1.25, -0.12), (0.14, -0.3, -0.6, -0.1), (0.12, 0.32, -1.85, -0.18), (0.16, 0.12, -2.5, -0.08), (0.05, -0.12, -0.95, -0.15), (0.04, 0.2, -1.5, -0.2), (0.035, 0.05, -0.4, -0.12)]
    for k, (sz, dx, dz, dy) in enumerate(specs):
        P, TF = stone_local(sz, sz * 0.85, sz * 0.9, rng, 900 + k, m=7, rough=1.4)
        # 丸めて塊に
        P *= 1.0
        pos = np.array([cx + dx, cy + dy, BAY['z0'] + dz])
        v = math.sqrt(2 * 9.8 * max(0.2, -dz))           # 落ちてきた速さ（m/s）
        rot = (rng.random() * 6, rng.random() * 6, rng.random() * 6)
        FALL.append((pos, v))
        def anim(ob, pos=pos, v=v, rot=rot):
            for fr, dt in ((0, -1 / 30), (1, 0), (2, 1 / 30)):
                ob.location = (pos[0], pos[1], pos[2] - v * dt - 4.9 * dt * dt)
                ob.rotation_euler = (rot[0] + 5 * dt, rot[1] + 3 * dt, rot[2])
                ob.keyframe_insert('location', frame=fr); ob.keyframe_insert('rotation_euler', frame=fr)
            for fc in ob.animation_data.action.fcurves:
                for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        if DRY:
            emit('fall%d' % k, P + pos, TF, 'stone')
        else:
            emit('fall%d' % k, P, TF, 'stone', attrs={'srand': np.full(len(P), 0.55 if k % 2 == 0 else 0.8)}, smooth=True, anim=anim)

# ---------------------------------------------------------------- カメラ・縄
import os
CAM = np.array([float(v) for v in os.environ.get('K32_CAM', '0.0,-3.6,1.6').split(',')])
AIM = np.array([-D_TOP - float(os.environ.get('K32_AIMU', '1.6')), D_TOP, 0.0])   # 角から面Aへ寄せた所を向く
PITCH_DEG = float(os.environ.get('K32_PITCH', '40'))
def cam_basis():
    h = nrm([AIM[0] - CAM[0], AIM[1] - CAM[1], 0]); p = math.radians(PITCH_DEG)
    f = h * math.cos(p) + np.array([0, 0, math.sin(p)])
    r = nrm(np.cross(f, [0, 0, 1])); u = np.cross(r, f)
    return f, r, u
def project(X):
    f, r, u = cam_basis(); D = np.atleast_2d(X) - CAM; z = D @ f
    return np.stack([(D @ r) / z / TAN_H, (D @ u) / z / TAN_V, z], 1)   # -1..1（右・上）
def ray_hit_faceA(sx, sy):
    f, r, u = cam_basis(); dv = nrm(f + r * sx * TAN_H + u * sy * TAN_V)
    lo, hi = 0.1, 40.0
    for _ in range(60):
        m = (lo + hi) / 2; p = CAM + dv * m
        if p[1] < d(p[2]): lo = m
        else: hi = m
    return CAM + dv * lo

def build_rope():
    rng = np.random.default_rng(55)
    hook = ray_hit_faceA(-0.5, -0.62); w1 = ray_hit_faceA(-0.72, -0.86)
    f, r, u = cam_basis()
    hand = CAM + f * 0.9 - u * 0.75 - r * 0.25            # 画面の外（左下の手元）
    Hh, T, N = frame('A', hook[2])
    # 壁に沿う所
    pts = []
    for t in np.linspace(0, 1, 120):
        p = hook + (w1 - hook) * t; z = p[2]; Hz, Tz, Nz = frame('A', z)
        q = np.array([p[0], d(z), z]) + Nz * (0.035 + 0.01 * math.sin(t * 7))
        pts.append(q)
    # 宙に張る所（少したるむ）
    a = pts[-1]
    for t in np.linspace(0, 1, 160)[1:]:
        p = a + (hand - a) * t; p[2] -= 0.35 * math.sin(math.pi * t) * 0.6
        pts.append(p)
    pts = np.array(pts)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1); sl = np.concatenate([[0], np.cumsum(seg)])
    # 等間隔に取り直す（2cm）
    ts = np.arange(0, sl[-1], 0.01); C = np.stack([np.interp(ts, sl, pts[:, i]) for i in range(3)], 1)
    Tg = np.gradient(C, axis=0); Tg /= np.linalg.norm(Tg, axis=1, keepdims=True)
    Nv = nrm(np.cross(Tg[0], [0, 0, 1])); rope = Builder()
    R = 0.03; strands = []
    frames = []
    for i in range(len(C)):
        if i > 0: Nv = nrm(Nv - Tg[i] * np.dot(Nv, Tg[i]))
        frames.append((Nv, np.cross(Tg[i], Nv)))
    for k in range(3):
        sp = []
        for i, (Nn, Bn) in enumerate(frames):
            th = 2 * math.pi * ts[i] / 0.075 + k * 2 * math.pi / 3
            sp.append(C[i] + 0.55 * R * (math.cos(th) * Nn + math.sin(th) * Bn))
        rope.tube(sp, 0.55 * R, k=7)
    rope.emit('rope', 'rope', smooth=True)
    # 鉤（鉄の爪3本＋輪）
    hk = Builder(); n = N; up = T
    top = hook + up * 0.05 + n * 0.03
    hk.tube([hook - up * 0.04 + n * 0.04, top + up * 0.18], 0.016, k=10, cap=True)
    for k, side in enumerate((-1, 0, 1)):
        base = top + up * 0.18
        pts = [base]
        for t in np.linspace(0.1, 1, 8):
            ang = t * 2.6
            pts.append(base + up * 0.1 * math.sin(ang) + Hh * side * 0.07 * t - n * (0.1 * (1 - math.cos(ang)) * (0.6 if side == 0 else 1)) + n * 0.06 * t * (side == 0))
        hk.tube(pts, np.linspace(0.013, 0.006, len(pts)), k=8)
    ring_c = hook - up * 0.06 + n * 0.04
    ring = [ring_c + 0.04 * (math.cos(t) * Hh + math.sin(t) * up) for t in np.linspace(0, 2 * math.pi, 20)]
    hk.tube(ring, 0.008, k=6)
    hk.emit('hook', 'iron', smooth=True)
    log('rope', 'hook', np.round(hook, 2), 'hand', np.round(hand, 2), 'len', round(float(sl[-1]), 2))
    return hook

# ---------------------------------------------------------------- 材質（Blender のみ）
MATS = {}
def S(node, name, kind='in', typ=None):
    socks = node.inputs if kind == 'in' else node.outputs
    for s in socks:
        if s.name == name and (typ is None or s.type == typ) and getattr(s, 'enabled', True):
            return s
    raise KeyError(f'{node.bl_idname}.{name}')

class NT:
    def __init__(self, mat):
        mat.use_nodes = True; self.nt = mat.node_tree; self.nt.nodes.clear(); self.N = self.nt.nodes; self.L = self.nt.links
    def node(self, t, **kw):
        n = self.N.new(t)
        for k, v in kw.items(): setattr(n, k, v)
        return n
    def feed(self, sock, val):
        if hasattr(val, 'is_output'): self.L.new(val, sock)
        else: sock.default_value = val
    def pos(self): return S(self.node('ShaderNodeNewGeometry'), 'Position', 'out')
    def geo(self, name): return S(self.node('ShaderNodeNewGeometry'), name, 'out')
    def vmul(self, v, sc):
        n = self.node('ShaderNodeVectorMath', operation='MULTIPLY'); self.feed(n.inputs[0], v); n.inputs[1].default_value = sc; return S(n, 'Vector', 'out')
    def noise(self, v, scale, detail=4, rough=0.55, dist=0.0):
        n = self.node('ShaderNodeTexNoise'); self.feed(S(n, 'Vector'), v)
        S(n, 'Scale').default_value = scale; S(n, 'Detail').default_value = detail; S(n, 'Roughness').default_value = rough; S(n, 'Distortion').default_value = dist
        return S(n, 'Fac', 'out')
    def ramp(self, fac, stops, interp='LINEAR'):
        n = self.node('ShaderNodeValToRGB'); cr = n.color_ramp; cr.interpolation = interp
        while len(cr.elements) < len(stops): cr.elements.new(0.995)
        cr.elements[-1].position = 1.0
        # 小さい順に置く（後ろの点はまだ 0.995〜1.0 にあるので並びが崩れない）
        for i, (p, c) in enumerate(stops):
            e = cr.elements[i]; e.position = min(p, 0.99) if i < len(stops) - 1 else p
            e.color = c if len(c) == 4 else (c[0], c[1], c[2], 1.0)
        self.feed(S(n, 'Fac'), fac); return S(n, 'Color', 'out')
    def framp(self, fac, a, b, lo=0.0, hi=1.0):   # 数を a..b → lo..hi（はみ出しは切る）
        n = self.node('ShaderNodeMapRange'); n.clamp = True
        self.feed(S(n, 'Value', typ='VALUE'), fac)
        S(n, 'From Min', typ='VALUE').default_value = a; S(n, 'From Max', typ='VALUE').default_value = b
        S(n, 'To Min', typ='VALUE').default_value = lo; S(n, 'To Max', typ='VALUE').default_value = hi
        return S(n, 'Result', 'out', typ='VALUE')
    def math(self, op, a, b=0.0, clamp=False):
        n = self.node('ShaderNodeMath', operation=op); n.use_clamp = clamp
        self.feed(n.inputs[0], a); self.feed(n.inputs[1], b); return S(n, 'Value', 'out')
    def mix(self, fac, a, b, blend='MIX'):
        n = self.node('ShaderNodeMix'); n.data_type = 'RGBA'; n.blend_type = blend
        self.feed(S(n, 'Factor', typ='VALUE'), fac)
        self.feed(S(n, 'A', typ='RGBA'), a if hasattr(a, 'is_output') else (*a[:3], 1.0))
        self.feed(S(n, 'B', typ='RGBA'), b if hasattr(b, 'is_output') else (*b[:3], 1.0))
        return S(n, 'Result', 'out', typ='RGBA')
    def sepz(self, v):
        n = self.node('ShaderNodeSeparateXYZ'); self.feed(n.inputs[0], v); return S(n, 'Z', 'out')
    def ao(self, dist):
        n = self.node('ShaderNodeAmbientOcclusion'); n.samples = 4; S(n, 'Distance').default_value = dist; return S(n, 'AO', 'out')
    def bump(self, h, strength, dist=0.02, normal=None):
        n = self.node('ShaderNodeBump'); S(n, 'Strength').default_value = strength; S(n, 'Distance').default_value = dist
        self.feed(S(n, 'Height'), h)
        if normal is not None: self.feed(S(n, 'Normal'), normal)
        return S(n, 'Normal', 'out')
    def principled(self, color, rough, normal=None, metal=0.0, spec=0.5):
        b = self.node('ShaderNodeBsdfPrincipled'); self.feed(S(b, 'Base Color'), color); self.feed(S(b, 'Roughness'), rough)
        S(b, 'Metallic').default_value = metal
        try: S(b, 'Specular IOR Level').default_value = spec
        except KeyError: pass
        if normal is not None: self.feed(S(b, 'Normal'), normal)
        return S(b, 'BSDF', 'out')
    def out(self, shader):
        o = self.node('ShaderNodeOutputMaterial'); self.L.new(shader, S(o, 'Surface'))

def make_materials():
    def new(name):
        m = bpy.data.materials.new(name); MATS[name] = m; return NT(m)
    # 石：花崗岩の色を石ごとに変え、まだら・黒い粒・雨だれ・目地の土・苔・地衣
    t = new('stone'); P = t.pos()
    at = t.node('ShaderNodeAttribute', attribute_name='srand'); sr = S(at, 'Fac', 'out')
    base = t.ramp(sr, [(0.0, (0.30, 0.29, 0.27)), (0.18, (0.24, 0.24, 0.23)), (0.33, (0.33, 0.29, 0.23)), (0.5, (0.15, 0.15, 0.145)),
                       (0.62, (0.31, 0.31, 0.30)), (0.75, (0.27, 0.23, 0.18)), (0.88, (0.20, 0.20, 0.19))], 'CONSTANT')
    mott = t.ramp(t.noise(P, 1.6, 8, 0.6), [(0.3, (0.6, 0.6, 0.6)), (0.7, (1.15, 1.13, 1.1))])
    stain = t.ramp(t.noise(P, 0.45, 5, 0.6), [(0.45, (1, 1, 1)), (0.7, (0.55, 0.53, 0.5))])
    mott = t.mix(1.0, mott, stain, 'MULTIPLY')
    c = t.mix(1.0, base, mott, 'MULTIPLY')
    spk = t.ramp(t.noise(P, 160, 2, 0.5), [(0.66, (1, 1, 1)), (0.72, (0.55, 0.55, 0.55))])
    c = t.mix(1.0, c, spk, 'MULTIPLY')
    stk = t.ramp(t.noise(t.vmul(P, (7, 7, 0.45)), 1.0, 5, 0.6), [(0.5, (1, 1, 1)), (0.72, (0.62, 0.6, 0.58))])
    c = t.mix(1.0, c, stk, 'MULTIPLY')
    crev = t.framp(t.ao(0.3), 0.35, 0.85, 1.0, 0.0)
    c = t.mix(t.math('MULTIPLY', crev, 0.85), c, (0.05, 0.038, 0.026))
    nz = t.sepz(t.geo('Normal'))
    up = t.framp(nz, 0.15, 0.65)
    mn = t.framp(t.noise(P, 4.5, 6, 0.6), 0.45, 0.6)
    moss = t.math('MULTIPLY', t.math('ADD', up, t.math('MULTIPLY', crev, 0.9), clamp=True), mn, clamp=True)
    mcol = t.ramp(t.noise(P, 12, 3), [(0.3, (0.04, 0.06, 0.015)), (0.7, (0.10, 0.12, 0.03))])
    c = t.mix(moss, c, mcol)
    lich = t.math('MULTIPLY', t.framp(t.noise(P, 8, 4, 0.6), 0.63, 0.68), t.math('SUBTRACT', 1.0, crev, clamp=True))
    c = t.mix(t.math('MULTIPLY', lich, 0.65), c, (0.52, 0.53, 0.47))
    hgt = t.math('ADD', t.math('MULTIPLY', t.noise(P, 28, 8, 0.6), 0.6), t.math('MULTIPLY', t.noise(P, 5, 4), 0.4))
    hgt = t.math('ADD', hgt, t.math('MULTIPLY', t.noise(P, 90, 4, 0.7), 0.25))
    t.out(t.principled(c, t.math('ADD', 0.8, t.math('MULTIPLY', moss, 0.17)), t.bump(hgt, 0.6, 0.035)))
    # 漆喰：汚れ・雨だれ・はがれ
    t = new('plaster'); P = t.pos()
    c = t.ramp(t.noise(P, 0.9, 5, 0.6), [(0.35, (0.80, 0.79, 0.75)), (0.8, (0.55, 0.54, 0.5))])
    stk = t.ramp(t.noise(t.vmul(P, (16, 16, 0.6)), 1.0, 4, 0.6), [(0.5, (1, 1, 1)), (0.68, (0.58, 0.57, 0.54))])
    c = t.mix(1.0, c, stk, 'MULTIPLY')
    peel = t.framp(t.noise(P, 2.2, 6, 0.65), 0.66, 0.675)
    c = t.mix(peel, c, (0.47, 0.44, 0.39))
    crev = t.framp(t.ao(0.25), 0.4, 0.9, 1.0, 0.0)
    c = t.mix(t.math('MULTIPLY', crev, 0.5), c, (0.25, 0.24, 0.22))
    hgt = t.math('ADD', t.math('MULTIPLY', t.noise(P, 40, 6), 0.25), t.math('MULTIPLY', peel, -0.6))
    t.out(t.principled(c, 0.9, t.bump(hgt, 0.25, 0.01)))
    # 下見板：墨の黒、日焼けの灰、木目
    t = new('board'); P = t.pos()
    w = t.node('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X'); t.feed(S(w, 'Vector'), t.vmul(P, (0.6, 9, 9)))
    S(w, 'Scale').default_value = 3.0; S(w, 'Distortion').default_value = 7.0; S(w, 'Detail').default_value = 4.0
    grain = S(w, 'Fac', 'out')
    c = t.ramp(t.noise(P, 1.3, 5), [(0.35, (0.028, 0.026, 0.024)), (0.75, (0.085, 0.082, 0.076))])
    c = t.mix(t.math('MULTIPLY', grain, 0.35), c, (0.12, 0.115, 0.105))
    crev = t.framp(t.ao(0.15), 0.4, 0.9, 1.0, 0.0)
    c = t.mix(crev, c, (0.01, 0.01, 0.01))
    t.out(t.principled(c, t.framp(grain, 0, 1, 0.55, 0.8), t.bump(grain, 0.2, 0.005)))
    # 古い木（底板・蓋）
    t = new('wood'); P = t.pos()
    w = t.node('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X'); t.feed(S(w, 'Vector'), t.vmul(P, (0.5, 12, 12)))
    S(w, 'Scale').default_value = 2.0; S(w, 'Distortion').default_value = 6.0
    c = t.mix(t.math('MULTIPLY', S(w, 'Fac', 'out'), 0.5), (0.11, 0.095, 0.08), (0.06, 0.05, 0.042))
    t.out(t.principled(c, 0.82, t.bump(S(w, 'Fac', 'out'), 0.25, 0.005)))
    # 瓦：いぶし銀の灰
    t = new('tile'); P = t.pos()
    c = t.ramp(t.noise(P, 3, 5), [(0.3, (0.055, 0.058, 0.063)), (0.75, (0.10, 0.10, 0.105))])
    crev = t.framp(t.ao(0.2), 0.4, 0.9, 1.0, 0.0)
    c = t.mix(t.math('MULTIPLY', crev, 0.7), c, (0.02, 0.02, 0.02))
    lich = t.framp(t.noise(P, 6, 4), 0.66, 0.7)
    c = t.mix(t.math('MULTIPLY', lich, 0.5), c, (0.3, 0.31, 0.27))
    t.out(t.principled(c, t.framp(t.noise(P, 9, 3), 0.3, 0.7, 0.32, 0.55), t.bump(t.noise(P, 60, 4), 0.1, 0.005)))
    # 鉄（鉤）
    t = new('iron'); P = t.pos()
    rust = t.framp(t.noise(P, 30, 5), 0.48, 0.62)
    c = t.mix(rust, (0.035, 0.033, 0.03), (0.13, 0.06, 0.025))
    t.out(t.principled(c, t.framp(rust, 0, 1, 0.45, 0.9), t.bump(t.noise(P, 80, 4), 0.3, 0.003), metal=0.75))
    # 縄（麻）
    t = new('rope'); P = t.pos()
    c = t.ramp(t.noise(P, 40, 4), [(0.3, (0.24, 0.19, 0.11)), (0.7, (0.36, 0.29, 0.17))])
    crev = t.framp(t.ao(0.02), 0.4, 0.9, 1.0, 0.0)
    c = t.mix(t.math('MULTIPLY', crev, 0.7), c, (0.05, 0.04, 0.025))
    t.out(t.principled(c, 0.95, t.bump(t.noise(t.vmul(P, (1, 1, 1)), 300, 3), 0.5, 0.002)))
    # 草（少し透ける）
    t = new('grass'); P = t.pos()
    c = t.ramp(t.noise(P, 6, 3), [(0.3, (0.05, 0.09, 0.02)), (0.7, (0.16, 0.15, 0.05))])
    b1 = t.principled(c, 0.6)
    tr = t.node('ShaderNodeBsdfTranslucent'); t.feed(S(tr, 'Color'), c)
    mx = t.node('ShaderNodeMixShader'); mx.inputs[0].default_value = 0.3
    t.L.new(b1, mx.inputs[1]); t.L.new(S(tr, 'BSDF', 'out'), mx.inputs[2]); t.out(S(mx, 'Shader', 'out'))
    # 目地の土・地面・暗がり
    t = new('soil'); P = t.pos()
    t.out(t.principled(t.ramp(t.noise(P, 8, 4), [(0.3, (0.05, 0.04, 0.03)), (0.7, (0.09, 0.075, 0.05))]), 1.0))
    t = new('ground'); t.out(t.principled((0.12, 0.12, 0.08, 1), 1.0))
    t = new('dark'); t.out(t.principled((0.015, 0.013, 0.012, 1), 1.0))

def make_world():
    wd = bpy.data.worlds.new('sky'); bpy.context.scene.world = wd; wd.use_nodes = True
    nt = wd.node_tree; nt.nodes.clear(); N = nt.nodes; L = nt.links
    tc = N.new('ShaderNodeTexCoord'); dirv = tc.outputs['Generated']
    sep = N.new('ShaderNodeSeparateXYZ'); L.new(dirv, sep.inputs[0])
    gr = N.new('ShaderNodeValToRGB'); cr = gr.color_ramp
    cr.elements[0].position = 0.0; cr.elements[0].color = (0.66, 0.69, 0.72, 1)
    cr.elements[1].position = 1.0; cr.elements[1].color = (0.45, 0.52, 0.62, 1)
    L.new(sep.outputs['Z'], gr.inputs['Fac'])
    # 雲：方向を高さで割って平面に投げる
    mz = N.new('ShaderNodeMath'); mz.operation = 'MAXIMUM'; L.new(sep.outputs['Z'], mz.inputs[0]); mz.inputs[1].default_value = 0.12
    dv = N.new('ShaderNodeVectorMath'); dv.operation = 'DIVIDE'; L.new(dirv, dv.inputs[0])
    cm = N.new('ShaderNodeCombineXYZ'); L.new(mz.outputs['Value'], cm.inputs[0]); L.new(mz.outputs['Value'], cm.inputs[1]); L.new(mz.outputs['Value'], cm.inputs[2])
    L.new(cm.outputs['Vector'], dv.inputs[1])
    nz = N.new('ShaderNodeTexNoise'); L.new(dv.outputs['Vector'], nz.inputs['Vector'])
    nz.inputs['Scale'].default_value = 0.9; nz.inputs['Detail'].default_value = 10; nz.inputs['Roughness'].default_value = 0.58
    cov = N.new('ShaderNodeValToRGB'); c2 = cov.color_ramp
    c2.elements[0].position = 0.36; c2.elements[0].color = (0, 0, 0, 1); c2.elements[1].position = 0.66; c2.elements[1].color = (1, 1, 1, 1)
    L.new(nz.outputs['Fac'], cov.inputs['Fac'])
    shade = N.new('ShaderNodeValToRGB'); c3 = shade.color_ramp
    c3.elements[0].position = 0.45; c3.elements[0].color = (0.9, 0.9, 0.9, 1); c3.elements[1].position = 0.75; c3.elements[1].color = (0.48, 0.5, 0.54, 1)
    L.new(nz.outputs['Fac'], shade.inputs['Fac'])
    mx = N.new('ShaderNodeMix'); mx.data_type = 'RGBA'
    L.new(S(cov, 'Color', 'out'), S(mx, 'Factor', typ='VALUE'))
    L.new(S(gr, 'Color', 'out'), S(mx, 'A', typ='RGBA')); L.new(S(shade, 'Color', 'out'), S(mx, 'B', typ='RGBA'))
    bg = N.new('ShaderNodeBackground'); L.new(S(mx, 'Result', 'out', typ='RGBA'), bg.inputs['Color']); bg.inputs['Strength'].default_value = 1.0
    o = N.new('ShaderNodeOutputWorld'); L.new(bg.outputs['Background'], o.inputs['Surface'])

def setup_render():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    sc.cycles.samples = 64; sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    try: sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception: pass
    sc.cycles.max_bounces = 5; sc.cycles.diffuse_bounces = 3; sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2; sc.cycles.transparent_max_bounces = 4; sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
    sc.render.resolution_x = W; sc.render.resolution_y = H; sc.render.resolution_percentage = 100
    sc.render.fps = 30; sc.frame_start = 1; sc.frame_end = 1
    sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = 'AgX'; sc.view_settings.exposure = 0.1
    try: sc.view_settings.look = 'AgX - Base Contrast'
    except Exception: pass
    sc.render.image_settings.file_format = 'PNG'
    # 曇りの柔らかい日差し（右手前の上から）
    sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 1.3; sun.angle = math.radians(28); sun.color = (1.0, 0.97, 0.93)
    so = bpy.data.objects.new('sun', sun); sc.collection.objects.link(so)
    to_sun = Vector(nrm([0.85, -0.3, 0.55]).tolist())
    so.rotation_euler = (-to_sun).to_track_quat('-Z', 'Y').to_euler()
    # カメラ
    cam = bpy.data.cameras.new('cam'); cam.lens = LENS; cam.sensor_fit = 'VERTICAL'; cam.sensor_height = SENSOR_H
    cam.clip_start = 0.05; cam.clip_end = 300
    cam.dof.use_dof = True; cam.dof.focus_distance = 14.0; cam.dof.aperture_fstop = 5.6
    co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co)
    f, r, u = cam_basis()
    co.location = Vector(CAM.tolist())
    co.rotation_euler = Vector(f.tolist()).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = co
    sc.frame_set(1)

def main():
    if not DRY:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        make_materials(); make_world()
    build_wall(); log('wall')
    build_yagura(); log('yagura')
    build_falling(); log('falling')
    build_rope(); log('rope')
    GRASS.emit('grass', 'grass', smooth=False); log('grass')
    for nm, X in (('wall top corner', [-D_TOP, D_TOP, HT]), ('eave corner', [XE, YE, ZE]), ('bay bottom', [(BAY['x0'] + BAY['x1']) / 2, YY - 0.3, BAY['z0']]),
                  ('head stone', FALL[0][0] if FALL else [0, 0, 0])):
        p = project(np.array(X, float))[0]
        log(f'{nm:16s} screen x {0.5 + p[0] / 2:5.2f} y(from top) {0.5 - p[1] / 2:5.2f} dist {p[2]:5.1f}')
    if not DRY:
        setup_render(); log('ready', len(bpy.data.objects), 'objects')

main()

# ---------------------------------------------------------------- 手元の確かめ（bpy なし）：点を投影して構図だけ見る
if DRY and '--dry' in sys.argv:
    from PIL import Image, ImageDraw
    out = sys.argv[sys.argv.index('--dry') + 1]
    col = {'stone': (120, 118, 110), 'soil': (60, 50, 40), 'plaster': (230, 228, 220), 'board': (25, 25, 25), 'dark': (0, 0, 0), 'wood': (90, 70, 50),
           'tile': (70, 72, 80), 'iron': (150, 60, 30), 'rope': (200, 160, 90), 'grass': (60, 140, 40), 'ground': (80, 90, 60)}
    im = Image.new('RGB', (W // 2, H // 2), (170, 190, 215)); dr = ImageDraw.Draw(im)
    allp = []
    rs = np.random.default_rng(0)
    for nm, mat, V, F in OBJS:
        if len(V) > 60000:
            pts = V[:: len(V) // 60000]
        else:
            pts = [V]
            for f in F:
                q = V[list(f)]; a = np.linalg.norm(np.cross(q[1] - q[0], q[2] - q[0]))
                k = int(min(400, max(1, a * 60)))
                w = rs.dirichlet(np.ones(len(q)), k); pts.append(w @ q)
            pts = np.concatenate(pts)
        p = project(pts); m = (p[:, 2] > 0.1)
        for (x, y, z) in p[m]:
            allp.append((z, x, y, col.get(mat, (255, 0, 255)), mat))
    allp.sort(key=lambda a: -a[0])
    for z, x, y, c, mat in allp:
        px = (0.5 + x / 2) * W / 2; py = (0.5 - y / 2) * H / 2
        if -5 < px < W / 2 + 5 and -5 < py < H / 2 + 5:
            r = 2 if mat in ('rope', 'iron') else 1
            dr.rectangle([px - r, py - r, px + r, py + r], fill=c)
    im.save(out); print('dry preview', out)
