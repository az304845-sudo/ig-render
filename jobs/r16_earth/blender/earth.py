# R16 宇宙から見た地球と、海面を下げていく海（11/25 動画作成・Blender 5.3・Cycles）。
# 地図の絵：NASA Blue Marble NG 2004年7月（dl/bluemarble）。高さ：NOAA ETOPO 2022 0.1度（data/elev16.png＝(z+11000)/20000 を16bitで）。
# 海の色は「元の高さ < 海面」の所だけ水にする。海面 SEA（m・0＝今・−3700＝平均の深さまで）を下げると、浅い所から海底が出る。
# 出た海底は Blue Marble の海の色（暗い青）を使わず、深さで色を決めた岩と砂の色＋高さの陰影。光る物（発光・ネオン）は使わない。
# 使い方：blender -b -P earth.py -- --sea -50 --view pacific --out ../preview/earth_test.png [--samples 48] [--res 50]
import bpy, math, sys, os, argparse
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
ap.add_argument('--sea', type=float, default=0.0); ap.add_argument('--view', default='pacific')
ap.add_argument('--out', default=os.path.join(ROOT, 'preview', 'earth_test.png'))
ap.add_argument('--samples', type=int, default=48); ap.add_argument('--res', type=int, default=50)
ap.add_argument('--engine', default='cycles')
ap.add_argument('--no-atm', action='store_true')   # 時間の切り分け用
ap.add_argument('--atm', default='surf')
ap.add_argument('--anim', action='store_true'); ap.add_argument('--step', type=int, default=1); ap.add_argument('--fs', type=int, default=120); ap.add_argument('--fe', type=int, default=990)
ap.add_argument('--outdir', default=os.path.join(ROOT, 'frames_earth')); ap.add_argument('--t', type=float, default=None)   # --t：動画の秒の1コマだけ描く
ap.add_argument('--view-sun', action='store_true')   # 静止画で、太陽を見る所に合わせる（v10 までの試し描きと同じ）   # surf：表面の膜（速い・11/25 本番用）／ vol：体積の散乱（1枚5分かかる）   # cycles / eevee（11/25 描き出しの時間を比べる）
A = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])

VIEWS = {   # 見る所（緯度・経度）・距離（地球の半径の何倍）・画面の中で地球を下へずらす量
    'pacific': dict(lat=30, lon=160, dist=3.4, shift=0.10),
    'japan':   dict(lat=36, lon=138, dist=1.9, shift=0.0),
    'bering':  dict(lat=63, lon=-170, dist=1.7, shift=0.0),
}
V = VIEWS[A.view]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
if A.engine == 'eevee':
    sc.render.engine = 'BLENDER_EEVEE'; sc.eevee.taa_render_samples = A.samples
    try: sc.eevee.use_raytracing = True
    except Exception: pass
    try: sc.eevee.volumetric_tile_size = '2'; sc.eevee.volumetric_samples = 128
    except Exception: pass
else:
    sc.render.engine = 'CYCLES'; sc.cycles.samples = A.samples; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1080, 1920, A.res
sc.render.threads_mode = 'FIXED'; sc.render.threads = 4
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Base Contrast'
w = bpy.data.worlds.new('space'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)

# 地球（半径1）
bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, radius=1.0)
earth = bpy.context.object; earth.name = 'earth'; bpy.ops.object.shade_smooth()
m = bpy.data.materials.new('earth'); m.use_nodes = True; earth.data.materials.append(m)
nt = m.node_tree; N = nt.nodes; Lk = nt.links; N.clear()
def node(t, x, y, **kw):
    n = N.new(t); n.location = (x, y)
    for k, v in kw.items(): setattr(n, k, v)
    return n
def math_(op, x, y, a=None, b=None):
    n = node('ShaderNodeMath', x, y, operation=op)
    if a is not None and not hasattr(a, 'bl_idname'): n.inputs[0].default_value = a
    if b is not None and not hasattr(b, 'bl_idname'): n.inputs[1].default_value = b
    return n
