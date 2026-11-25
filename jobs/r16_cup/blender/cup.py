# R16 コップの場面（11/25 動画作成・Blender 5.3・Cycles）。0〜4秒：机の上の水のグラスとストロー、水が減っていく（L00「1日2Lずつ飲むと…」）。
# 終わり（L12〜L14）は同じコマを逆に回して満ちていく → 最初のコマ（満タン）へ戻ってループ。人・顔・ロゴは出さない。光る物は使わない。
# 使い方：blender -b -P cup.py -- --t 0.0 --out ../preview/cup_test.png [--samples 48] [--res 50]
#         blender -b -P cup.py -- --anim --fs 0 --fe 120 --step 2 --outdir ../frames_cup
import bpy, math, sys, os, argparse
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
ap.add_argument('--t', type=float, default=0.0); ap.add_argument('--out', default=os.path.join(ROOT, 'preview', 'cup_test.png'))
ap.add_argument('--samples', type=int, default=48); ap.add_argument('--res', type=int, default=50)
ap.add_argument('--anim', action='store_true'); ap.add_argument('--fs', type=int, default=0); ap.add_argument('--fe', type=int, default=120)
ap.add_argument('--step', type=int, default=1); ap.add_argument('--outdir', default=os.path.join(ROOT, 'frames_cup'))
ap.add_argument('--wb', default='')   # 11/25 締めの灰色：solid（粘土）／wire（線だけ・背景透明）。出力は frames_cup_wb/{s,w}_####.png
A = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.samples = A.samples; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 32; sc.cycles.transmission_bounces = 24; sc.cycles.glossy_bounces = 16; sc.cycles.transparent_max_bounces = 16; sc.cycles.diffuse_bounces = 4
sc.cycles.blur_glossy = 0.5; sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False   # v10：運用の指定（破片のような映り込みを消す）
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1080, 1920, A.res
sc.render.threads_mode = 'FIXED'; sc.render.threads = 4
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'; sc.view_settings.exposure = -1.3   # v7：明るすぎて机と壁が白く飛んでいた
w = bpy.data.worlds.new('room'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.10, 0.09, 0.08, 1)   # v6：部屋を暗めに（ガラスが周りを銀色に映さないように）; w.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0

def mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True; return m, m.node_tree.nodes, m.node_tree.links

# 机（木目：波の模様＋ノイズ。明るめの楢）
bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0)); desk = bpy.context.object
m, N, L = mat('wood'); b = N['Principled BSDF']
tc = N.new('ShaderNodeTexCoord'); mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (4.0, 40.0, 4.0)
# ↑ 11/25 v3：木目を細かく（水の屈折で木目が歪んで水が見えるように）。v6：つなぎの1行が上の行のコメントに入って木目が消えていたのを直した
L.new(tc.outputs['Object'], mp.inputs[0])
nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 3.0; nz.inputs['Detail'].default_value = 6.0; L.new(mp.outputs[0], nz.inputs['Vector'])
wv = N.new('ShaderNodeTexWave'); wv.inputs['Scale'].default_value = 2.2; wv.inputs['Distortion'].default_value = 6.0; wv.inputs['Detail'].default_value = 3.0; L.new(mp.outputs[0], wv.inputs['Vector'])
mx = N.new('ShaderNodeMix'); mx.data_type = 'FLOAT'; mx.inputs[0].default_value = 0.6; L.new(wv.outputs['Fac'], mx.inputs[2]); L.new(nz.outputs['Fac'], mx.inputs[3])
cr = N.new('ShaderNodeValToRGB'); L.new(mx.outputs[0], cr.inputs[0])
cr.color_ramp.elements[0].color = (0.10, 0.05, 0.025, 1); cr.color_ramp.elements[1].color = (0.32, 0.18, 0.09, 1)   # 胡桃（濃い木）
L.new(cr.outputs[0], b.inputs['Base Color']); b.inputs['Roughness'].default_value = 0.42
bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.08; L.new(mx.outputs[0], bp.inputs['Height']); L.new(bp.outputs[0], b.inputs['Normal'])
desk.data.materials.append(m)

