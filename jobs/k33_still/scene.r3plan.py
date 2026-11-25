"""k33 何面で転がり出す？ — 濡れた石の坂に、削った木の立体（4・6・8・12・20・32・80面・球）を置く。
Blender 4.2。場面を作るだけ（描き出しは外から -s/-e/-a。クラウド描き出し.sh の blender 用）。

MODE（同じフォルダの目印ファイルで切り替え）
  final    : 本編。sim_k33.json があればその軌跡（Blender の剛体計算の実測）を、無ければここで計算して、
             位置・回転をキーフレームに焼く。描くときに剛体の計算は走らない＝どのチャンクから描いても同じ。
  simcheck : 目印 SIMCHECK があるとき。坂の角度×摩擦の組を並べて一度に計算し、
             結果の表（SIMSUM）と軌跡（SIMDATA、zlib+base64）をログに出す。絵は小さく1枚だけ。
"""
import bpy, bmesh, math, os, sys, json, zlib, base64, random
from mathutils import Vector, Matrix, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
MODE = 'simcheck' if os.path.exists(os.path.join(HERE, 'SIMCHECK')) else 'final'
SIM_JSON = os.path.join(HERE, 'sim_k33.json')
FPS = 30

# ── 物理の条件（本編はこの1組。simcheck の結果から決めた） ──
THETA = 26          # 坂の角度（度）
FRIC = 0.75         # 立体・坂・地面それぞれの摩擦（Bullet は掛け算で合わせる＝0.5625）
REST = 0.1          # 跳ね返り（同じく掛け算＝0.01）
LIN_DAMP, ANG_DAMP = 0.01, 0.02
SIM_FRAMES = 180    # 6秒
SUBSTEPS, ITERS = 40, 40
GAP, MARGIN = 0.001, 0.0005
SLAB_L, SLAB_W, SLAB_T = 2.4, 0.46, 0.05
Y0 = SLAB_L / 2 - 0.22          # 置く場所（坂の上端から22cm下）
R_SPHERE = 0.075
VOL = 4 / 3 * math.pi * R_SPHERE ** 3   # どの立体も同じ体積（同じ量の木）
SOLIDS = [4, 6, 8, 12, 20, 32, 80, 0]   # 0 = 球
CHECK_THETAS = [20, 23, 26, 29, 32]
CHECK_FRICS = [0.75, 0.65]

# ── 本編の段（n, コマ数）。sim の結果を見て決める ──
# 実測（sim_k33.json・26°・摩擦0.75）：4〜12面は動かない／20面は4コマ目に動き出し80コマ目で坂の下、108コマ目に平らな所で停止
# 32面は48コマ目で坂の下・秒速2.5m、6秒後も転がる／球は36コマ目で坂の下（約90コマ目で地面の箱の端から落ちるので75コマで切る）
STAGES = [(4, 75), (6, 45), (8, 45), (12, 60), (20, 135), (32, 90), (0, 75)]
END_HOLD = 45       # 最後に空の坂の上（頭の画）へ戻すコマ数（締めの一言をここで言う）

random.seed(33)
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
for m in list(bpy.data.meshes): bpy.data.meshes.remove(m)
for m in list(bpy.data.materials): bpy.data.materials.remove(m)
sc.render.fps = FPS; sc.render.fps_base = 1
sc.frame_start = 1

def key_of(th, fr, n): return f"{int(round(th))}_{int(round(fr * 100))}_{n}"
def zg(th): return -(SLAB_L / 2) * math.sin(math.radians(th))   # 坂の下端の高さ＝地面
def slab_matrix(th, off=Vector((0, 0, 0))):
    return Matrix.Translation(off) @ Matrix.Rotation(math.radians(th), 4, 'X')