tc = node('ShaderNodeTexCoord', -1600, 0); sep = node('ShaderNodeSeparateXYZ', -1400, 0); Lk.new(tc.outputs['Object'], sep.inputs[0])
lon = math_('ARCTAN2', -1200, 100); Lk.new(sep.outputs['Y'], lon.inputs[0]); Lk.new(sep.outputs['X'], lon.inputs[1])
ln = node('ShaderNodeVectorMath', -1400, -200, operation='LENGTH'); Lk.new(tc.outputs['Object'], ln.inputs[0])
zr = math_('DIVIDE', -1200, -100); Lk.new(sep.outputs['Z'], zr.inputs[0]); Lk.new(ln.outputs['Value'], zr.inputs[1])
lat = math_('ARCSINE', -1000, -100); Lk.new(zr.outputs[0], lat.inputs[0])
u1 = math_('ADD', -1000, 100, b=math.pi); Lk.new(lon.outputs[0], u1.inputs[0]); u = math_('DIVIDE', -800, 100, b=2 * math.pi); Lk.new(u1.outputs[0], u.inputs[0])
v1 = math_('ADD', -800, -100, b=math.pi / 2); Lk.new(lat.outputs[0], v1.inputs[0]); v = math_('DIVIDE', -600, -100, b=math.pi); Lk.new(v1.outputs[0], v.inputs[0])
uv = node('ShaderNodeCombineXYZ', -400, 0); Lk.new(u.outputs[0], uv.inputs[0]); Lk.new(v.outputs[0], uv.inputs[1])
img_c = node('ShaderNodeTexImage', -200, 300, interpolation='Cubic'); img_c.image = bpy.data.images.load(os.path.join(ROOT, 'dl/bluemarble/world.200407.3x5400x2700.jpg'))
img_e = node('ShaderNodeTexImage', -200, -200, interpolation='Cubic'); img_e.image = bpy.data.images.load(os.path.join(ROOT, 'data/elev16.png')); img_e.image.colorspace_settings.name = 'Non-Color'
img_c.extension = img_e.extension = 'EXTEND'
Lk.new(uv.outputs[0], img_c.inputs[0]); Lk.new(uv.outputs[0], img_e.inputs[0])
elev = math_('MULTIPLY_ADD', 0, -200); elev.inputs[1].default_value = 20000; elev.inputs[2].default_value = -11000; Lk.new(img_e.outputs['Color'], elev.inputs[0])   # m
# 水の所：深さ d = SEA − elev（>0 が水）
SEA = node('ShaderNodeValue', 0, -600); SEA.name = 'SEA'; SEA.outputs[0].default_value = A.sea   # 海面（m）。動画では毎コマ書き換える
sab = math_('ABSOLUTE', 100, -650); Lk.new(SEA.outputs[0], sab.inputs[0])
def from_abs(k, lo, x, y):   # max(lo, k·|SEA|)
    a = math_('MULTIPLY', x, y, b=k); Lk.new(sab.outputs[0], a.inputs[0]); m_ = math_('MAXIMUM', x + 100, y, b=lo); Lk.new(a.outputs[0], m_.inputs[0]); return m_
