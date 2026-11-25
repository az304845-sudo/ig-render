# k32「城」：castle.blend を時刻（コマ番号）だけで動かす。描き出しの時に -P で読む。
#   blender -b castle.blend -P castle_anim.py -t 4 -o <出力> -F PNG -x 1 -f N   （または -s S -e E -a）
# 時計と乱数は使わない（乱数は固定の種で最初に1回だけ作る）。t = (コマ − 1) / 30
import bpy, math
import numpy as np
from mathutils import Vector, Euler, Matrix

sc = bpy.context.scene
FPS = 30
def ss(a, b, t):
    x = min(1.0, max(0.0, (t - a) / (b - a))); return x * x * (3 - 2 * x)
def lerp(a, b, u): return a + (b - a) * u

A_SLOPE, HT = 0.72, 12.0
def d(z): return A_SLOPE * z - A_SLOPE / (2 * HT) * z * z
def dp(z): return A_SLOPE - A_SLOPE * z / HT
D_TOP = d(HT); XY, YY = -D_TOP - 0.25, D_TOP + 0.25
BAY = dict(x0=XY - 2.35, x1=XY - 0.55, yo=YY - 0.78, z0=12.4)
L = 44.0; GATE = (-27.5, -22.5); GY = 4.6; WATER, MOATD = -0.7, 3.5

OBJ = {}
for ob in bpy.data.objects:
    OBJ.setdefault(ob.get('grp', 'none'), []).append(ob)
POSE = {m.name: m for m in bpy.data.meshes if m.name[:3] in ('run', 'cli', 'sta', 'fal', 'swi', 'pus', 'sru', 'sst', 'wcl')}

# ---------------------------------------------------------------- 段の進み具合（0＝無い・1＝ある）
def f_hi(t): return 1.0 if t < 4.0 else (1 - ss(4.0, 4.9, t) if t < 6.95 else ss(7.0, 8.0, t))
def f_low(t): return 0.0 if t < 4.3 or t > 7.6 else ss(4.3, 4.9, t)
def f_masu(t): return 1.0 if t < 4.0 else (1 - ss(4.0, 4.5, t) if t < 11.0 else ss(11.4, 12.4, t))
def f_ten(t): return 1.0 if t < 4.0 else (1 - ss(4.0, 4.6, t) if t < 19.0 else ss(19.8, 20.9, t))
def f_floor(t): return 1.0 if t < 4.0 else (1 - ss(4.1, 4.7, t) if t < 6.5 else ss(6.6, 7.3, t))
def f_water(t): return 1.0 if t < 4.0 else (1 - ss(4.0, 4.4, t) if t < 6.9 else ss(7.0, 7.8, t))
def f_bay(t): return 1.0 if t < 4.0 else (1 - ss(4.0, 4.3, t) if t < 16.0 else ss(16.1, 16.9, t))
def lid_deg(t):
    if t < 4.0: return 72 * ss(0.08, 0.36, t)
    if t < 16.0: return 72 * (1 - ss(4.0, 4.25, t))
    if t < 22.0: return 72 * ss(16.9, 17.3, t)
    return 72 * (1 - ss(22.6, 23.4, t))
def door_deg(t):
    if t < 11.0: return 85 * ss(10.48, 10.72, t)
    if t < 12.0: return 85 * (1 - ss(11.2, 11.5, t))
    if t < 20.0: return 85 * ss(12.73, 12.97, t)
    return 85 * (1 - ss(20.4, 21.0, t))

# ---------------------------------------------------------------- 落ちる石
DROPS = sorted(OBJ.get('drop', []), key=lambda o: o.name)
CX = (BAY['x0'] + BAY['x1']) / 2; CY = (YY - 0.3 + BAY['yo'] + 0.1) / 2
def drop_pos(k, t):
    sz, dx, dz, dy = DROPS[k]['spec']; r = sz * 0.5
    x0, y0, zh = CX + dx, CY + dy, BAY['z0'] - 0.1
    if t < 4.0:                                   # 冒頭：ゆっくり落ちる（1.0 秒で v2 の位置）→ 1.35 秒で止まる
        t0 = 0.22 + 0.05 * k; g = 2 * abs(dz) / (1.0 - t0) ** 2; tt = min(t, 1.35)
        if tt < t0: return None
        z = zh - 0.5 * g * (tt - t0) ** 2; rot = (tt - t0) * 5
    elif 17.6 < t < 22.5:                         # 03/03：本当の重さで落ち、反りに当たって滑り落ちる
        t0 = 17.7 + 0.12 * k
        if t < t0: return None
        tau = t - t0; z = max(r, zh - 4.9 * tau * tau); rot = tau * 7
    else:
        return None
    y = min(y0, d(z) - r - 0.02) if z > r else d(r) - r - 0.4
    return (x0, y, z), rot