# ── 立体の形 ──
PHI = (1 + 5 ** 0.5) / 2
def points(n):
    if n == 4: return [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
    if n == 6: return [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    if n == 8: return [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    if n == 12:
        v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        a, b = 1 / PHI, PHI
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                v += [(0, s1 * a, s2 * b), (s1 * a, s2 * b, 0), (s1 * b, 0, s2 * a)]
        return v
    if n == 20:
        v = []
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                v += [(0, s1, s2 * PHI), (s1, s2 * PHI, 0), (s1 * PHI, 0, s2)]
        return v
    if n == 32:   # 切頂二十面体（サッカーボールの形）
        out = set()
        for (a, b, c) in [(0, 1, 3 * PHI), (1, 2 + PHI, 2 * PHI), (PHI, 2, PHI ** 3)]:
            for sa in ((1, -1) if a else (1,)):
                for sb in (1, -1):
                    for sc_ in (1, -1):
                        p = (a * sa, b * sb, c * sc_)
                        for q in (p, (p[1], p[2], p[0]), (p[2], p[0], p[1])):
                            out.add(tuple(round(t, 9) for t in q))
        return sorted(out)
    raise ValueError(n)

def build_mesh(n):
    bm = bmesh.new()
    if n == 0:
        bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=R_SPHERE)
    elif n == 80:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    else:
        for p in points(n): bm.verts.new(p)
        bmesh.ops.convex_hull(bm, input=list(bm.verts))
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=list(bm.verts), edges=list(bm.edges))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if n:
        s = (VOL / bm.calc_volume(signed=False)) ** (1 / 3)
        bmesh.ops.scale(bm, vec=(s, s, s), verts=list(bm.verts))
    me = bpy.data.meshes.new(f'solid{n}'); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = (n == 0)
    if n and len(me.polygons) != n:
        print(f'WARN faces n={n} got {len(me.polygons)}')
    return me

def rest_pose(me, n):
    """置き方の決まり：どの立体も「いちばん転がりやすい向き」＝傾きの小さい辺を坂の下に向けて面で置く。
    返り値：回転 R（下の面が -Z を向き、その辺が -Y＝坂の下を向く）、重心から面までの高さ d、転がり出す角度（静的）"""
    if n == 0: return Matrix.Identity(3), R_SPHERE, 0.0
    best = None
    for p in me.polygons:
        nrm = p.normal.copy(); d = p.center.dot(nrm); foot = nrm * d
        vs = [me.vertices[i].co.copy() for i in p.vertices]
        for k in range(len(vs)):
            a, b = vs[k], vs[(k + 1) % len(vs)]
            ab = (b - a).normalized(); ap = foot - a
            perp = ap - ab * ap.dot(ab)        # 辺から重心の足へ
            ang = math.atan2(perp.length, d)
            if best is None or ang < best[0] - 1e-6:
                best = (ang, nrm, d, -perp.normalized())
    ang, nrm, d, u = best
    R1 = nrm.rotation_difference(Vector((0, 0, -1))).to_matrix()
    u1 = R1 @ u
    yaw = -math.pi / 2 - math.atan2(u1.y, u1.x)
    return Matrix.Rotation(yaw, 3, 'Z') @ R1, d, math.degrees(ang)

MESH = {n: build_mesh(n) for n in SOLIDS}
POSE = {n: rest_pose(MESH[n], n) for n in SOLIDS}
for n in SOLIDS:
    print(f'SOLID n={n} faces={len(MESH[n].polygons)} d={POSE[n][1]:.4f} tip_deg={POSE[n][2]:.2f}')

def box_mesh(name, x0, x1, y0, y1, z0, z1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 if v.co.x < 0 else x1
        v.co.y = y0 if v.co.y < 0 else y1
        v.co.z = z0 if v.co.z < 0 else z1
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return me

def new_obj(name, me, M=None):
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o)
    if M is not None: o.matrix_world = M
    return o

# ── 剛体の計算（Blender の Bullet） ──
def run_sim(configs):
    slab_me = box_mesh('sim_slab', -SLAB_W / 2, SLAB_W / 2, -SLAB_L / 2, SLAB_L / 2, -SLAB_T, 0)
    actives, passives, info = [], [], []
    k = 0
    for (th, fr) in configs:
        for n in SOLIDS:
            off = Vector((k * 1.2, 0, 0)); k += 1
            SM = slab_matrix(th, off)
            cl = SLAB_L / 2 * math.cos(math.radians(th))
            g_me = box_mesh('sim_ground', -0.6, 0.6, -cl - 6.0, cl + 0.5, -0.3, 0.0)
            slab = new_obj('sim_slab', slab_me, SM)
            gr = new_obj('sim_ground', g_me, Matrix.Translation(off + Vector((0, 0, zg(th)))))
            R, d, _ = POSE[n]
            o = new_obj(f'sim_{key_of(th, fr, n)}', MESH[n], SM @ Matrix.Translation((0, Y0, d + GAP)) @ R.to_4x4())
            o.rotation_mode = 'QUATERNION'
            passives += [(slab, fr), (gr, fr)]; actives.append(o); info.append((o, th, fr, n, SM))
    if sc.rigidbody_world is None: bpy.ops.rigidbody.world_add()
    rbw = sc.rigidbody_world
    rbw.enabled = True
    rbw.substeps_per_frame = SUBSTEPS; rbw.solver_iterations = ITERS
    rbw.use_split_impulse = True
    rbw.point_cache.frame_start = 1; rbw.point_cache.frame_end = SIM_FRAMES + 5
    sc.frame_end = max(sc.frame_end, SIM_FRAMES + 5)
    def add(objs, kind):
        for x in list(bpy.context.selected_objects): x.select_set(False)
        for x in objs: x.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.rigidbody.objects_add(type=kind)
    add([p for p, _ in passives], 'PASSIVE')
    add(actives, 'ACTIVE')
    for p, fr in passives:
        rb = p.rigid_body; rb.collision_shape = 'CONVEX_HULL'; rb.mesh_source = 'BASE'
        rb.friction = fr; rb.restitution = REST; rb.use_margin = True; rb.collision_margin = MARGIN
    for (o, th, fr, n, SM) in info:
        rb = o.rigid_body
        rb.collision_shape = 'SPHERE' if n == 0 else 'CONVEX_HULL'; rb.mesh_source = 'BASE'
        rb.mass = VOL * 600.0
        rb.friction = fr; rb.restitution = REST
        rb.use_margin = True; rb.collision_margin = MARGIN
        rb.linear_damping = LIN_DAMP; rb.angular_damping = ANG_DAMP
        rb.use_deactivation = False
    traj = {key_of(th, fr, n): ([], []) for (o, th, fr, n, SM) in info}
    for f in range(1, SIM_FRAMES + 1):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for (o, th, fr, n, SM) in info:
            M = SM.inverted() @ o.evaluated_get(dg).matrix_world
            loc, rot, _ = M.decompose()
            P, Q = traj[key_of(th, fr, n)]
            P.append(loc.copy()); Q.append(rot.copy())
    bpy.ops.rigidbody.world_remove()
    for (o, *_ ) in info: bpy.data.objects.remove(o, do_unlink=True)
    for p, _ in passives: bpy.data.objects.remove(p, do_unlink=True)
    for m in list(bpy.data.meshes):
        if m.name.startswith('sim_') and m.users == 0: bpy.data.meshes.remove(m)
    sc.frame_set(1)
    return traj

def qang(a, b): return math.degrees(a.rotation_difference(b).angle)

def summarize(n, P, Q):
    N = len(P); p0, q0 = P[0], Q[0]
    moved = next((i for i in range(N) if (P[i] - p0).length > 0.003 or qang(q0, Q[i]) > 3), None)
    faces = []
    if n:
        nr = [p.normal.copy() for p in MESH[n].polygons]
        for i in range(N):
            if P[i].y < -SLAB_L / 2: break
            R = Q[i].to_matrix()
            faces.append(max(range(len(nr)), key=lambda j: -(R @ nr[j]).z))
    seq = []
    for fi in faces:
        if seq and seq[-1][0] == fi: seq[-1][1] += 1
        else: seq.append([fi, 1])
    stable = [s for s in seq if s[1] >= 3]
    tips = max(0, len(stable) - 1)
    first_tip = None
    if len(stable) > 1:
        acc = 0
        for s in seq:
            if s[0] != stable[0][0]: first_tip = acc; break
            acc += s[1]
    slide = sum((P[i] - P[i - 1]).length for i in range(1, len(faces))
                if faces[i] == faces[i - 1] and qang(Q[i - 1], Q[i]) < 0.3)
    rot_total = sum(qang(Q[i - 1], Q[i]) for i in range(1, N))
    last_move = 0
    for i in range(1, N):
        if (P[i] - P[i - 1]).length * FPS > 0.01 or qang(Q[i - 1], Q[i]) * FPS > 2: last_move = i
    off = P[-1].y < -SLAB_L / 2
    moving = last_move >= N - 3
    if moved is None: status = 'stay'
    elif off or moving: status = 'away'
    elif tips >= 1: status = 'roll_stop'
    elif slide > 0.01: status = 'slide_stop'
    else: status = 'wobble'
    return dict(n=n, status=status, moved=moved, first_tip=first_tip, tips=tips, stop=last_move,
                down=round(p0.y - P[-1].y, 4), lateral=round(P[-1].x - p0.x, 4),
                slide=round(slide, 4), rot=round(rot_total, 1), tip_deg=round(POSE[n][2], 2))

def pack(traj):
    out = {}
    for k, (P, Q) in traj.items():
        out[k] = {'p': [int(round(c * 1e4)) for v in P for c in v],
                  'q': [int(round(c * 1e5)) for q in Q for c in (q.w, q.x, q.y, q.z)]}
    return out

def unpack(d):
    p, q = d['p'], d['q']
    P = [Vector((p[i] / 1e4, p[i + 1] / 1e4, p[i + 2] / 1e4)) for i in range(0, len(p), 3)]
    Q = [Quaternion((q[i] / 1e5, q[i + 1] / 1e5, q[i + 2] / 1e5, q[i + 3] / 1e5)).normalized() for i in range(0, len(q), 4)]
    return P, Q

# ══════════════ simcheck ══════════════
if MODE == 'simcheck':
    cfgs = [(th, fr) for fr in CHECK_FRICS for th in CHECK_THETAS]
    traj = run_sim(cfgs)
    for (th, fr) in cfgs:
        for n in SOLIDS:
            P, Q = traj[key_of(th, fr, n)]
            s = summarize(n, P, Q); s.update(theta=th, fric=fr)
            print('SIMSUM ' + json.dumps(s), flush=True)
    blob = base64.b64encode(zlib.compress(json.dumps({'cfg': dict(SLAB_L=SLAB_L, Y0=Y0, FPS=FPS, SIM_FRAMES=SIM_FRAMES),
                                                       'runs': pack(traj)}, separators=(',', ':')).encode(), 9)).decode()
    CH = 6000; parts = [blob[i:i + CH] for i in range(0, len(blob), CH)]
    for i, part in enumerate(parts): print(f'SIMDATA {i}/{len(parts)} {part}', flush=True)
    sys.stdout.flush()
    # クラウドには libEGL が無く Workbench/EEVEE は落ちる → Cycles。運用の決まり：確認は 270×480・8サンプル・デノイズ
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 8; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 270, 480
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam)
    cam.location = (2, -3, 2); cam.rotation_euler = (1.1, 0, 0.6); sc.camera = cam
    sc.frame_start = 1; sc.frame_end = 1