d = math_('SUBTRACT', 200, -200); Lk.new(SEA.outputs[0], d.inputs[0]); Lk.new(elev.outputs[0], d.inputs[1])
wet = math_('GREATER_THAN', 400, -100, b=0.0); Lk.new(d.outputs[0], wet.inputs[0])
seabed = math_('LESS_THAN', 400, -300, b=0.0); Lk.new(elev.outputs[0], seabed.inputs[0])     # もとは海底
# 水の色：浅い（〜60m）＝青緑 → 深い（4000m）＝紺
dnk = math_('MULTIPLY_ADD', 200, -700); dnk.inputs[1].default_value = -1.4; dnk.inputs[2].default_value = 4000.0; Lk.new(sab.outputs[0], dnk.inputs[0])
DN = math_('MAXIMUM', 300, -700, b=1200.0); Lk.new(dnk.outputs[0], DN.inputs[0])     # 11/25 v9：海面を大きく下げたとき、残った海（日本海など）が明るい灰青になり氷に見えた→浅くても紺に寄せる
dn = math_('DIVIDE', 400, -500); Lk.new(d.outputs[0], dn.inputs[0]); Lk.new(DN.outputs[0], dn.inputs[1]); dn.use_clamp = True
dsq = math_('POWER', 600, -500, b=0.35); Lk.new(dn.outputs[0], dsq.inputs[0])
wr = node('ShaderNodeValToRGB', 800, -500); Lk.new(dsq.outputs[0], wr.inputs[0])
wr.color_ramp.elements[0].color = (0.035, 0.15, 0.20, 1); wr.color_ramp.elements[1].color = (0.004, 0.018, 0.06, 1)
# 出た海底の色：浅い棚＝砂（明るい灰茶）→ 深い平原＝暗い灰
en = math_('DIVIDE', 400, -800, b=-6000.0); Lk.new(elev.outputs[0], en.inputs[0]); en.use_clamp = True
sr = node('ShaderNodeValToRGB', 800, -800); Lk.new(en.outputs[0], sr.inputs[0])
# 11/25 運用の検品：灰〜焦げ茶の泥と岩・海の際ほど暗く濡れた色・水際に細い濡れた線・起伏の陰影を強く
sr.color_ramp.elements[0].color = (0.075, 0.058, 0.040, 1); sr.color_ramp.elements[1].color = (0.050, 0.046, 0.042, 1)   # 11/25 本番：干上がった深い底が黒く焦げて見えたので少し明るく
e3 = sr.color_ramp.elements.new(0.25); e3.color = (0.048, 0.042, 0.035, 1)
nz = node('ShaderNodeTexNoise', 400, -1100); nz.inputs['Scale'].default_value = 160.0; nz.inputs['Detail'].default_value = 12.0; nz.inputs['Roughness'].default_value = 0.62
Lk.new(tc.outputs['Object'], nz.inputs['Vector'])
nz2 = node('ShaderNodeTexNoise', 400, -1300); nz2.inputs['Scale'].default_value = 900.0; nz2.inputs['Detail'].default_value = 6.0
Lk.new(tc.outputs['Object'], nz2.inputs['Vector'])
mott = node('ShaderNodeMix', 1000, -900, data_type='RGBA', blend_type='OVERLAY'); mott.inputs['Factor'].default_value = 0.55
Lk.new(sr.outputs['Color'], mott.inputs['A']); Lk.new(nz.outputs['Fac'], mott.inputs['B'])   # 灰色の模様（色つきの Color は桃色に寄るので使わない）
mott2 = node('ShaderNodeMix', 1150, -900, data_type='RGBA', blend_type='OVERLAY'); mott2.inputs['Factor'].default_value = 0.35
Lk.new(mott.outputs['Result'], mott2.inputs['A']); Lk.new(nz2.outputs['Fac'], mott2.inputs['B'])
# 今の水際からの高さ e = elev − SEA（>0 が出た所）。濡れ：水際から W m までを暗く。濡れた線：水際から WL m までを明るく・つやを出す
W = from_abs(0.35, 8.0, 500, -1800); WL = from_abs(0.015, 0.6, 500, -1900)   # 11/25 v6：線が太く霜のように見えたので細く
e = math_('SUBTRACT', 600, -1500); Lk.new(elev.outputs[0], e.inputs[0]); Lk.new(SEA.outputs[0], e.inputs[1])
wetf = math_('DIVIDE', 800, -1500); Lk.new(e.outputs[0], wetf.inputs[0]); Lk.new(W.outputs[0], wetf.inputs[1]); wetf.use_clamp = True
wet_dark = math_('MULTIPLY_ADD', 1000, -1500); wet_dark.inputs[1].default_value = 0.65; wet_dark.inputs[2].default_value = 0.35; Lk.new(wetf.outputs[0], wet_dark.inputs[0])   # 0.5（際）→1.0（乾いた所）
bedc = node('ShaderNodeMix', 1300, -900, data_type='RGBA', blend_type='MULTIPLY'); bedc.inputs['Factor'].default_value = 1.0
Lk.new(mott2.outputs['Result'], bedc.inputs['A']); cw = node('ShaderNodeCombineColor', 1150, -1500)
for k in range(3): Lk.new(wet_dark.outputs[0], cw.inputs[k])
Lk.new(cw.outputs[0], bedc.inputs['B'])
# 焼いた陰影（prep_hill.py・0.5＝平ら）を出た海底の色に掛ける：平ら1.0・陰0.2・日なた1.2（11/25 v5：橋の陰を強く）
img_h = node('ShaderNodeTexImage', -200, -1900, interpolation='Cubic'); img_h.image = bpy.data.images.load(os.path.join(ROOT, 'data/hill.png')); img_h.image.colorspace_settings.name = 'Non-Color'
img_h.extension = 'EXTEND'; Lk.new(uv.outputs[0], img_h.inputs[0])
hk = math_('MULTIPLY_ADD', 1200, -1900); hk.inputs[1].default_value = 3.0; hk.inputs[2].default_value = -0.5; Lk.new(img_h.outputs['Color'], hk.inputs[0])
hc = node('ShaderNodeCombineColor', 1300, -1900)
for k in range(3): Lk.new(hk.outputs[0], hc.inputs[k])
bedh = node('ShaderNodeMix', 1380, -1100, data_type='RGBA', blend_type='MULTIPLY'); bedh.inputs['Factor'].default_value = 1.0
Lk.new(bedc.outputs['Result'], bedh.inputs['A']); Lk.new(hc.outputs[0], bedh.inputs['B'])
linef = math_('LESS_THAN', 800, -1700); Lk.new(e.outputs[0], linef.inputs[0]); Lk.new(WL.outputs[0], linef.inputs[1])
online = math_('MULTIPLY', 1000, -1700); Lk.new(linef.outputs[0], online.inputs[0]); Lk.new(seabed.outputs[0], online.inputs[1])
bedl = node('ShaderNodeMix', 1450, -900, data_type='RGBA'); bedl.inputs["B"].default_value = (0.17, 0.16, 0.15, 1)
Lk.new(online.outputs[0], bedl.inputs['Factor']); Lk.new(bedh.outputs['Result'], bedl.inputs['A'])
land_or_bed = node('ShaderNodeMix', 1100, 200, data_type='RGBA'); Lk.new(seabed.outputs[0], land_or_bed.inputs['Factor'])
Lk.new(img_c.outputs['Color'], land_or_bed.inputs['A']); Lk.new(bedl.outputs['Result'], land_or_bed.inputs['B'])
col = node('ShaderNodeMix', 1300, 0, data_type='RGBA'); Lk.new(wet.outputs[0], col.inputs['Factor'])
Lk.new(land_or_bed.outputs['Result'], col.inputs['A']); Lk.new(wr.outputs['Color'], col.inputs['B'])
# 起伏の陰影（水の下は平ら）
dry = math_('SUBTRACT', 1100, -300, a=1.0); Lk.new(wet.outputs[0], dry.inputs[1])
bedk = math_('MULTIPLY_ADD', 1100, -450); bedk.inputs[1].default_value = 5.0; bedk.inputs[2].default_value = 1.0; Lk.new(seabed.outputs[0], bedk.inputs[0])   # 出た海底は高さ5倍
hg0 = math_('MULTIPLY', 1250, -400); Lk.new(elev.outputs[0], hg0.inputs[0]); Lk.new(bedk.outputs[0], hg0.inputs[1])
hgn = math_('MULTIPLY_ADD', 1250, -550); hgn.inputs[1].default_value = 40.0; hgn.inputs[2].default_value = 0.0; Lk.new(nz2.outputs['Fac'], hgn.inputs[0])   # 細かい岩肌
hg1 = math_('ADD', 1350, -450); Lk.new(hg0.outputs[0], hg1.inputs[0]); Lk.new(hgn.outputs[0], hg1.inputs[1])
hgt = math_('MULTIPLY', 1450, -300); Lk.new(hg1.outputs[0], hgt.inputs[0]); Lk.new(dry.outputs[0], hgt.inputs[1])
bump = node('ShaderNodeBump', 1600, -300); bump.inputs['Strength'].default_value = 0.85; bump.inputs['Distance'].default_value = 0.00003
Lk.new(hgt.outputs[0], bump.inputs['Height'])
bsdf = node('ShaderNodeBsdfPrincipled', 1700, 0); Lk.new(col.outputs['Result'], bsdf.inputs['Base Color']); Lk.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
rough = node('ShaderNodeMix', 1500, 100, data_type='FLOAT'); rough.inputs['A'].default_value = 0.85; rough.inputs['B'].default_value = 0.4
# 11/25 v10 運用：残った海（日本海・オホーツク）が太陽の映り込みで白銀に光り、氷に見えた（映り込み0で周りと同じ紺になるのを確かめた）
# → 映り込み：水 0・陸 0.3・水際の濡れた線 0.8
spw = math_('MULTIPLY_ADD', 1450, 300); spw.inputs[1].default_value = 0.5; spw.inputs[2].default_value = 0.3; Lk.new(online.outputs[0], spw.inputs[0])   # 線 0.8・陸 0.3
spl = math_('MULTIPLY', 1600, 250); Lk.new(spw.outputs[0], spl.inputs[0]); Lk.new(dry.outputs[0], spl.inputs[1])   # 水の中は 0（online は水の中でも 1 になるので dry で消す）
Lk.new(spl.outputs[0], bsdf.inputs['Specular IOR Level'])
wl = math_('MAXIMUM', 1450, 150); Lk.new(wet.outputs[0], wl.inputs[0]); Lk.new(online.outputs[0], wl.inputs[1])
Lk.new(wl.outputs[0], rough.inputs['Factor']); Lk.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
out = node('ShaderNodeOutputMaterial', 1950, 0); Lk.new(bsdf.outputs[0], out.inputs['Surface'])