# ---------------------------------------------------------------- 攻め手
rng = np.random.default_rng(4242)
ENEMIES = sorted(OBJ.get('enemy', []), key=lambda o: o.name)
FIG = [o for o in ENEMIES if o.name.startswith('enemy')]; RAM = bpy.data.objects.get('ram')
SPEAR = {}; SCALE = {}
for o in FIG: SPEAR[o.name] = rng.random() < 0.4; SCALE[o.name] = 0.92 + 0.16 * rng.random()
N1, N2, N3, N4 = 46, 40, 46, 7
W1 = [dict(x=(lambda x: x if not (-28.5 < x < -21.5) else x - 7.5)(-40 + 34 * rng.random()), ta=5.5 + 0.8 * rng.random(), v=5.2 + 1.3 * rng.random(), ph=rng.random()) for _ in range(N1)]
W2 = [dict(x=-16 + 26 * rng.random(), yt=-19.7 - 5.5 * rng.random() ** 1.5, ta=7.95 + 0.6 * rng.random(), v=4.5 + 1.5 * rng.random(), hd=(rng.random() - 0.5) * 0.6, ps=rng.integers(0, 2), sw=rng.random() * 6) for _ in range(N2)]
SWIM = [dict(x=-9 + 6 * rng.random(), zmax=2.6 + 1.4 * rng.random(), dl=0.15 * rng.random()) for _ in range(5)]
W3 = [dict(ox=(rng.random() - 0.5) * 3.4, q=(0 if i < 6 else 2.5 + 0.9 * (i - 6) + rng.random() * 0.6), ph=rng.random(),
           tA=(-34 + 20 * rng.random(), 12 + 16 * rng.random()), tB=(-30.3 + 12.6 * rng.random(), 9.2 + 10.4 * rng.random()), hd=(rng.random() - 0.5) * 1.2, sw=rng.random() * 6) for i in range(N3)]
W4 = [dict(x=-10 + 8 * (i + 0.5 * rng.random()) / 7, zmax=1.5 + 3.5 * rng.random(), ta=15.0 + 0.8 * rng.random(), go=18.0 + 0.5 * rng.random(), ph=rng.random()) for i in range(N4)]

def run_pose(dist, ph): return 'run%d' % (int(((dist / 1.7) + ph) * 8) % 8)
def climb_pose(z, ph): return 'wclimb%d' % (int((z / 0.45 + ph) * 4) % 4)

def place(ob, pos, heading=0.0, pose='stand0', tilt=0.0):
    if SPEAR.get(ob.name) and pose[:3] in ('run', 'sta'): pose = 's' + pose
    ob.data = POSE[pose]; s = SCALE.get(ob.name, 1.0); ob.scale = (s, s, s); ob.location = pos; ob.rotation_euler = (tilt, 0.0, heading); ob.hide_render = False

def on_wall(x, z):   # 面A に張りつく位置と傾き
    return (x, d(z) - 0.38, z), -math.atan(dp(z))