# 奥の壁（ぼける。漆喰の明るい灰）
bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 2.2, 2.0), rotation=(math.radians(90), 0, 0)); wall = bpy.context.object
m, N, L = mat('wall'); wb = N['Principled BSDF']   # v7：暗めの塗り壁＋縦の板目（水とガラスごしの歪みが見えるように）
wtc = N.new('ShaderNodeTexCoord'); wwv = N.new('ShaderNodeTexWave'); wwv.wave_type = 'BANDS'; wwv.bands_direction = 'X'; wwv.inputs['Scale'].default_value = 9.0; wwv.inputs['Distortion'].default_value = 1.5
L.new(wtc.outputs['Object'], wwv.inputs['Vector'])
wcr = N.new('ShaderNodeValToRGB'); L.new(wwv.outputs['Fac'], wcr.inputs[0]); wcr.color_ramp.elements[0].color = (0.10, 0.075, 0.055, 1); wcr.color_ramp.elements[1].color = (0.30, 0.23, 0.17, 1)
L.new(wcr.outputs[0], wb.inputs['Base Color']); N['Principled BSDF'].inputs['Roughness'].default_value = 0.9
wall.data.materials.append(m)
# v8：左右と手前にも同じ板壁（水の縁は横の物を映すので、何も無いと黒や銀の帯になる）
for loc, rot in (((-1.1, 0.4, 1.5), (math.radians(90), 0, math.radians(90))), ((1.1, 0.4, 1.5), (math.radians(90), 0, math.radians(-90))), ((0, -2.4, 1.5), (math.radians(90), 0, math.radians(180)))):
    bpy.ops.mesh.primitive_plane_add(size=5, location=loc, rotation=rot); bpy.context.object.data.materials.append(m)

# グラス（高さ 0.14・口の半径 0.036・底の半径 0.031・厚み 2mm・底は 6mm）
H, R1, R0, TH = 0.14, 0.036, 0.031, 0.002
bpy.ops.mesh.primitive_cone_add(vertices=128, radius1=R0, radius2=R1, depth=H, end_fill_type='NGON', location=(0, 0, H / 2)); glass = bpy.context.object
bm_del = [f for f in glass.data.polygons if f.center.z > H / 2 - 1e-4 and abs(f.normal.z) > 0.9]
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
for f in glass.data.polygons: f.select = (f.center.z > H / 2 - 1e-4 and abs(f.normal.z) > 0.9)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.delete(type='FACE'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.normals_make_consistent(inside=False); bpy.ops.object.mode_set(mode='OBJECT')
so = glass.modifiers.new('thick', 'SOLIDIFY'); so.thickness = TH; so.offset = -1; so.use_flip_normals = True
glass.modifiers.new('bevel', 'BEVEL').width = 0.0008; bpy.ops.object.shade_smooth()
m, N, L = mat('glass'); g = N['Principled BSDF']   # v6：金属っぽさ0・透過・IOR 1.45（縁の反射だけ）
g.inputs['Base Color'].default_value = (1, 1, 1, 1); g.inputs['Metallic'].default_value = 0.0; g.inputs['Roughness'].default_value = 0.0
g.inputs['IOR'].default_value = 1.45; g.inputs['Transmission Weight'].default_value = 1.0
# 11/25 v4：集光を切っているので、ガラスの中が影になり水とストローが黒く沈んだ → 影の光線だけ素通し（よくある作り）
def shadow_pass(N, L, sh):
    lp = N.new('ShaderNodeLightPath'); tr = N.new('ShaderNodeBsdfTransparent'); mx = N.new('ShaderNodeMixShader')
    L.new(lp.outputs['Is Shadow Ray'], mx.inputs[0]); L.new(sh.outputs[0], mx.inputs[1]); L.new(tr.outputs[0], mx.inputs[2]); return mx
L.new(shadow_pass(N, L, g).outputs[0], N['Material Output'].inputs['Surface']); glass.data.materials.append(m)
bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=R0 - 0.0005, depth=0.006, location=(0, 0, 0.003)); base = bpy.context.object; base.data.materials.append(m); bpy.ops.object.shade_smooth()