# 大気の薄い層（散乱の体積。発光は使わない）
bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.018); atm = bpy.context.object; atm.name = 'atmosphere'; bpy.ops.object.shade_smooth()
ma = bpy.data.materials.new('atm'); ma.use_nodes = True; atm.data.materials.append(ma); an = ma.node_tree.nodes; an.clear()
if A.atm == 'vol':
    vs = an.new('ShaderNodeVolumeScatter'); vs.inputs['Color'].default_value = (0.35, 0.55, 1.0, 1); vs.inputs['Density'].default_value = 6.0
    ao = an.new('ShaderNodeOutputMaterial'); ma.node_tree.links.new(vs.outputs[0], ao.inputs['Volume'])
else:
    # 表面の膜：縁ほど濃い青の拡散（日の当たる側だけ見える）。発光は使わない。円盤全体にも薄いもや
    AL = ma.node_tree.links
    lw = an.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = 0.5
    p1 = an.new('ShaderNodeMath'); p1.operation = 'POWER'; p1.inputs[1].default_value = 4.0; AL.new(lw.outputs['Facing'], p1.inputs[0])
    f1 = an.new('ShaderNodeMath'); f1.operation = 'MULTIPLY_ADD'; f1.inputs[1].default_value = 0.75; f1.inputs[2].default_value = 0.025; f1.use_clamp = True; AL.new(p1.outputs[0], f1.inputs[0])
    tr = an.new('ShaderNodeBsdfTransparent')
    df = an.new('ShaderNodeBsdfDiffuse'); df.inputs['Color'].default_value = (0.30, 0.50, 1.0, 1)
    mx = an.new('ShaderNodeMixShader'); AL.new(f1.outputs[0], mx.inputs[0]); AL.new(tr.outputs[0], mx.inputs[1]); AL.new(df.outputs[0], mx.inputs[2])
    ao = an.new('ShaderNodeOutputMaterial'); AL.new(mx.outputs[0], ao.inputs['Surface'])
    atm.visible_shadow = False