def wave_positions(t):
    out = []   # (pos, heading, pose, tilt)
    if 5.0 <= t <= 6.95:
        te = t if t <= 6.45 else 6.45 - (t - 6.45) * 3.2
        for e in W1:
            ta, v = e['ta'], e['v']
            if te < ta:
                y = v * (te - ta) - 0.4; z = 0.0; pose = run_pose(y, e['ph'])
            elif te < ta + 0.45:
                p = (te - ta) / 0.45; y = -0.4 + 2.1 * p; z = 1.75 * math.sin(math.pi * p); pose = climb_pose(p * 2, e['ph'])
            else:
                y = 1.7 + v * (te - ta - 0.45); z = 0.0; pose = run_pose(y, e['ph'])
            if y > -45: out.append(((e['x'], y, z), 0.0, pose, 0.0))
    if 7.9 <= t <= 9.95:
        for e in W2:
            y = e['yt'] - e['v'] * max(0.0, e['ta'] - t) - 0.4 * (1 - ss(e['ta'] - 0.25, e['ta'] + 0.1, t))
            moving = t < e['ta']
            sway = 0.12 * math.sin(t * 2.3 + e['sw'])
            out.append(((e['x'] + (0 if moving else sway), y, 0.0), e['hd'] * (0 if moving else 1), run_pose(y, 0) if moving else 'stand%d' % e['ps'], 0.0))
        for e in SWIM:
            tt = t - e['dl']
            if tt < 8.35:
                y = -8.5 + 3.3 * ss(7.9, 8.35, tt); out.append(((e['x'], y, WATER - 1.05), 0.0, 'swim0', -1.2))
            elif tt < 8.75:
                y = -5.2 + 4.9 * ss(8.35, 8.75, tt); out.append(((e['x'], y, 0.0), 0.0, run_pose(y, 0.3), 0.0))
            elif tt < 9.3:
                z = e['zmax'] * ss(8.75, 9.3, tt); p, tl = on_wall(e['x'], max(z, 0.05)); out.append((p, 0.0, climb_pose(z, 0.2), tl))
            elif tt < 9.7:
                z = e['zmax'] * (1 - ss(9.3, 9.7, tt)) ** 1.6; p, tl = on_wall(e['x'], max(z, 0.05)); out.append((p, 0.0, 'fall0', tl * 0.6))
            else:
                y = -0.5 - 3.0 * (tt - 9.7); out.append(((e['x'], y, 0.0), math.pi, run_pose(y, 0.6), 0.0))
    # 02/03：門（A＝枡形なしで流れ込む・B＝枡形の中で詰まる）
    for phase, t0, t1 in (('A', 10.0, 11.58), ('B', 12.4, 15.0)):
        if not (t0 <= t <= t1): continue
        if phase == 'A': te = t if t <= 11.2 else 11.2 - (t - 11.2) * 4.0
        else: te = t - 2.25
        sL = 44.6 + (7.0 if phase == 'A' else 8.0) * (te - 10.5)
        for i, e in enumerate(W3):
            s = sL - e['q'] * (1.0 if phase == 'A' else 0.5)
            if te < 10.5: s = min(s, 44.3 - e['q'] * 0.15)
            x = -25 + e['ox']; tgt = e['tA'] if phase == 'A' else e['tB']
            if s <= 48.3:
                y = -40 + s; pos = (x, y, 0.0); hd = 0.0; moving = True
            else:
                rem = s - 48.3; vx, vy = tgt[0] - x, tgt[1] - 8.3; dist = math.hypot(vx, vy)
                if rem < dist:
                    pos = (x + vx * rem / dist, 8.3 + vy * rem / dist, 0.0); hd = math.atan2(-vx, vy); moving = True
                else:
                    sw = 0.15 * math.sin(t * 2.0 + e['sw'])
                    pos = (tgt[0] + sw, tgt[1], 0.0); hd = e['hd'] + (0.0 if phase == 'A' else 0.5 * math.sin(t * 1.3 + e['sw'])); moving = False
            if pos[1] < -44: continue
            pose = ('push0' if (i < 6 and te < 10.55) else run_pose(s, e['ph'])) if moving else ('stand0' if phase == 'A' else ('stand1' if i % 2 else 'stand0'))
            out.append((pos, hd, pose, 0.0))
    if False:   # 03/03 は兵を出さない（梯子と鉤縄で見せる）
        for e in W4:
            if t < e['ta']:
                y = -4.0 + 3.6 * ss(14.8, e['ta'], t); out.append(((e['x'], y, 0.0), 0.0, run_pose(y * 3, e['ph']), 0.0))
            elif t < e['go']:
                z = e['zmax'] * ss(e['ta'], e['ta'] + 1.4, t) + 0.25 * max(0, t - e['ta'] - 1.4); p, tl = on_wall(e['x'], max(min(z, e['zmax'] + 0.8), 0.05))
                out.append((p, 0.0, climb_pose(z, e['ph']), tl))
            elif t < e['go'] + 0.45:
                z0 = e['zmax'] + 0.25 * max(0, e['go'] - e['ta'] - 1.4); z = z0 * (1 - ss(e['go'], e['go'] + 0.45, t)) ** 1.5
                p, tl = on_wall(e['x'], max(z, 0.05)); out.append((p, 0.0, 'fall0', tl * 0.6))
            else:
                y = -0.4 - 5.5 * (t - e['go'] - 0.45); x = e['x'] - 3.0 * (t - e['go'] - 0.45)
                if y > -5.2: out.append(((x, y, 0.0), math.pi * 1.2, run_pose(y * 2, e['ph']), 0.0))
    return out