# 水（グラスの内側。上面の高さを動かす）。v9：ガラスとの境目は 0.3mm 食い込ませる
def water_radius(z): return (R0 + (R1 - R0) * z / H) - TH + 0.0   # v10H：水をガラスに0.3mm食い込ませる（すき間の空気で全反射して縁が黒い帯になっていた）
bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=1.0, depth=1.0, location=(0, 0, 0.5)); water = bpy.context.object; bpy.ops.object.shade_smooth()
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
m, N, L = mat('water'); wg = N['Principled BSDF']   # v6：透明で少しだけ青い水
wg.inputs['Base Color'].default_value = (0.92, 0.97, 1.0, 1); wg.inputs['Metallic'].default_value = 0.0; wg.inputs['Roughness'].default_value = 0.0
wg.inputs['IOR'].default_value = 1.333; wg.inputs['Transmission Weight'].default_value = 1.0
va = N.new('ShaderNodeVolumeAbsorption'); va.inputs['Color'].default_value = (0.80, 0.93, 1.0, 1); va.inputs['Density'].default_value = 5.0
L.new(shadow_pass(N, L, wg).outputs[0], N['Material Output'].inputs['Surface']); L.new(va.outputs[0], N['Material Output'].inputs['Volume']); water.data.materials.append(m)
Z0 = 0.006
def set_level(top):   # 水の上面の高さ（m）。円柱を高さ方向に伸ばし、上の縁の半径をグラスに合わせる
    vs = water.data.vertices
    for v in vs:
        if v.co.z > 0.5:
            r = water_radius(top); ang = math.atan2(v.co.y, v.co.x); v.co = Vector((r * math.cos(ang), r * math.sin(ang), top))
        else:
            r = water_radius(Z0); ang = math.atan2(v.co.y, v.co.x); v.co = Vector((r * math.cos(ang), r * math.sin(ang), Z0))
    water.data.update()
# 頂点の上下を覚えておく（set_level のあとも区別できるように、最初の高さで印を付ける）
TOPS = [v.index for v in water.data.vertices if v.co.z > 0.5]
def set_level2(top):
    for v in water.data.vertices:
        z = top if v.index in TOPS_SET else Z0
        r = water_radius(z); ang = math.atan2(v.co.y, v.co.x); v.co = Vector((r * math.cos(ang), r * math.sin(ang), z))
    water.data.update()
TOPS_SET = set(TOPS)

# ストロー（紙・白。グラスの中で斜めに。直径 6mm・長さ 0.21）
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.003, depth=0.21, end_fill_type='NOTHING'); straw = bpy.context.object
straw.modifiers.new('t', 'SOLIDIFY').thickness = 0.0004; bpy.ops.object.shade_smooth()
straw.rotation_euler = (math.radians(-8), math.radians(18), 0); straw.location = (0.0121, 0.0046, 0.106)   # v10：底は左寄り・上は右の縁へ。軸から離して、水面で横にずれて見えるように
m, N, L = mat('straw'); sb = N['Principled BSDF']; sb.inputs['Base Color'].default_value = (0.86, 0.84, 0.80, 1); sb.inputs['Roughness'].default_value = 0.75
straw.data.materials.append(m)

# 光：左の窓（大きい面光源・やや暖かい）＋右の弱い返し
def area(name, loc, rot, size, energy, color):
    l = bpy.data.lights.new(name, 'AREA'); l.size = size; l.energy = energy; l.color = color
    o = bpy.data.objects.new(name, l); sc.collection.objects.link(o); o.location = loc; o.rotation_euler = rot; return o