# ══════════════ final ══════════════
else:
    if os.path.exists(SIM_JSON):
        runs = json.load(open(SIM_JSON))['runs']
        TRAJ = {n: unpack(runs[key_of(THETA, FRIC, n)]) for n in SOLIDS}
        print('SIM from json', SIM_JSON)
    else:
        t = run_sim([(THETA, FRIC)])
        TRAJ = {n: t[key_of(THETA, FRIC, n)] for n in SOLIDS}
        print('SIM computed in scene (no json)')
    for n in SOLIDS:
        print('SIMSUM ' + json.dumps(summarize(n, *TRAJ[n])), flush=True)

    SM = slab_matrix(THETA)
    SMq = SM.to_quaternion()

    # ── 材質（すべてノードで手続き生成） ──
    def new_mat(name):
        m = bpy.data.materials.new(name); m.use_nodes = True
        nt = m.node_tree
        return m, nt.nodes, nt.links, nt.nodes['Principled BSDF']
    def ramp(N, stops):
        r = N.new('ShaderNodeValToRGB'); el = r.color_ramp.elements
        el[0].position, el[0].color = stops[0][0], (*stops[0][1], 1)
        el[1].position, el[1].color = stops[-1][0], (*stops[-1][1], 1)
        for pos, col in stops[1:-1]:
            e = el.new(pos); e.color = (*col, 1)
        return r
    def mix_rgb(N, L, fac, a, b, blend='MIX'):
        m = N.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = blend
        if isinstance(fac, float): m.inputs[0].default_value = fac
        else: L.new(fac, m.inputs[0])
        for sock, v in ((m.inputs[6], a), (m.inputs[7], b)):
            if isinstance(v, tuple): sock.default_value = (*v, 1)
            else: L.new(v, sock)
        return m.outputs[2]
    def mix_f(N, L, fac, a, b):
        m = N.new('ShaderNodeMix'); m.data_type = 'FLOAT'
        L.new(fac, m.inputs[0])
        for sock, v in ((m.inputs[2], a), (m.inputs[3], b)):
            if isinstance(v, float): sock.default_value = v
            else: L.new(v, sock)
        return m.outputs[0]
    def noise(N, L, vec, scale, detail=4.0, rough=0.55, dist=0.0):
        t = N.new('ShaderNodeTexNoise'); t.inputs['Scale'].default_value = scale
        t.inputs['Detail'].default_value = detail; t.inputs['Roughness'].default_value = rough
        t.inputs['Distortion'].default_value = dist
        if vec is not None: L.new(vec, t.inputs['Vector'])
        return t
    def mapping(N, L, vec, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), kind='POINT'):
        mp = N.new('ShaderNodeMapping'); mp.vector_type = kind
        for nm, v in (('Location', loc), ('Rotation', rot), ('Scale', scale)):
            if nm in mp.inputs: mp.inputs[nm].default_value = v   # NORMAL 型には Location が無い
        L.new(vec, mp.inputs['Vector']); return mp.outputs['Vector']
    def bump(N, L, h, strength, dist, normal=None):
        b = N.new('ShaderNodeBump'); b.inputs['Distance'].default_value = dist
        if isinstance(strength, float): b.inputs['Strength'].default_value = strength
        else: L.new(strength, b.inputs['Strength'])
        L.new(h, b.inputs['Height'])
        if normal is not None: L.new(normal, b.inputs['Normal'])
        return b.outputs['Normal']
    def math_node(N, L, op, a, b=None, clamp=False):
        m = N.new('ShaderNodeMath'); m.operation = op; m.use_clamp = clamp
        for sock, v in ((m.inputs[0], a), (m.inputs[1], b)):
            if v is None: continue
            if isinstance(v, (int, float)): sock.default_value = float(v)
            else: L.new(v, sock)
        return m.outputs[0]

    def wood_mat():
        """削ったブナ材：年輪は立体の中を通る3次元の模様なので、面ごとに切り口の模様が変わる。木口（年輪に直角）は濃く粗い"""
        m, N, L, b = new_mat('wood')
        tc = N.new('ShaderNodeTexCoord')
        ROT = (0.46, 0.21, 0.33)
        g = mapping(N, L, tc.outputs['Object'], loc=(0.62, -0.41, 0.0), rot=ROT)
        wob = noise(N, L, g, 3.0, detail=3.0)
        wv = N.new('ShaderNodeVectorMath'); wv.operation = 'SUBTRACT'; L.new(wob.outputs['Color'], wv.inputs[0]); wv.inputs[1].default_value = (0.5, 0.5, 0.5)
        ws = N.new('ShaderNodeVectorMath'); ws.operation = 'SCALE'; L.new(wv.outputs[0], ws.inputs[0]); ws.inputs['Scale'].default_value = 0.0045
        gp = N.new('ShaderNodeVectorMath'); gp.operation = 'ADD'; L.new(g, gp.inputs[0]); L.new(ws.outputs[0], gp.inputs[1])
        rings = N.new('ShaderNodeTexWave'); rings.wave_type = 'RINGS'; rings.rings_direction = 'Z'; rings.wave_profile = 'SAW'
        rings.inputs['Scale'].default_value = 135.0; rings.inputs['Distortion'].default_value = 0.0
        L.new(gp.outputs[0], rings.inputs['Vector'])
        rr = ramp(N, [(0.0, (0.47, 0.315, 0.185)), (0.66, (0.45, 0.30, 0.17)), (0.88, (0.38, 0.245, 0.13)), (1.0, (0.34, 0.21, 0.11))])
        L.new(rings.outputs['Fac'], rr.inputs['Fac'])
        # 道管（年輪に沿った細い筋）
        pg = mapping(N, L, gp.outputs[0], scale=(700, 700, 18))
        pores = noise(N, L, pg, 1.0, detail=1.0)
        pr = ramp(N, [(0.0, (0.72, 0.72, 0.72)), (0.30, (1, 1, 1)), (1.0, (1, 1, 1))])
        L.new(pores.outputs['Fac'], pr.inputs['Fac'])
        col = mix_rgb(N, L, 1.0, rr.outputs['Color'], pr.outputs['Color'], 'MULTIPLY')
        # 色むら（大きい）
        big = noise(N, L, g, 9.0, detail=2.0)
        br = ramp(N, [(0.35, (0.88, 0.86, 0.84)), (0.65, (1.06, 1.03, 1.0))])
        L.new(big.outputs['Fac'], br.inputs['Fac'])
        col = mix_rgb(N, L, 1.0, col, br.outputs['Color'], 'MULTIPLY')
        fib = noise(N, L, mapping(N, L, gp.outputs[0], scale=(260, 260, 6)), 1.0, detail=4.0, rough=0.6)   # r3：繊維の筋
        fr_ = ramp(N, [(0.3, (0.80, 0.78, 0.76)), (0.7, (1.0, 1.0, 1.0))])
        L.new(fib.outputs['Fac'], fr_.inputs['Fac'])
        col = mix_rgb(N, L, 1.0, col, fr_.outputs['Color'], 'MULTIPLY')
        # 木口：面の向きが年輪の軸に近いほど濃く・粗い
        nrm = mapping(N, L, tc.outputs['Normal'], rot=ROT, kind='NORMAL')
        sep = N.new('ShaderNodeSeparateXYZ'); L.new(nrm, sep.inputs[0])
        endg = math_node(N, L, 'ABSOLUTE', sep.outputs['Z'])
        endf = math_node(N, L, 'POWER', endg, 3.0)
        col = mix_rgb(N, L, endf, col, (0.20, 0.12, 0.06), 'MIX')
        L.new(col, b.inputs['Base Color'])
        b.inputs['Roughness'].default_value = 0.6
        L.new(mix_f(N, L, endf, 0.58, 0.78), b.inputs['Roughness'])
        b.inputs['Specular IOR Level'].default_value = 0.45
        # 刃物の跡（面ごとの浅いうねり）＋年輪・道管の凹凸
        tool = N.new('ShaderNodeTexWave'); tool.wave_type = 'BANDS'; tool.bands_direction = 'DIAGONAL'
        tool.inputs['Scale'].default_value = 14.0; tool.inputs['Distortion'].default_value = 4.0
        tool.inputs['Detail'].default_value = 2.0
        L.new(tc.outputs['Object'], tool.inputs['Vector'])
        h = math_node(N, L, 'ADD', tool.outputs['Fac'], math_node(N, L, 'MULTIPLY', pores.outputs['Fac'], 0.6))
        L.new(bump(N, L, h, 0.025, 0.0008), b.inputs['Normal'])
        return m

    def slate_mat():
        """濡れた粘板岩（スレート）：濃い青灰に薄い錆、劈開の段、濡れたところだけ表面に水の膜（コート）"""
        m, N, L, b = new_mat('slate')
        tc = N.new('ShaderNodeTexCoord'); o = tc.outputs['Object']
        c1 = noise(N, L, o, 2.2, detail=8.0, rough=0.6)
        cr = ramp(N, [(0.25, (0.030, 0.033, 0.037)), (0.55, (0.048, 0.050, 0.054)), (0.85, (0.075, 0.074, 0.071))])
        mid = noise(N, L, o, 14.0, detail=6.0, rough=0.6)            # r3：手の大きさのまだら（画面で読める大きさ）
        c1m = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', c1.outputs['Fac'], 0.6), math_node(N, L, 'MULTIPLY', mid.outputs['Fac'], 0.4))
        L.new(c1m, cr.inputs['Fac'])
        rust = noise(N, L, o, 6.5, detail=5.0)
        rr = ramp(N, [(0.62, (0, 0, 0)), (0.72, (1, 1, 1))])
        L.new(rust.outputs['Fac'], rr.inputs['Fac'])
        rf = math_node(N, L, 'MULTIPLY', rr.outputs['Color'], 0.35)
        col = mix_rgb(N, L, rf, cr.outputs['Color'], (0.085, 0.052, 0.030))
        # 劈開の段（板の厚みの向きに層、上面には細長い段差）
        lay = N.new('ShaderNodeTexWave'); lay.wave_type = 'BANDS'; lay.bands_direction = 'Z'
        lay.inputs['Scale'].default_value = 18.0; lay.inputs['Distortion'].default_value = 6.0; lay.inputs['Detail'].default_value = 6.0
        L.new(mapping(N, L, o, scale=(1, 0.3, 1)), lay.inputs['Vector'])
        step = noise(N, L, mapping(N, L, o, scale=(3.0, 0.8, 3.0)), 3.0, detail=10.0, rough=0.7)
        grit = noise(N, L, o, 260.0, detail=2.0)
        h = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', lay.outputs['Fac'], 0.5), step.outputs['Fac'])
        h = math_node(N, L, 'ADD', h, math_node(N, L, 'MULTIPLY', grit.outputs['Fac'], 0.25))
        # 濡れの膜（まだら）
        wet = noise(N, L, o, 2.6, detail=4.0, rough=0.5)
        wr = ramp(N, [(0.50, (0, 0, 0)), (0.58, (1, 1, 1))])
        L.new(wet.outputs['Fac'], wr.inputs['Fac'])
        wf = math_node(N, L, 'MULTIPLY', wr.outputs['Color'], 1.0)   # 濡れはまだらに（乾いた所は粗い石のまま）
        # 薄い灰色の筋（擦れ・石の層の出た所）
        vein = noise(N, L, mapping(N, L, o, scale=(9.0, 1.2, 9.0)), 2.0, detail=6.0, rough=0.65)
        vr = ramp(N, [(0.54, (0, 0, 0)), (0.64, (1, 1, 1))])
        L.new(vein.outputs['Fac'], vr.inputs['Fac'])
        col = mix_rgb(N, L, math_node(N, L, 'MULTIPLY', vr.outputs['Color'], 0.6), col, (0.075, 0.075, 0.072))
        dark = N.new('ShaderNodeMix'); dark.data_type = 'RGBA'; dark.blend_type = 'MULTIPLY'
        L.new(wf, dark.inputs[0]); L.new(col, dark.inputs[6]); dark.inputs[7].default_value = (0.42, 0.42, 0.42, 1)
        L.new(dark.outputs[2], b.inputs['Base Color'])
        L.new(mix_f(N, L, wf, 0.74, 0.32), b.inputs['Roughness'])
        b.inputs['Specular IOR Level'].default_value = 0.35
        L.new(bump(N, L, h, mix_f(N, L, wf, 0.6, 0.15), 0.003), b.inputs['Normal'])
        L.new(wf, b.inputs['Coat Weight'])
        b.inputs['Coat Roughness'].default_value = 0.035
        b.inputs['Coat IOR'].default_value = 1.33
        return m

    def ground_mat():
        """苔と砂利の地面（ぼけて写る）"""
        m, N, L, b = new_mat('ground')
        tc = N.new('ShaderNodeTexCoord'); o = tc.outputs['Object']
        n1 = noise(N, L, o, 1.3, detail=6.0)
        r1 = ramp(N, [(0.35, (0.020, 0.017, 0.012)), (0.6, (0.030, 0.042, 0.016)), (0.8, (0.040, 0.052, 0.020))])
        L.new(n1.outputs['Fac'], r1.inputs['Fac'])
        vo = N.new('ShaderNodeTexVoronoi'); vo.inputs['Scale'].default_value = 55.0
        L.new(o, vo.inputs['Vector'])
        vr = ramp(N, [(0.0, (1, 1, 1)), (0.45, (1, 1, 1)), (0.6, (0, 0, 0))])
        L.new(vo.outputs['Distance'], vr.inputs['Fac'])
        gmask = math_node(N, L, 'MULTIPLY', vr.outputs['Color'], math_node(N, L, 'GREATER_THAN', n1.outputs['Fac'], 0.5))
        col = mix_rgb(N, L, gmask, r1.outputs['Color'], (0.070, 0.068, 0.062))
        L.new(col, b.inputs['Base Color'])
        b.inputs['Roughness'].default_value = 0.85
        L.new(bump(N, L, vr.outputs['Color'], 0.5, 0.01), b.inputs['Normal'])
        return m

    def wall_mat():
        """奥の石垣（大きくぼける）"""
        m, N, L, b = new_mat('wall')
        tc = N.new('ShaderNodeTexCoord'); o = tc.outputs['Object']
        bk = N.new('ShaderNodeTexBrick'); bk.inputs['Scale'].default_value = 1.0
        bk.inputs['Brick Width'].default_value = 0.42; bk.inputs['Row Height'].default_value = 0.24
        bk.inputs['Mortar Size'].default_value = 0.015; bk.offset = 0.45
        bk.inputs['Color1'].default_value = (0.06, 0.062, 0.058, 1); bk.inputs['Color2'].default_value = (0.09, 0.088, 0.08, 1)
        bk.inputs['Mortar'].default_value = (0.02, 0.025, 0.015, 1)
        L.new(mapping(N, L, o, rot=(math.pi / 2, 0, math.pi / 2)), bk.inputs['Vector'])
        moss = noise(N, L, o, 1.8, detail=5.0)
        mr = ramp(N, [(0.45, (0, 0, 0)), (0.65, (1, 1, 1))])
        L.new(moss.outputs['Fac'], mr.inputs['Fac'])
        col = mix_rgb(N, L, mr.outputs['Color'], bk.outputs['Color'], (0.035, 0.05, 0.02))
        L.new(col, b.inputs['Base Color']); b.inputs['Roughness'].default_value = 0.8
        L.new(bump(N, L, bk.outputs['Fac'], 0.6, 0.02), b.inputs['Normal'])
        return m

    def granite_mat():
        m, N, L, b = new_mat('granite')
        tc = N.new('ShaderNodeTexCoord'); o = tc.outputs['Object']
        sp = noise(N, L, o, 90.0, detail=2.0)
        r = ramp(N, [(0.3, (0.045, 0.045, 0.045)), (0.5, (0.09, 0.088, 0.084)), (0.7, (0.14, 0.135, 0.13))])
        L.new(sp.outputs['Fac'], r.inputs['Fac'])
        L.new(r.outputs['Color'], b.inputs['Base Color']); b.inputs['Roughness'].default_value = 0.7
        L.new(bump(N, L, noise(N, L, o, 25.0, detail=8.0).outputs['Fac'], 0.4, 0.004), b.inputs['Normal'])
        return m

    def water_mat():
        m, N, L, b = new_mat('water')
        b.inputs['Base Color'].default_value = (1, 1, 1, 1)
        b.inputs['Roughness'].default_value = 0.0
        b.inputs['IOR'].default_value = 1.33
        b.inputs['Transmission Weight'].default_value = 1.0
        return m

    WOOD, SLATE, GROUND, WALL, GRANITE, WATER = wood_mat(), slate_mat(), ground_mat(), wall_mat(), granite_mat(), water_mat()

    # ── 坂（濡れた石の板） ──
    slab_me = box_mesh('slab', -SLAB_W / 2, SLAB_W / 2, -SLAB_L / 2, SLAB_L / 2, -SLAB_T, 0)
    slab = new_obj('slab', slab_me, SM); slab.data.materials.append(SLATE)
    bv = slab.modifiers.new('bv', 'BEVEL'); bv.width = 0.004; bv.segments = 3
    # 板の上の水滴（置く所と真ん中の通り道はまばら）
    bm = bmesh.new()
    for i in range(900):
        x = random.uniform(-SLAB_W / 2 + 0.01, SLAB_W / 2 - 0.01)
        y = random.uniform(-SLAB_L / 2 + 0.02, SLAB_L / 2 - 0.02)
        if (Vector((x, y)) - Vector((0, Y0))).length < 0.17: continue
        if abs(x) < 0.13 and random.random() < 0.8: continue
        r = random.choice([0.0012, 0.0016, 0.002, 0.0025, 0.003, 0.0035, 0.0045])
        ret = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
        sq = random.uniform(0.38, 0.5)
        for v in ret['verts']:
            z = max(v.co.z, -0.2 * r)
            v.co = Vector((v.co.x, v.co.y, (z + 0.2 * r) * sq)) + Vector((x, y, 0))
    dme = bpy.data.meshes.new('drops'); bm.to_mesh(dme); bm.free()
    for p in dme.polygons: p.use_smooth = True
    drops = new_obj('drops', dme, SM); drops.data.materials.append(WATER)

    # ── 上の端を支える石・地面・奥の石垣 ──
    th = math.radians(THETA)
    top_y = SLAB_L / 2 * math.cos(th); top_z = SLAB_L / 2 * math.sin(th) - SLAB_T / math.cos(th)
    y_lo = top_y - 0.26
    top_z = y_lo * math.tan(th) - SLAB_T / math.cos(th) - 0.002     # 板の下面（いちばん低い所）に当たる高さ
    st = new_obj('support', box_mesh('support', -0.34, 0.34, y_lo, top_y + 0.06, zg(THETA) - 0.1, top_z), None)
    st.data.materials.append(GRANITE)
    sbv = st.modifiers.new('bv', 'BEVEL'); sbv.width = 0.02; sbv.segments = 3
    gnd = new_obj('ground', box_mesh('ground', -12, 12, -14, 10, zg(THETA) - 0.3, zg(THETA)), None)
    gnd.data.materials.append(GROUND)
    wall = new_obj('wall', box_mesh('wall', -3.4, -3.0, -10, 10, zg(THETA) - 0.1, zg(THETA) + 3.2), None)
    wall.data.materials.append(WALL)

    # ── 空と光（薄曇りの昼） ──
    world = bpy.data.worlds.new('sky') if sc.world is None else sc.world
    sc.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    for x in list(wn): wn.remove(x)
    sky = wn.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'
    sky.sun_disc = False; sky.sun_elevation = math.radians(38); sky.sun_rotation = math.radians(-120)
    sky.air_density = 1.6; sky.dust_density = 4.0
    bgn = wn.new('ShaderNodeBackground'); bgn.inputs['Strength'].default_value = 0.22
    outn = wn.new('ShaderNodeOutputWorld')
    wl.new(sky.outputs['Color'], bgn.inputs['Color']); wl.new(bgn.outputs['Background'], outn.inputs['Surface'])
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sc.collection.objects.link(sun)
    sun.data.energy = 2.2; sun.data.angle = math.radians(9); sun.data.color = (1.0, 0.96, 0.9)
    sdir = Vector((0.60, -0.30, 0.74)).normalized()   # 4面体の見える2面で明暗が分かれる向き。濡れた坂の照り返しはカメラに入らない
    sun.rotation_mode = 'QUATERNION'; sun.rotation_quaternion = sdir.to_track_quat('Z', 'Y')

    # ── 立体（段ごとに1つ。計算の軌跡をキーフレームに焼く） ──
    def fc_set(action, path, idx, frames, vals, interp):
        fc = action.fcurves.new(path, index=idx)
        fc.keyframe_points.add(len(frames))
        co = []
        for f, v in zip(frames, vals): co += [float(f), float(v)]
        fc.keyframe_points.foreach_set('co', co)
        ip = ('CONSTANT', 'LINEAR')[interp]
        for kp in fc.keyframe_points: kp.interpolation = ip
        fc.update()

    starts = []; f = 1
    for (n, ln) in STAGES: starts.append(f); f += ln
    TOTAL = f - 1 + END_HOLD
    A = SM @ Vector((0, Y0, 0.075))           # いつもの構図の中心（置く場所の少し上）
    world_pos = {}                             # 段の物の位置（カメラ用）
    for si, ((n, ln), s0) in enumerate(zip(STAGES, starts)):
        P, Q = TRAJ[n]
        o = new_obj(f'stage{si}_{n}', MESH[n], None)
        if not o.data.materials: o.data.materials.append(WOOD)
        if n:
            mb = o.modifiers.new('bv', 'BEVEL'); mb.width = 0.0012; mb.segments = 2; mb.limit_method = 'ANGLE'
            mb.harden_normals = False
        o.rotation_mode = 'QUATERNION'
        frames = list(range(s0, s0 + ln)); locs = []; rots = []; prev = None
        for t in range(ln):
            p, q = P[min(t, len(P) - 1)], Q[min(t, len(Q) - 1)]
            wp = SM @ p; wq = SMq @ q
            if prev is not None and prev.dot(wq) < 0: wq = Quaternion((-wq.w, -wq.x, -wq.y, -wq.z))
            prev = wq; locs.append(wp); rots.append(wq)
            world_pos[s0 + t] = (wp, SM @ P[0])
        act = bpy.data.actions.new(f'act{si}'); o.animation_data_create(); o.animation_data.action = act
        for i in range(3): fc_set(act, 'location', i, frames, [v[i] for v in locs], 1)
        for i in range(4): fc_set(act, 'rotation_quaternion', i, frames, [q[i] for q in rots], 1)
        hf = [1, s0, s0 + ln] if s0 > 1 else [s0, s0 + ln]
        hv = [1, 0, 1] if s0 > 1 else [0, 1]
        fc_set(act, 'hide_render', 0, hf, hv, 0)
        fc_set(act, 'hide_viewport', 0, hf, hv, 0)

    # ── カメラ（いつもの構図→転がったら追う。手持ちの小さな揺れ） ──
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.lens = 50; cam.data.sensor_width = 36; cam.data.sensor_fit = 'AUTO'
    cam.data.dof.use_dof = True; cam.data.dof.aperture_fstop = 2.8
    foc = bpy.data.objects.new('focus', None); sc.collection.objects.link(foc); cam.data.dof.focus_object = foc
    # 斜め45°・仰角38°・1.05m：4面体の2つの面が同じくらいに見え（手前に稜線）、坂は右上→左下の対角に読める
    # 4面体の坂の下側の面はほぼ垂直になるため、3面を見せるには坂の下から60°以上見下ろす必要があり、坂が平らに見えるので採らない
    # r3（未描画）：r2 は上から見下ろしすぎて板が平らな天板に見えた → 斜め35°・仰角26°。坂の線と水平の差が画面で18°→24°、
    # 奥の石垣の根元（水平の目安）が主役の後ろ（約780px）に入る。主役は 650〜1270px（計算）
    OFF = Vector((0.7363, -0.5155, 0.4384)).normalized() * 1.05
    AIM = Vector((0, 0, -0.03))
    cam.rotation_mode = 'QUATERNION'
    cf, cl, cr, ff = [], [], [], []
    s1 = s2 = None; stage_of = {}
    for si, s0 in enumerate(starts):
        for t in range(STAGES[si][1]): stage_of[s0 + t] = si
    for fr_ in range(1, TOTAL + 1):
        if fr_ in world_pos:
            wp, w0 = world_pos[fr_]
            if fr_ in starts: s1 = s2 = Vector((0, 0, 0))
            d = wp - w0
            a = 0.16
            s1 = s1 + (d - s1) * a; s2 = s2 + (s1 - s2) * a
            T = A + s2
        else:
            T = A.copy()
        tt = fr_ / FPS
        shake = Vector((0.0015 * math.sin(tt * 1.3 + 0.4) + 0.0008 * math.sin(tt * 3.1),
                        0.0012 * math.sin(tt * 1.7 + 1.1), 0.0010 * math.sin(tt * 2.3 + 2.0)))
        pos = T + OFF + shake
        look = T + AIM + Vector((0.0006 * math.sin(tt * 2.1), 0, 0.0005 * math.sin(tt * 1.5)))
        q = (look - pos).to_track_quat('-Z', 'Y')
        cf.append(fr_); cl.append(pos); cr.append(q); ff.append(T)
    act = bpy.data.actions.new('camact'); cam.animation_data_create(); cam.animation_data.action = act
    for i in range(3): fc_set(act, 'location', i, cf, [v[i] for v in cl], 1)
    prev = None
    for k in range(len(cr)):
        if prev is not None and prev.dot(cr[k]) < 0: cr[k] = Quaternion((-cr[k].w, -cr[k].x, -cr[k].y, -cr[k].z))
        prev = cr[k]
    for i in range(4): fc_set(act, 'rotation_quaternion', i, cf, [q[i] for q in cr], 1)
    fact = bpy.data.actions.new('focact'); foc.animation_data_create(); foc.animation_data.action = fact
    for i in range(3): fc_set(fact, 'location', i, cf, [v[i] for v in ff], 1)

    # ── 描き出しの設定（呼び出しはしない） ──
    sc.frame_start = 1; sc.frame_end = TOTAL
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 64
    sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.015
    sc.cycles.use_denoising = True; sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    sc.cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    sc.cycles.max_bounces = 8; sc.cycles.diffuse_bounces = 3; sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 8; sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0; sc.cycles.sample_clamp_indirect = 6.0
    sc.render.use_persistent_data = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1080, 1920, 100
    sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = 'AgX'
    try: sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception: pass
    sc.view_settings.exposure = 0.0
    print('STAGES ' + json.dumps([dict(n=n, start=s0, frames=ln) for (n, ln), s0 in zip(STAGES, starts)]) + f' TOTAL {TOTAL}')