def ram_pos(t):
    for phase, t0, t1 in (('A', 10.0, 11.58), ('B', 12.4, 15.0)):
        if t0 <= t <= t1:
            te = (t if t <= 11.2 else 11.2 - (t - 11.2) * 4.0) if phase == 'A' else t - 2.25
            sL = min(44.6 + 7.0 * (te - 10.5), 44.6 + 1.2 * max(0, te - 10.5))
            if te > 10.9: return None
            return (-25.0, -40 + sL - 1.0, 1.0)
    return None

# ---------------------------------------------------------------- カメラ
def look(pos, aim):
    v = Vector(aim) - Vector(pos); return v.to_track_quat('-Z', 'Y').to_euler()
CAM0 = np.array([0.0, -3.6, 1.6]); aimv2 = np.array([-D_TOP - 1.6, D_TOP, 0.0])
hh = aimv2 - CAM0; hh[2] = 0; hh /= np.linalg.norm(hh); pr = math.radians(40)
AIM0 = CAM0 + (hh * math.cos(pr) + np.array([0, 0, math.sin(pr)])) * 15
p135, _ = drop_pos(0, 1.35) if DROPS else ((0, 0, 0), 0)
STONE = np.array(p135); dv = STONE - CAM0; dv /= np.linalg.norm(dv)
NEAR = STONE - dv * 1.25; NEAR2 = STONE - dv * 1.4
C = np.array([-22.0, 22.0, 3.0])
KEYS = [  # (秒, カメラの位置, 見る先, 絞り)
    (0.00, CAM0, AIM0, 5.6), (1.30, CAM0, AIM0, 5.6), (1.35, NEAR, STONE, 5.6), (2.30, NEAR2, STONE, 5.6),
    (3.00, (26, -54, 40), (-21, 20, 3), 8), (4.00, (24, -52, 38), (-21, 20, 3), 8), (5.05, (23, -51, 37), (-21, 20, 3), 8),
    (5.35, (-7, -38, 9), (-24, 0, 1.2), 2.8), (6.45, (-9, -36, 9), (-24, 0, 1.2), 2.8),
    (6.95, (-12.6, -16.4, 0.35), (-3.0, 2.1, 5.6), 5.6), (8.05, (-12.2, -16.0, 0.3), (-3.0, 2.1, 5.8), 5.6),
    (8.25, (14, -44, 6), (-6, 0, 5), 2.0), (9.85, (13, -42, 5.6), (-6, 0, 5), 2.0),
    (10.20, (-5, -33, 30), (-24, 9, 1), 8), (11.15, (-6, -31, 29), (-24, 9, 1), 8), (11.60, (-12, 27, 38), (-24, 13, 0), 8), (14.70, (-13, 26, 36), (-24, 13, 0), 8),
    (15.05, (-6.7, -10.4, 1.9), (-6.0, 3.4, 11.6), 1.8), (19.60, (-6.5, -10.0, 1.8), (-6.0, 3.4, 11.6), 1.8),
    (21.40, (24, -56, 44), (-22, 21, 3), 8)]
ORB0, ORB1, END = 21.40, 23.0, 24.47
def orbit(t):
    p = np.array(KEYS[-1][1], float); th = 0.2 * ss(ORB0, ORB1, t) if t < ORB1 else 0.2
    v = p - C; c, s = math.cos(th), math.sin(th)
    return C + np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2]])