win = area('window', (-0.9, 0.3, 0.6), (math.radians(0), math.radians(-65), math.radians(10)), 1.2, 160, (1.0, 0.93, 0.84))
win.visible_glossy = False   # v8：窓の白い四角がガラスに鏡のように映らないように
rim = area('rim', (-0.35, 0.25, 0.12), (math.radians(90), 0, math.radians(-55)), 0.04, 6, (1.0, 0.97, 0.92)); rim.data.shape = 'RECTANGLE'; rim.data.size_y = 0.5   # 縁に細い光の線だけ
# v10：白い板の光（左右の横と、カメラの斜め後ろ）。ガラスの縁に縦の白い線を入れ、縁を明るく見せる
def panel(name, loc, size, size_y, energy):
    o = area(name, loc, (0, 0, 0), size, energy, (1.0, 0.99, 0.97)); o.data.shape = 'RECTANGLE'; o.data.size_y = size_y
    o.rotation_euler = (Vector((0, 0, 0.08)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); o.visible_camera = False; return o
panel('panelL', (-0.42, -0.02, 0.12), 0.05, 0.6, 7)
panel('panelR', (0.42, -0.02, 0.12), 0.05, 0.6, 7)
panel('panelBack', (0.45, -0.95, 0.35), 0.9, 0.9, 10)
area('fill', (0.8, -0.6, 0.4), (math.radians(60), math.radians(40), math.radians(40)), 0.8, 25, (0.85, 0.9, 1.0))
area('back', (0.2, 0.9, 0.5), (math.radians(-70), 0, math.radians(180)), 0.6, 30, (1.0, 0.95, 0.9))

# カメラ：グラスの高さの少し上から、やや見下ろす。被写界深度で奥をぼかす
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 65; cam.data.sensor_fit = 'VERTICAL'
cam.location = (0.0, -0.72, 0.105); tgt = Vector((0.0, 0.0, 0.08)); cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
# ↑ 11/25 v5：水面の高さから横に見る（水面が線で見える）。v2：近すぎて水面と机が見えなかったので引いた
cam.data.dof.use_dof = True; cam.data.dof.focus_distance = (tgt - cam.location).length; cam.data.dof.aperture_fstop = 5.6   # v7：奥の壁と机の模様が水ごしに見えるように絞った
cam.data.shift_y = 0.0

# 水位：0秒＝満タン（口から1.2cm下）→ 4秒＝口から8cm下。飲む速さは一定（ストローで吸う）
FULL, LOW, FPS = H - 0.012, H - 0.080, 30
def level(t): return FULL + (LOW - FULL) * max(0.0, min(1.0, t / 4.0))

PFX = 'c'
if A.wb:
    sys.path.insert(0, os.path.dirname(ROOT)); import kit_workbench
    kit_workbench.setup(sc, A.wb, wire_th=0.0004, dim_mats=('glass',), dim=0.10, xray=0.5 if A.wb == 'solid' else 0.0)
    PFX = A.wb[0]
    if A.outdir == os.path.join(ROOT, 'frames_cup'): A.outdir = os.path.join(ROOT, 'frames_cup_wb')
if A.anim:
    os.makedirs(A.outdir, exist_ok=True)
    for f in range(A.fs, A.fe + 1, A.step):
        fp = os.path.join(A.outdir, f'{PFX}_{f:04d}.png')
        if os.path.exists(fp): continue
        set_level2(level(f / FPS)); sc.render.filepath = fp
        bpy.ops.render.render(write_still=True); print('FRAME', f, flush=True)
else:
    set_level2(level(A.t)); os.makedirs(os.path.dirname(A.out), exist_ok=True); sc.render.filepath = A.out
    bpy.ops.render.render(write_still=True); print('WROTE', A.out)