if A.no_atm: bpy.data.objects.remove(atm)

# 太陽（左上の奥から）
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 4.5; sun.data.angle = math.radians(0.53)
# カメラ：見る所の真上（距離 dist）から地心を見る
def dir_ll(la, lo):
    la, lo = math.radians(la), math.radians(lo); return Vector((math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)))
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 35; cam.data.sensor_fit = 'VERTICAL'
def set_view(lat, lon, dist, shift):
    p = dir_ll(lat, lon) * dist
    cam.location = p; cam.rotation_euler = (-p).to_track_quat('-Z', 'Y').to_euler(); cam.data.shift_y = shift
def set_sun(lat, lon):
    s_dir = dir_ll(lat, lon).normalized(); sun.rotation_euler = (-s_dir).to_track_quat('-Z', 'Y').to_euler()

# 動画の流れ（動画の秒・海面 m・緯度・経度・距離・画面のずらし）。11/25 動画作成：台本 L01〜L11（4.0〜33.0秒）
# 経度は回り込みが無いよう続けた数で書く（−178 → 182）。海面 'log' は深さを対数で進める（浅い段を長めに見せる）
KEYS = [
    (4.0,    0.0,     36, 138, 1.9, 0.00),   # L01 じゃあ、82億人で… 日本の近くから
    (16.0,   0.0,     30, 160, 3.4, 0.10),   # L02〜L05 引いて太平洋ごと
    (19.3,  -0.000017, 30, 160, 3.4, 0.10),   # L06 1年で 0.017ミリ（m で書く。見た目は変わらない）
    (21.4,  -1.7,     52, 182, 2.4, 0.04),   # L07 10万年で背の高さ。ベーリングへ向かう
    (22.4,  -1.7,     63, 190, 1.7, 0.00),   # L08 300万年…ベーリング
    (24.2,  -50.0,    63, 190, 1.7, 0.00),   #   陸の橋が出る
    (24.8,  -50.0,    63, 190, 1.7, 0.00),
    (27.8,  -11000.0, 30, 160, 3.4, 0.10),   # L09 2億2000万年で干上がる（＋1秒の間）'log'
    (28.15, -11000.0, 30, 160, 3.4, 0.10),
    (28.75,  0.0,     30, 160, 3.4, 0.10),   # L10 のはずが満タンのまま（一気に戻る）
    (33.0,   0.0,     30, 160, 3.4, 0.10),   # L11 また海へ戻る（28.8秒からは still_2x の拡大で見せる。11/25：静止画と向きをそろえた）
]
LOG_SEG = {7}   # KEYS[6]→KEYS[7] の区間
def ease(u): return u * u * (3 - 2 * u)
def state(t):
    if t <= KEYS[0][0]: return KEYS[0][1:]
    for k in range(1, len(KEYS)):
        a, b = KEYS[k - 1], KEYS[k]
        if t <= b[0]:
            u = ease((t - a[0]) / (b[0] - a[0]))
            v = [a[j] + (b[j] - a[j]) * u for j in range(1, 6)]
            if k in LOG_SEG:
                v[0] = -math.exp(math.log(-a[1]) + (math.log(-b[1]) - math.log(-a[1])) * u)
            return tuple(v)
    return KEYS[-1][1:]
FPS = 30
def apply(t):
    sea, lat, lon, dist, shift = state(t)
    nt.nodes['SEA'].outputs[0].default_value = sea
    set_view(lat, lon, dist, shift)
    return sea
set_sun(50, 80)   # 太陽は地球に対して動かさない（太平洋の画の左上の奥）

if A.anim:
    os.makedirs(A.outdir, exist_ok=True)
    for f in range(A.fs, A.fe + 1, A.step):
        fp = os.path.join(A.outdir, f'e_{f:04d}.png')
        if os.path.exists(fp): continue
        sea = apply(f / FPS); sc.render.filepath = fp
        bpy.ops.render.render(write_still=True); print('FRAME', f, 'sea', round(sea, 3), flush=True)
else:
    if A.t is not None: sea = apply(A.t)
    else:
        set_view(V['lat'], V['lon'], V['dist'], V['shift'])
        set_sun(V['lat'] + 20, V['lon'] - 80) if A.view_sun else None
    os.makedirs(os.path.dirname(A.out), exist_ok=True); sc.render.filepath = A.out
    bpy.ops.render.render(write_still=True); print('WROTE', A.out, 'sea', nt.nodes['SEA'].outputs[0].default_value, 'view', A.view)