def cam_at(t):
    if t >= ORB0:
        if t <= ORB1: return orbit(t), np.array(KEYS[-1][2], float), 8
        u = ss(ORB1, END, t); p0 = orbit(ORB1); a0 = np.array(KEYS[-1][2], float)
        # 下りながら冒頭の見上げに戻る（位置は高さを先に落とす）
        p = np.array([lerp(p0[0], CAM0[0], ss(ORB1, END, t)), lerp(p0[1], CAM0[1], ss(ORB1, END, t)), lerp(p0[2], CAM0[2], ss(ORB1, END - 0.25, t))])
        return p, a0 + (AIM0 - a0) * ss(ORB1 + 0.3, END, t), lerp(8, 5.6, u)
    for (ta, pa, aa, fa), (tb, pb, ab, fb) in zip(KEYS[:-1], KEYS[1:]):
        if ta <= t <= tb:
            u = ss(ta, tb, t); return np.array(pa, float) + (np.array(pb, float) - np.array(pa, float)) * u, np.array(aa, float) + (np.array(ab, float) - np.array(aa, float)) * u, lerp(fa, fb, u)
    return CAM0, AIM0, 5.6

# ---------------------------------------------------------------- 1コマを決める
def apply(t):
    zhi = -(1 - f_hi(t)) * 26.0
    for ob in OBJ.get('hi', []):
        ob.location = (ob['base'][0], ob['base'][1], ob['base'][2] + zhi); ob.hide_render = f_hi(t) < 0.002
    for grp, f, depth in (('low', f_low(t), 2.2), ('masu', f_masu(t), 6.5), ('ten', f_ten(t), 32.0)):
        for ob in OBJ.get(grp, []):
            ob.location = (ob['base'][0], ob['base'][1], ob['base'][2] - (1 - f) * depth); ob.hide_render = f < 0.002
    by = (1 - f_bay(t)) * 1.0
    for ob in OBJ.get('bay', []):
        ob.location = (0, by, zhi); ob.hide_render = f_hi(t) < 0.002
    for ob in OBJ.get('lid', []):
        b = ob['base']; ob.location = (b[0], b[1] + by, b[2] + zhi); ob.rotation_euler = (math.radians(lid_deg(t)), 0, 0); ob.hide_render = f_hi(t) < 0.002
    dg = math.radians(door_deg(t))
    for ob in OBJ.get('door', []):
        b = ob['base']; ob.location = (b[0], b[1], b[2] + zhi); ob.rotation_euler = (0, 0, dg if ob.name.endswith('L') else -dg); ob.hide_render = f_hi(t) < 0.002
    for ob in OBJ.get('moatfloor', []): ob.location = (0, 0, -MOATD * f_floor(t))
    fw = f_water(t)
    for ob in OBJ.get('water', []): ob.location = (0, 0, lerp(-MOATD + 0.05, WATER, fw)); ob.hide_render = fw < 0.02
    for k, ob in enumerate(DROPS):
        r = drop_pos(k, t)
        if r is None: ob.hide_render = True; ob.location = (0, 0, -60); continue
        (x, y, z), rot = r; ob.location = (x, y, z); ob.rotation_euler = (rot, rot * 0.6, 0.3 * k); ob.hide_render = False
    pos = wave_positions(t)
    for i, ob in enumerate(FIG):
        if i < len(pos): place(ob, *pos[i])
        else: ob.hide_render = True; ob.location = (0, 0, -60)
    if RAM:
        rp = ram_pos(t)
        if rp: RAM.location = rp; RAM.hide_render = False
        else: RAM.hide_render = True; RAM.location = (0, 0, -60)
    p, a, fs = cam_at(t); cam = sc.camera
    cam.location = Vector(p); cam.rotation_euler = look(p, a)
    cam.data.dof.focus_distance = float(np.linalg.norm(np.array(a) - np.array(p))); cam.data.dof.aperture_fstop = fs
    g = bpy.data.node_groups['ClayMask']
    A = -0.2 if t < 1.35 else (lerp(-0.05, 1.1, ss(1.35, 2.0, t)) if t < 3.4 else -0.2)
    B = lerp(-0.05, 1.1, ss(2.8, 3.3, t)) if 2.8 <= t < 3.4 else -0.2
    g.nodes['A'].outputs[0].default_value = A; g.nodes['B'].outputs[0].default_value = B

SUN = bpy.data.objects.get('sun')
BG = next((n for n in sc.world.node_tree.nodes if n.bl_idname == 'ShaderNodeBackground' and n.inputs['Color'].is_linked), None)
# ---------------------------------------------------------------- 03/03 の梯子と鉤縄
SIEGE = OBJ.get('siege', [])
LAD = sorted([o for o in SIEGE if o.name.startswith('ladder')], key=lambda o: o.name)
HK = [o for o in SIEGE if o.name.startswith('hrope') or o.name.startswith('hhook')]
def hit_time():
    if not DROPS: return 99.0
    sz, dx, dz, dy = DROPS[0]['spec']; zh = BAY['z0'] - 0.1
    return 17.7 + math.sqrt(max(0.0, zh - LAD[0]['top'][2]) / 4.9) if LAD else 99.0
TH = hit_time()
def siege(t):
    vis = 15.0 <= t <= 21.3
    for i, ob in enumerate(LAD):
        ob.hide_render = not vis
        if not vis: ob.location = (0, 0, -60); continue
        base = Vector(ob['lbase']); top = Vector(ob['top']); u = (top - base).normalized()
        al = math.atan2(u.z, u.y)                      # 地面からの角（壁の側へ傾く）
        jig = 0.004 * math.sin(t * 9.0 + i * 2.0) * (1.0 if t < TH or i else 0.0)   # 登っている重みで少し揺れる
        be = 0.0
        if i == 0 and t > TH:
            tau = min((t - TH) / 1.0, 1.0); e2 = tau * tau            # 石に上を打たれて壁から外れ、横へ倒れる
            al = al + (1.78 - al) * min(1.0, tau * 1.6) ** 1.5; be = 1.5 * e2
        al += jig
        v = Vector((0.0, math.cos(al), math.sin(al)))
        v = Vector((v.z * math.sin(be), v.y, v.z * math.cos(be)))
        X = Vector((math.cos(be), 0.0, -math.sin(be))); Y = v.cross(X).normalized(); X = Y.cross(v).normalized()
        M = Matrix((X, Y, v)).transposed().to_4x4(); M.translation = base; ob.matrix_world = M
    for ob in HK:
        ob.hide_render = not vis
        if not vis: ob.location = (0, 0, -60); continue
        k = 0 if ob.name.endswith('0') else 1
        ang = 0.05 * math.sin(t * 2.3 + k * 1.7) + 0.02 * math.sin(t * 5.1 + k)   # 縄が左右に揺れる
        M = Matrix.Translation(Vector(ob['hk'])) @ Matrix.Rotation(ang, 4, Vector(ob['nrm']))
        ob.matrix_world = M

def light(t):
    w = max(ss(2.3, 3.0, t), 0.75 * ss(1.30, 1.35, t)) * (1 - ss(23.3, 24.3, t))   # 石への寄り（1.35〜）は強い光で色を出す
    if SUN: SUN.data.energy = lerp(1.3, 2.8, w); SUN.data.angle = math.radians(lerp(28, 9, w))
    if BG: BG.inputs['Strength'].default_value = lerp(1.0, 1.35, w)
    for ob in OBJ.get('rope', []):
        b = ob['base']; ob.location = (b[0], b[1], b[2] - (1 - f_hi(t)) * 26.0); ob.hide_render = 1.32 < t < 23.9

def on_frame(scene, depsgraph=None):
    light((scene.frame_current - 1) / FPS); siege((scene.frame_current - 1) / FPS)
    apply((scene.frame_current - 1) / FPS)

bpy.app.handlers.frame_change_pre.clear()
bpy.app.handlers.frame_change_pre.append(on_frame)
sc.cycles.device = 'CPU'
on_frame(sc)
print('k32 anim ready', len(FIG), 'figures', len(DROPS), 'drops', flush=True)
