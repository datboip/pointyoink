#!/usr/bin/env python3
# PointYoink - pull 3D scans off a Revopoint MIRACO over USB (Linux).
# MIT licensed. See LICENSE.
# Unofficial. Not affiliated with or endorsed by Revopoint.
# "Revopoint" and "MIRACO" are trademarks of their respective owners.
import os, re, json, time, glob, shutil, threading, subprocess, queue
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

APP = "PointYoink"; VERSION = "0.7.0"
GITHUB = "https://github.com/datboip/pointyoink"
HOME = os.path.expanduser("~")
MOUNT = os.path.join(HOME, "revopoint-mtp")
PROJECTS = os.path.join(MOUNT, "Internal shared storage", "Projects")
SCREENSHOTS = os.path.join(MOUNT, "Internal shared storage", "Screenshots")
THUMBS = "/tmp/pointyoink-thumbs"
CFG_DIR = os.path.join(HOME, ".config", "pointyoink"); CFG = os.path.join(CFG_DIR, "config.json")
HERE = os.path.dirname(os.path.abspath(__file__)); ICON = os.path.join(HERE, "icon.png")
DEFAULT_DEST = os.path.join(HOME, "revopoint-scans-models")
VID = "2207"
for d in (THUMBS, CFG_DIR): os.makedirs(d, exist_ok=True)

# palette
BG="#0e1117"; CARD="#171b23"; CARD2="#1d222c"; STROKE="#2a3140"; SELB="#22304a"
AC="#4aa3ff"; AC_H="#3b8fe6"; OK="#3ecf8e"; WARN="#ffb454"; DANGER="#ff6b6b"
TX="#eef1f5"; MUT="#98a2b3"

CHANGELOG = """0.7.0
  - Remove base: an interactive cut-plane tool to slice the table/turntable off
    a scan (keeps a cleaned copy). Plus optional mesh cleanup on import.
  - Captures tab: browse and pull the scanner's screenshots AND screen
    recordings, in their own place instead of the project list.
  - A Tools row groups View in 3D and Remove base.
  - A bottom status bar shows activity so the app never feels frozen.
  - Heavy mesh work runs in a memory-capped process so it can't crash your PC.
  - "Imported" now requires a real model file; partial export/zip failures are
    reported instead of silently passing; safer device mount cleanup.

0.6.2
  - "Imported" now reflects what is actually on disk - the badge clears if you
    delete the files, and updates live.
  - Project cards rebalanced so the size no longer gets cut off.

0.6.1
  - Export ZIP now shows an estimated size next to each option, so you can pick
    one that fits (e.g. under an upload limit) before zipping.

0.6.0
  - Cleaner file layout: imports land flat with clear unique names
    (Project_<scan>.ply / .stl / .png), not buried in nested folders.
  - Export ZIP now asks what to include (STL / OBJ / GLB / all models /
    everything) and packs files flat, so unzipping is ready to use. It can
    make STLs on the fly even if you did not export them at import.

0.5.2
  - Fix the square outline around the "View in 3D" button.

0.5.1
  - 3D viewer opens already-drawn (no black flash while it loads).
  - Preview image scales to fit the window at any size.
  - Project cards on three lines so nothing is cut off.
  - Exported STL/OBJ/GLB are named per project + scan, so they stay unique
    when you gather them in one folder.

0.5.0
  - View in 3D: open a scan's mesh in an interactive window (drag to rotate,
    scroll to zoom). Works straight from the device or a local copy.

0.4.0
  - Export ZIP button: bundle the selected project(s) into a .zip in your save
    folder (raw frames skipped), for archiving or moving to another machine.

0.3.2
  - Fix a crash that stopped the project list from showing whenever the
    scanner had projects on it (an undefined name in the list renderer).
  - HiDPI: read the GNOME desktop scale (and POINTYOINK_SCALE) so the window
    is sized correctly on scaled displays.

0.3.1
  - Fix tiny window on HiDPI laptops (auto-detect display scale) and add a
    UI scale setting.
  - Smarter re-import: detects when a project changed on the device.
  - Themed dialogs, animated conversion progress.

0.3.0
  - Rounded UI built on CustomTkinter, app icon, splash screen, cleaner spacing.
  - Auto-connects when the scanner is in File Transfer mode.
  - Optional STL / OBJ export of the meshes on import.
  - Rename a project (keeps the original ID as reference) and remember
    what's already been imported across sessions.
  - Bigger About with supported devices and an inline changelog.
  - Preview/Files tabs, per-project size, import summary.
  - Settings, Cancel and Retry, built-in error log, MIT licensed.

0.2.0
  - Project list with thumbnails and the scanner's own scan renders.
  - Models-only vs full import, imported badges, destination picker.

0.1.0
  - First working build: mount the MIRACO over MTP, pick projects, pull them.
  - Models-only skips the raw depth frames for a big speed-up."""

HELP = """POINTYOINK - HELP

WHAT IT DOES
PointYoink copies your finished 3D scans off a Revopoint MIRACO / MIRACO Pro
onto Linux, over the USB cable. No Windows, no Revo Scan, no cloud account.

HOW TO USE
1. Plug the scanner into this PC with the USB-C cable.
2. On the MIRACO screen tap  "File Transfer"  (Share to PC -> USB Cable).
3. Click  Connect. Your projects appear on the left.
4. Tick the projects you want; click one to preview its scans.
5. Pick a "Save to" folder and click  Import selected.

MODELS ONLY vs FULL
- "Models only" (default) copies just the finished meshes + point clouds
  (.ply) and skips the thousands of raw depth frames. This is ~1000x faster
  (~19 MB/s vs ~20 KB/s).
- Turn it OFF only if you want the raw frames to re-process a scan later in
  Revo Scan on another machine.

WHAT YOU GET
- fuse_mesh.ply = the finished 3D MESH (with faces) - what you print/render.
- fuse.ply      = the fused POINT CLOUD (points only).
Both are standard .ply - open them in Blender, MeshLab, or CloudCompare.
The "Files" tab lists every model file and its size before you import.

TROUBLESHOOTING
- "Not connected" won't go away: make sure you tapped FILE TRANSFER on the
  scanner (not just plugged it in). The scanner shows a USB mode popup.
- Connect fails / hangs: unplug and replug the cable, re-tap File Transfer,
  then Connect again. PointYoink clears stale connections automatically.
- Previews blank: the scanner is still waking up - click the project again.
- Import slow with "Models only" OFF: that's the raw frames; expected.

PRIVACY & LEGAL
Everything happens locally over USB - nothing is uploaded anywhere.
PointYoink is UNOFFICIAL and not affiliated with or endorsed by Revopoint.
It only reads files off your own device.

fuse_mesh.ply = finished mesh (faces).   fuse.ply = point cloud (points)."""

import traceback as _tb, datetime as _dt
LOGFILE = os.path.join(CFG_DIR, "pointyoink.log")

def log_line(msg):
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOGFILE, "a") as f:
            f.write("[%s] %s\n" % (stamp, msg))
    except Exception:
        pass

def log_error(kind, exc):
    log_line("%s: %s\n%s" % (kind, exc, "".join(_tb.format_exception(type(exc), exc, exc.__traceback__)).rstrip()))

import sys as _sys
def _excepthook(t, v, tb):
    log_line("UNCAUGHT: %s\n%s" % (v, "".join(_tb.format_exception(t, v, tb)).rstrip()))
    _sys.__excepthook__(t, v, tb)
_sys.excepthook = _excepthook

# ---------------- config ----------------
def load_cfg():
    try: return json.load(open(CFG))
    except Exception: return {}
def save_cfg(c):
    try: json.dump(c, open(CFG, "w"), indent=2)
    except Exception: pass

# ---------------- device / mount ----------------
def usb_state():
    dev = None
    for d in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        try:
            if open(d).read().strip() == VID: dev = os.path.dirname(d); break
        except Exception: pass
    if not dev: return "absent", None
    classes = []
    for f in glob.glob(dev + "/*/bInterfaceClass"):
        try: classes.append(open(f).read().strip())
        except Exception: pass
    serial = None
    try: serial = open(os.path.join(dev, "serial")).read().strip()
    except Exception: pass
    return ("mtp" if "06" in classes else "adb"), serial

def quick_mounted():
    try:
        return subprocess.run(["ls", os.path.join(MOUNT, "Internal shared storage")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6).returncode == 0
    except Exception: return False

def do_mount():
    if quick_mounted(): return True, "already mounted"
    # Clear our OWN mountpoint gracefully first (don't blanket-kill MTP for other
    # devices the user may have connected). Release any gvfs claim on the device,
    # lazily unmount our path, and only then kill a jmtpfs still holding OUR mount.
    subprocess.run(["bash","-c","gio mount -u 'mtp://*' 2>/dev/null; true"])
    subprocess.run(["fusermount","-uz",MOUNT], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill","-9","-f","jmtpfs .*%s" % os.path.basename(MOUNT)], stderr=subprocess.DEVNULL)
    if not os.path.isdir(MOUNT):
        try: os.makedirs(MOUNT, exist_ok=True)
        except FileExistsError: pass
    time.sleep(1.5)
    try: r = subprocess.run(["jmtpfs",MOUNT], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired: return False, "jmtpfs timed out -- unplug/replug & re-tap File Transfer"
    time.sleep(2)
    if quick_mounted(): return True, "mounted"
    return False, (r.stderr or r.stdout or "mount failed -- replug USB & re-tap File Transfer").strip()

def list_projects():
    out = []
    if not quick_mounted(): return out
    try: names = sorted(os.listdir(PROJECTS), reverse=True)
    except Exception: return out
    for name in names:
        pdir = os.path.join(PROJECTS, name)
        if not os.path.isdir(pdir): continue
        info = {"name": name, "meshes": None, "clouds": None, "date": None, "nodes": None, "thumb": None, "edit_time": None}
        revo = os.path.join(pdir, name + ".revo")
        if os.path.exists(revo):
            try:
                d = json.load(open(revo))
                info["meshes"]=d.get("model_mesh_count"); info["clouds"]=d.get("model_pointcloud_count")
                info["nodes"]=len(d.get("nodes", []))
                et=d.get("edit_time")
                if et:
                    info["date"]=time.strftime("%Y-%m-%d %H:%M", time.localtime(int(et)))
                    try: info["edit_time"]=int(et)
                    except Exception: info["edit_time"]=None
            except Exception: pass
        tp = os.path.join(THUMBS, name + "__thumb.png")
        if not os.path.exists(tp):
            try:
                for node in sorted(os.listdir(os.path.join(pdir,"data"))):
                    prev=os.path.join(pdir,"data",node,"preview.png")
                    if os.path.exists(prev): shutil.copyfile(prev, tp); break
            except Exception: pass
        if os.path.exists(tp): info["thumb"]=tp
        out.append(info)
    return out

def list_screenshots():
    """Device screenshots (Internal shared storage/Screenshots), newest first."""
    out=[]
    if not quick_mounted(): return out
    try:
        for f in sorted(os.listdir(SCREENSHOTS), reverse=True):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                out.append((f, os.path.join(SCREENSHOTS, f)))
    except Exception: pass
    return out

def list_recordings():
    """Screen recordings (videos) anywhere on the device except the big Projects tree."""
    out=[]; exts=(".mp4",".mkv",".webm",".mov",".avi",".m4v")
    if not quick_mounted(): return out
    root=os.path.join(MOUNT, "Internal shared storage")
    try:
        for entry in os.listdir(root):
            if entry=="Projects": continue    # skip the huge scan tree
            sub=os.path.join(root, entry)
            if os.path.isdir(sub):
                try:
                    for f in sorted(os.listdir(sub), reverse=True):
                        if f.lower().endswith(exts): out.append((f, os.path.join(sub, f)))
                except Exception: pass
            elif entry.lower().endswith(exts):
                out.append((entry, sub))
    except Exception: pass
    return out

def project_model_size(name):
    total=0; files=[]
    for ply in glob.glob(os.path.join(PROJECTS,name,"data","*","*.ply")):
        try:
            sz=os.path.getsize(ply); total+=sz
            files.append((os.path.basename(os.path.dirname(ply)), os.path.basename(ply), sz))
        except Exception: pass
    return total, files

def gather_gallery(name):
    paths=[]
    try: nodes=sorted(os.listdir(os.path.join(PROJECTS,name,"data")))
    except Exception: return paths
    for node in nodes:
        prev=os.path.join(PROJECTS,name,"data",node,"preview.png")
        lp=os.path.join(THUMBS,"%s__%s.png"%(name,node))
        if not os.path.exists(lp):
            if os.path.exists(prev):
                try: shutil.copyfile(prev, lp)
                except Exception: continue
            else: continue
        paths.append((node, lp))
    return paths

def human(n):
    for u in ("B","KB","MB","GB"):
        if n<1024: return "%.0f %s"%(n,u) if u=="B" else "%.1f %s"%(n,u)
        n/=1024
    return "%.1f TB"%n

def cimg(path, w):
    im=Image.open(path); r=w/im.width; return ctk.CTkImage(light_image=im, dark_image=im, size=(w, int(im.height*r)))

WORDMARK="Ubuntu"   # clean lowercase 'i' (the default bold font renders it like 'I')
def _has_imagetk():
    try:
        from PIL import ImageTk; return True
    except Exception: return False
def _has_trimesh():
    try:
        import trimesh; return True
    except Exception: return False

def _ply_counts(path):
    """Read vertex/face counts from a PLY header only (fast, no full load)."""
    v=f=0
    try:
        with open(path,"rb") as fh:
            for _ in range(80):
                line=fh.readline()
                if not line: break
                if line.startswith(b"element vertex"): v=int(line.split()[-1])
                elif line.startswith(b"element face"): f=int(line.split()[-1])
                elif line.strip()==b"end_header": break
    except Exception:
        pass
    return v,f

def _desktop_scale():
    """Best guess at the desktop UI scale so the app matches other windows.
    Priority: POINTYOINK_SCALE env > GNOME monitors.xml <scale> > None (caller falls back)."""
    env=os.environ.get("POINTYOINK_SCALE")
    if env:
        try:
            v=float(env)
            if 0.5<=v<=4: return v
        except Exception: pass
    try:
        import xml.etree.ElementTree as ET
        mx=os.path.expanduser("~/.config/monitors.xml")
        if os.path.exists(mx):
            scales=[float(s.text) for s in ET.parse(mx).getroot().iter("scale") if s.text]
            if scales:
                # the primary/most common scale
                return max(set(scales), key=scales.count)
    except Exception: pass
    return None

# ---------------- app ----------------
ctk.set_appearance_mode("dark"); ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = load_cfg()
        # per-project records keyed by ORIGINAL id: {label, imported_to, imported_at}
        self.records = self.cfg.get("records", {})
        # --- UI scaling: honor a saved override, else auto-detect HiDPI so it isn't tiny on laptops ---
        try:
            # priority: saved override > desktop scale (env / GNOME monitors.xml) > DPI heuristic > 1.0
            scale=self.cfg.get("ui_scale")
            if not scale:
                scale=_desktop_scale()
            if not scale:
                ppi=self.winfo_fpixels("1i") or 96.0   # note: XWayland reports a synthetic 96, so this rarely fires
                scale=max(1.0, min(2.5, round(ppi/96.0*20)/20)) if ppi>110 else 1.0
            scale=float(scale)
            if abs(scale-1.0)>0.02:
                ctk.set_widget_scaling(scale); ctk.set_window_scaling(scale)
            self._ui_scale=scale
        except Exception as e:
            self._ui_scale=1.0; log_error("ui-scale", e)
        # window size: default, but never bigger than the screen (keeps it usable on small/scaled displays)
        try:
            sw=self.winfo_screenwidth(); sh=self.winfo_screenheight()
            dw=min(1080, int(sw*0.92)); dh=min(840, int(sh*0.90))
        except Exception:
            dw,dh=1080,840
        self.title("%s  %s" % (APP, VERSION))
        self.geometry(self.cfg.get("geometry", "%dx%d"%(dw,dh)))
        self.minsize(min(940,dw), min(680,dh))
        self.configure(fg_color=BG)
        try:
            if os.path.exists(ICON):
                from PIL import ImageTk
                base=Image.open(ICON).convert("RGBA")
                self._iconimgs=[ImageTk.PhotoImage(base.resize((s,s), Image.LANCZOS)) for s in (256,128,64,48,32)]
                self.iconphoto(True, *self._iconimgs)
        except Exception as e: log_error("iconphoto", e)
        self.imgs={}             # image refs (needed by the splash, which runs first)
        self.withdraw()          # hide main window while the splash shows
        self._splash=None
        self._show_splash()

        self.q=queue.Queue(); self.pull_sel={}; self.projects=[]; self.projects_sig=None
        self.selected=None; self.gallery_cache={}; self.size_cache={}
        self.rows={}; self.serial=None
        self.pulling=False; self.cancel=False; self.listing=False; self.listed=False; self.proc=None
        self._mounting=False; self.auto_tried=False
        self.report_callback_exception = self._on_tk_error
        log_line("PointYoink %s started" % VERSION)

        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(2, weight=1)
        self._header(); self._statusbar(); self._body(); self._build_options(); self._actions(); self._bottombar()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_loop(); self.drain_loop(); self._pulse()
        self.after(9000, self._close_splash)   # safety fallback; the setup checks normally close it

    # ---- splash + animation ----
    def _pointer_monitor(self):
        """Return (x,y,w,h) of the monitor the cursor is on (multi-monitor aware)."""
        try: px,py=self.winfo_pointerx(), self.winfo_pointery()
        except Exception: px,py=0,0
        try:
            out=subprocess.run(["xrandr","--listmonitors"], capture_output=True, text=True, timeout=3).stdout
            best=None
            for m in re.finditer(r"(\d+)/\d+x(\d+)/\d+\+(\d+)\+(\d+)", out):
                w,h,x,y=map(int,m.groups())
                if best is None: best=(x,y,w,h)
                if x<=px<x+w and y<=py<y+h: return (x,y,w,h)
            if best: return best
        except Exception: pass
        return (0,0,self.winfo_screenwidth(), self.winfo_screenheight())

    def _make_splash_bg(self, w, h):
        import numpy as np
        from PIL import Image, ImageTk
        cx, cy = w/2, h*0.30
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt((xx-cx)**2 + (yy-cy)**2)
        t = np.clip(1 - d/(w*0.9), 0, 1)**1.5          # soft radial glow behind the logo
        r=(13+t*22).astype(np.uint8); g=(16+t*24).astype(np.uint8); b=(22+t*33).astype(np.uint8)
        return ImageTk.PhotoImage(Image.fromarray(np.dstack([r,g,b]), "RGB"))

    def _show_splash(self):
        try:
            W,H=480,480
            sp=ctk.CTkToplevel(self); sp.overrideredirect(True); sp.configure(fg_color=CARD)
            try: sp.wm_attributes("-type","splash")
            except Exception: pass
            mx,my,mw,mh=self._pointer_monitor()
            sp.geometry("%dx%d+%d+%d"%(W,H, mx+(mw-W)//2, my+(mh-H)//2))
            try: sp.attributes("-alpha",0.0); sp.attributes("-topmost",True)
            except Exception: pass
            # everything is drawn on ONE canvas so text/logo overlay the gradient with true transparency
            from PIL import Image, ImageTk
            cv=tk.Canvas(sp, width=W, height=H, highlightthickness=0, bd=0, bg=CARD); cv.pack(fill="both", expand=True)
            self._sp_cv=cv
            try:
                self.imgs["splashbg"]=self._make_splash_bg(W,H)
                cv.create_image(0,0, image=self.imgs["splashbg"], anchor="nw")
            except Exception as e: log_error("splashbg", e)
            cv.create_rectangle(0,0,W,3, fill=AC, outline="")                      # accent hairline
            if os.path.exists(ICON):
                try:
                    self.imgs["splash"]=ImageTk.PhotoImage(Image.open(ICON).convert("RGBA").resize((158,158), Image.LANCZOS))
                    cv.create_image(W//2, int(H*0.30), image=self.imgs["splash"], anchor="center")
                except Exception as e: log_error("splash-logo", e)
            cv.create_text(W//2, int(H*0.555), text=APP, fill=TX, font=(WORDMARK, 30, "bold"))
            cv.create_text(W//2, int(H*0.635), text="Y O I N K   Y O U R   S C A N S   O F F ,   O N   L I N U X",
                           fill=MUT, font=(WORDMARK, 8))
            px0, py, pw, ph = W//2-125, int(H*0.80), 250, 5
            cv.create_rectangle(px0, py, px0+pw, py+ph, fill="#0c0f15", outline="")
            self._sp_fill=cv.create_rectangle(px0, py, px0+1, py+ph, fill=AC, outline="")
            self._sp_px0, self._sp_pw, self._sp_py, self._sp_ph = px0, pw, py, ph
            self._sp_status=cv.create_text(W//2, int(H*0.865), text="checking your setup…", fill=MUT, font=(WORDMARK, 10))
            cv.create_text(W-22, H-20, text="v"+VERSION, fill=STROKE, font=(WORDMARK, 9), anchor="e")
            self._checklist=[
                {"pkg":"jmtpfs","fn":lambda:bool(shutil.which("jmtpfs")),"req":True,"ok":None},
                {"pkg":"rsync","fn":lambda:bool(shutil.which("rsync")),"req":True,"ok":None},
                {"pkg":"fuse","fn":lambda:bool(shutil.which("fusermount")),"req":True,"ok":None},
                {"pkg":"python3-pil.imagetk","fn":_has_imagetk,"req":True,"ok":None},
                {"pkg":"python3-trimesh","fn":_has_trimesh,"req":False,"ok":None},
                {"pkg":"xdg-utils","fn":lambda:bool(shutil.which("xdg-open")),"req":False,"ok":None},
            ]
            self._splash=sp; self._splash_a=0.0; self._missing=None
            self._splash_fade(0.12); self.after(400, lambda: self._run_checks(0))
        except Exception as e:
            log_error("splash", e); self.deiconify()
    def _splash_fade(self, d):
        sp=self._splash
        if not sp: return
        self._splash_a=max(0.0, min(1.0, self._splash_a+d))
        try: sp.attributes("-alpha", self._splash_a)
        except Exception: pass
        if 0.0 < self._splash_a < 1.0: self.after(22, lambda: self._splash_fade(d))
        elif self._splash_a<=0.0:
            try: sp.destroy()
            except Exception: pass
            self._splash=None; self.deiconify()
    def _run_checks(self, i):
        if not self._splash: return
        cv=self._sp_cv
        def setbar(frac):
            try: cv.coords(self._sp_fill, self._sp_px0, self._sp_py, self._sp_px0+int(self._sp_pw*frac), self._sp_py+self._sp_ph)
            except Exception: pass
        def setstatus(txt,col):
            try: cv.itemconfigure(self._sp_status, text=txt, fill=col)
            except Exception: pass
        if i>=len(self._checklist):
            setbar(1.0)
            req=[c for c in self._checklist if c["ok"] is False and c["req"]]
            opt=[c for c in self._checklist if c["ok"] is False and not c["req"]]
            if req:
                self._missing=req
                setstatus("missing: "+", ".join(c["pkg"] for c in req), WARN)
                self.after(1700, self._close_splash)
            else:
                setstatus("everything's here" if not opt else "ready (some optional tools missing)", OK)
                self.after(750, self._close_splash)
            return
        c=self._checklist[i]
        setstatus("checking "+c["pkg"]+" …", MUT)
        try: c["ok"]=bool(c["fn"]())
        except Exception: c["ok"]=False
        setbar((i+1)/len(self._checklist))
        self.after(300, lambda: self._run_checks(i+1))
    def _close_splash(self):
        if self._splash:
            self.deiconify()                                  # reveal the app BEHIND the still-topmost splash
            self.update_idletasks()
            self.after(140, lambda: self._splash_fade(-0.12)) # let it paint, then dissolve the splash over it
        else:
            self.deiconify()
        if getattr(self,"_missing",None):
            miss=self._missing; self._missing=None
            pkgs=" ".join(c["pkg"] for c in miss)
            self.after(500, lambda: self._alert("Missing tools",
                "Some required tools aren't installed:\n  "+", ".join(c["pkg"] for c in miss)+
                "\n\nInstall them with:\n  sudo apt install "+pkgs))
    # ---- bottom status bar ----
    def _bottombar(self):
        b=ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, height=30)
        b.grid(row=5,column=0, sticky="ew", padx=20, pady=(0,10)); b.grid_propagate(False)
        b.grid_columnconfigure(1, weight=1)
        self._spin=ctk.CTkLabel(b, text="●", text_color=OK, font=ctk.CTkFont(size=13), width=18)
        self._spin.grid(row=0,column=0, padx=(14,6))
        self._status=ctk.CTkLabel(b, text="Ready", text_color=MUT, anchor="w", font=ctk.CTkFont(size=12))
        self._status.grid(row=0,column=1, sticky="w")
        ctk.CTkLabel(b, text="%s %s"%(APP,VERSION), text_color="#5a6474",
                     font=ctk.CTkFont(size=10)).grid(row=0,column=2, padx=(0,14))
        self._status_msg=""

    def set_status(self, msg=""):
        """Set a transient bottom-bar message (pass '' to clear back to Ready/busy)."""
        self._status_msg=msg or ""

    _SPINNER=["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    def _pulse(self):
        busy = (self._mounting or self.listing or self.pulling
                or getattr(self,"_basing",False) or getattr(self,"_loader",None) is not None)
        self._pt=getattr(self,"_pt",0)+1
        try:
            if busy:
                self.dot.configure(text_color=(AC if self._pt%2 else "#2b5c8a"))
                self._spin.configure(text=self._SPINNER[self._pt % len(self._SPINNER)], text_color=AC)
                msg = self._status_msg or ("Connecting to the scanner…" if self._mounting else
                      "Reading projects off the scanner…" if self.listing else
                      "Importing…" if self.pulling else "Working…")
                self._status.configure(text=msg, text_color=TX)
            else:
                self._spin.configure(text="●", text_color=OK)
                self._status.configure(text=(self._status_msg or "Ready"),
                                       text_color=(TX if self._status_msg else MUT))
        except Exception: pass
        self.after(200, self._pulse)

    # ---- header ----
    def _header(self):
        h=ctk.CTkFrame(self, fg_color="transparent"); h.grid(row=0, column=0, sticky="ew", padx=20, pady=(10,2))
        h.grid_columnconfigure(2, weight=1)
        if os.path.exists(ICON):
            try:
                self.imgs["logo"]=cimg(ICON,30)
                ctk.CTkLabel(h, image=self.imgs["logo"], text="").grid(row=0,column=0, padx=(0,10))
            except Exception: pass
        col=ctk.CTkFrame(h, fg_color="transparent"); col.grid(row=0,column=1, sticky="w")
        ctk.CTkLabel(col, text=APP, font=ctk.CTkFont(family=WORDMARK, size=18, weight="bold"), text_color=TX).pack(side="left")
        ctk.CTkLabel(col, text="v"+VERSION, font=ctk.CTkFont(size=11), text_color=MUT).pack(side="left", padx=(6,12), pady=(3,0))
        ctk.CTkLabel(col, text="yoink 3D scans off your Revopoint MIRACO over USB",
                     font=ctk.CTkFont(size=11), text_color=MUT).pack(side="left", pady=(3,0))
        btns=ctk.CTkFrame(h, fg_color="transparent"); btns.grid(row=0,column=3, sticky="e")
        for t,c in [("Settings",self.dlg_settings),("Help",self.dlg_help),("About",self.dlg_about)]:
            ctk.CTkButton(btns, text=t, width=82, height=30, corner_radius=15, fg_color=CARD2,
                          hover_color=STROKE, text_color=TX, command=c).pack(side="left", padx=4)

    # ---- status ----
    def _statusbar(self):
        s=ctk.CTkFrame(self, fg_color=CARD, corner_radius=14); s.grid(row=1,column=0, sticky="ew", padx=20, pady=6)
        s.grid_columnconfigure(1, weight=1)
        self.dot=ctk.CTkLabel(s, text="●", text_color=WARN, font=ctk.CTkFont(size=16)); self.dot.grid(row=0,column=0, padx=(16,8), pady=12)
        self.banner=ctk.CTkLabel(s, text="…", text_color=TX, anchor="w", font=ctk.CTkFont(size=13)); self.banner.grid(row=0,column=1, sticky="w")
        self.action_btn=ctk.CTkButton(s, text="Connect", width=120, height=36, corner_radius=18,
                                      fg_color=AC, hover_color=AC_H, text_color="#04121f",
                                      font=ctk.CTkFont(size=13,weight="bold"), command=self.on_mount)
        self.action_btn.grid(row=0,column=2, padx=12, pady=10)

    # ---- body: list + preview ----
    def _body(self):
        body=ctk.CTkFrame(self, fg_color="transparent"); body.grid(row=2,column=0, sticky="nsew", padx=20, pady=6)
        body.grid_columnconfigure(0, weight=0); body.grid_columnconfigure(1, weight=1); body.grid_rowconfigure(0, weight=1)

        left=ctk.CTkFrame(body, fg_color=CARD, corner_radius=14, width=360); left.grid(row=0,column=0, sticky="nsew")
        left.grid_propagate(False); left.grid_rowconfigure(1, weight=1); left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="PROJECTS", font=ctk.CTkFont(size=12,weight="bold"), text_color=MUT).grid(row=0,column=0, sticky="w", padx=16, pady=(12,0))
        ctk.CTkLabel(left, text="tick to import · click to preview", font=ctk.CTkFont(size=10), text_color=MUT).grid(row=0,column=0, sticky="e", padx=16, pady=(12,0))
        self.llist=ctk.CTkScrollableFrame(left, fg_color="transparent"); self.llist.grid(row=1,column=0, sticky="nsew", padx=8, pady=8)
        self.llist.grid_columnconfigure(0, weight=1)

        right=ctk.CTkFrame(body, fg_color="transparent"); right.grid(row=0,column=1, sticky="nsew", padx=(14,0))
        right.grid_rowconfigure(0, weight=1); right.grid_columnconfigure(0, weight=1)
        self.tabs=ctk.CTkTabview(right, fg_color=CARD, corner_radius=14, segmented_button_fg_color=CARD2,
                                 segmented_button_selected_color=AC, text_color=TX)
        self.tabs.grid(row=0,column=0, sticky="nsew")
        pv=self.tabs.add("Preview"); fl=self.tabs.add("Files")
        pv.grid_columnconfigure(0, weight=1); pv.grid_rowconfigure(0, weight=1, minsize=240)
        self.big=ctk.CTkLabel(pv, text="Select a project to preview its scans", fg_color="#0a0c10",
                              corner_radius=12, text_color=MUT); self.big.grid(row=0,column=0, sticky="nsew", padx=10, pady=10)
        self.big.bind("<Configure>", self._on_big_resize)
        self.detail=ctk.CTkLabel(pv, text="", text_color=TX, anchor="w", justify="left", font=ctk.CTkFont(size=12))
        self.detail.grid(row=1,column=0, sticky="w", padx=12); self.detail.grid_remove()
        self.renders_lbl=ctk.CTkLabel(pv, text="scan renders (click to enlarge)", text_color=MUT, font=ctk.CTkFont(size=11))
        self.renders_lbl.grid(row=2,column=0, sticky="w", padx=12, pady=(6,0)); self.renders_lbl.grid_remove()
        self.film=ctk.CTkScrollableFrame(pv, orientation="horizontal", fg_color="transparent", height=104)
        self.film.grid(row=3,column=0, sticky="ew", padx=8, pady=(0,10)); self.film.grid_remove()
        # Tools toolbar: grouped scan actions (no floating buttons -> no square-corner artifacts)
        self.tools=ctk.CTkFrame(pv, fg_color=CARD2, corner_radius=12)
        self.tools.grid(row=4,column=0, sticky="ew", padx=10, pady=(0,10)); self.tools.grid_remove()
        ctk.CTkLabel(self.tools, text="TOOLS", text_color=MUT,
                     font=ctk.CTkFont(size=10,weight="bold")).pack(side="left", padx=(14,10), pady=8)
        self.view_btn=ctk.CTkButton(self.tools, text="⟳  View in 3D", width=124, height=32, corner_radius=16,
                                    fg_color=AC, hover_color=AC_H, text_color="#04121f",
                                    font=ctk.CTkFont(size=12,weight="bold"), command=self.on_view_3d)
        self.view_btn.pack(side="left", padx=5, pady=8)
        self.base_btn=ctk.CTkButton(self.tools, text="✂  Remove base", width=136, height=32, corner_radius=16,
                                    fg_color=CARD, hover_color=STROKE, text_color=TX,
                                    font=ctk.CTkFont(size=12,weight="bold"), command=self.on_remove_base)
        self.base_btn.pack(side="left", padx=5, pady=8)
        self._tip(self.base_btn, "Interactively slice the table/turntable off the scan. Opens a cut-plane "
                                 "tool; saves a cleaned copy as <name>_clean.ply. Original is kept.")
        self.files_box=ctk.CTkTextbox(fl, fg_color="#0a0c10", text_color=TX, corner_radius=10, font=ctk.CTkFont(family="monospace", size=12))
        self.files_box.pack(fill="both", expand=True, padx=10, pady=10)

        # Captures tab: device screenshots AND screen recordings, out of the project list
        sc=self.tabs.add("Captures")
        sc.grid_columnconfigure(0, weight=1); sc.grid_rowconfigure(1, weight=1)
        sctop=ctk.CTkFrame(sc, fg_color="transparent"); sctop.grid(row=0,column=0, sticky="ew", padx=10, pady=(10,4))
        self.shots_lbl=ctk.CTkLabel(sctop, text="Screenshots & recordings on the device", text_color=MUT,
                                    font=ctk.CTkFont(size=12)); self.shots_lbl.pack(side="left")
        ctk.CTkButton(sctop, text="⤓ Pull all", width=96, height=30, corner_radius=15, fg_color=AC,
                      hover_color=AC_H, text_color="#04121f", command=self.pull_screenshots).pack(side="right", padx=4)
        ctk.CTkButton(sctop, text="↻ Refresh", width=96, height=30, corner_radius=15, fg_color=CARD2,
                      hover_color=STROKE, text_color=TX, command=self.refresh_screenshots).pack(side="right", padx=4)
        self.shots=ctk.CTkScrollableFrame(sc, fg_color="#0a0c10", corner_radius=10)
        self.shots.grid(row=1,column=0, sticky="nsew", padx=10, pady=(0,10))
        for c in range(4): self.shots.grid_columnconfigure(c, weight=1)
        self._shots_items=[]

    # ---- import options ----
    def _build_options(self):
        o=ctk.CTkFrame(self, fg_color=CARD, corner_radius=14); o.grid(row=3,column=0, sticky="ew", padx=20, pady=6)
        o.grid_columnconfigure(0, weight=1)
        r1=ctk.CTkFrame(o, fg_color="transparent"); r1.grid(row=0,column=0, sticky="ew", padx=14, pady=(12,4))
        self.models_only=ctk.BooleanVar(value=self.cfg.get("models_only",True))
        mo=ctk.CTkCheckBox(r1, text="Models only (fast - skip raw frames)", variable=self.models_only,
                        onvalue=True, offvalue=False, command=self.update_summary,
                        fg_color=AC, hover_color=AC_H, text_color=TX); mo.pack(side="left")
        self._tip(mo, "Copies only the finished meshes and point clouds (.ply) and skips the "
                      "thousands of raw depth frames. Much faster and smaller. Turn off only if you "
                      "want the raw frames to re-process a scan later in Revo Scan.")
        self.auto_open=ctk.BooleanVar(value=self.cfg.get("auto_open",True))
        ao=ctk.CTkCheckBox(r1, text="Open folder when done", variable=self.auto_open,
                        fg_color=AC, hover_color=AC_H, text_color=TX); ao.pack(side="left", padx=(18,0))
        self._tip(ao, "Open the destination folder automatically when the import finishes.")
        self.cleanup=ctk.BooleanVar(value=self.cfg.get("cleanup",False))
        cu=ctk.CTkCheckBox(r1, text="Clean up mesh", variable=self.cleanup,
                        fg_color=AC, hover_color=AC_H, text_color=TX); cu.pack(side="left", padx=(18,0))
        self._tip(cu, "Tidy the mesh on your PC during import: keep the main object (remove floating bits), "
                      "fill small holes, and lightly smooth. Skips the slow on-device edit. Off = raw mesh, untouched.")
        ctk.CTkButton(r1, text="Select all", width=84, height=28, corner_radius=14, fg_color=CARD2,
                      hover_color=STROKE, text_color=TX, command=self.select_all).pack(side="right", padx=4)
        ctk.CTkButton(r1, text="None", width=64, height=28, corner_radius=14, fg_color=CARD2,
                      hover_color=STROKE, text_color=TX, command=self.select_none).pack(side="right", padx=4)
        # export format - a real, intentional control
        ex=ctk.CTkFrame(o, fg_color=CARD2, corner_radius=12); ex.grid(row=1,column=0, sticky="ew", padx=14, pady=(2,4))
        ctk.CTkLabel(ex, text="Save meshes as", text_color=TX, font=ctk.CTkFont(size=12,weight="bold")).pack(side="left", padx=(14,10), pady=10)
        ctk.CTkLabel(ex, text="PLY", fg_color=AC, text_color="#04121f", corner_radius=13, width=50, height=26,
                     font=ctk.CTkFont(size=12,weight="bold")).pack(side="left", padx=3)
        self.exp_stl=ctk.BooleanVar(value=self.cfg.get("exp_stl",False))
        self.exp_obj=ctk.BooleanVar(value=self.cfg.get("exp_obj",False))
        self.exp_glb=ctk.BooleanVar(value=self.cfg.get("exp_glb",False))
        self._fmt_chip(ex,"STL",self.exp_stl).pack(side="left", padx=3)
        self._fmt_chip(ex,"OBJ",self.exp_obj).pack(side="left", padx=3)
        self._fmt_chip(ex,"GLB",self.exp_glb).pack(side="left", padx=3)
        ctk.CTkLabel(ex, text="PLY is always kept  ·  STL for printing  ·  OBJ / GLB for editing",
                     text_color=MUT, font=ctk.CTkFont(size=10)).pack(side="left", padx=(14,0))
        r2=ctk.CTkFrame(o, fg_color="transparent"); r2.grid(row=2,column=0, sticky="ew", padx=14, pady=(4,12))
        r2.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(r2, text="Save to", text_color=MUT).grid(row=0,column=0, padx=(0,8))
        self.dest=ctk.StringVar(value=self.cfg.get("dest",DEFAULT_DEST))
        ctk.CTkEntry(r2, textvariable=self.dest, fg_color="#0d0f14", border_color=STROKE, text_color=TX,
                     corner_radius=10, height=34).grid(row=0,column=1, sticky="ew")
        ctk.CTkButton(r2, text="Browse", width=84, height=34, corner_radius=14, fg_color=CARD2,
                      hover_color=STROKE, text_color=TX, command=self.browse).grid(row=0,column=2, padx=(8,0))

    def _fmt_chip(self, parent, label, var):
        b=ctk.CTkButton(parent, text=label, width=50, height=26, corner_radius=13)
        def paint():
            on=var.get()
            b.configure(fg_color=(AC if on else "#11151c"), hover_color=(AC_H if on else STROKE),
                        text_color=("#04121f" if on else MUT))
        def toggle(): var.set(not var.get()); paint()
        b.configure(command=toggle); paint()
        return b

    # ---- action bar ----
    def _actions(self):
        a=ctk.CTkFrame(self, fg_color="transparent"); a.grid(row=4,column=0, sticky="ew", padx=20, pady=(2,14))
        a.grid_columnconfigure(0, weight=1)
        a.grid_rowconfigure(1, minsize=16); a.grid_rowconfigure(2, minsize=20)   # reserve progress space so it never resizes the window
        self.summary=ctk.CTkLabel(a, text="Nothing selected", text_color=MUT, anchor="w", font=ctk.CTkFont(size=12))
        self.summary.grid(row=0,column=0, sticky="w")
        self.progress=ctk.CTkProgressBar(a, height=8, corner_radius=6, progress_color=AC); self.progress.set(0)
        self.progline=ctk.CTkLabel(a, text="", text_color=MUT, anchor="w", font=ctk.CTkFont(size=11))
        self.open_btn=ctk.CTkButton(a, text="📂 Open folder", width=130, height=40, corner_radius=20,
                                    fg_color=CARD2, hover_color=STROKE, text_color=TX, command=self.open_folder)
        self.open_btn.grid(row=0,column=1, padx=6)
        self.zip_btn=ctk.CTkButton(a, text="🗜 Export ZIP", width=130, height=40, corner_radius=20,
                                   fg_color=CARD2, hover_color=STROKE, text_color=TX, command=self.on_export_zip)
        self.zip_btn.grid(row=0,column=2, padx=6)
        self.cancel_btn=ctk.CTkButton(a, text="Cancel", width=110, height=40, corner_radius=20,
                                      fg_color="#3a2530", hover_color=DANGER, text_color=TX, command=self.on_cancel)
        self.import_btn=ctk.CTkButton(a, text="⬇  Import selected", width=180, height=40, corner_radius=20,
                                      fg_color=AC, hover_color=AC_H, text_color="#04121f",
                                      font=ctk.CTkFont(size=13,weight="bold"), command=self.on_pull)
        self.import_btn.grid(row=0,column=3)

    # ---- dialogs ----
    def _top(self, title, w=560, h=440, key=None):
        key=key or title
        if not hasattr(self,"_dialogs"): self._dialogs={}
        ex=self._dialogs.get(key)
        if ex is not None:
            try:
                if ex.winfo_exists():
                    ex.deiconify(); ex.lift(); ex.focus_force(); return None
            except Exception: pass
        t=ctk.CTkToplevel(self); t.title(title); t.geometry("%dx%d"%(w,h)); t.configure(fg_color=BG)
        t.transient(self); t.after(60, t.lift)
        self._dialogs[key]=t
        t.protocol("WM_DELETE_WINDOW", lambda: (self._dialogs.pop(key,None), t.destroy()))
        return t

    def _tip(self, widget, text):
        """Lightweight hover tooltip for a widget."""
        st={"win":None}
        def show(_=None):
            if st["win"] or not text: return
            try:
                tw=tk.Toplevel(widget); tw.wm_overrideredirect(True); tw.configure(bg="#0b0e13")
                try: tw.wm_attributes("-type","tooltip"); tw.attributes("-topmost",True)
                except Exception: pass
                f=ctk.CTkFrame(tw, fg_color="#0b0e13", corner_radius=8, border_width=1, border_color=STROKE)
                f.pack()
                ctk.CTkLabel(f, text=text, text_color=TX, font=ctk.CTkFont(size=11), justify="left",
                             wraplength=300).pack(padx=10, pady=7)
                tw.update_idletasks()
                x=widget.winfo_rootx()+14
                y=widget.winfo_rooty()-tw.winfo_reqheight()-8          # above the widget
                if y < 0: y=widget.winfo_rooty()+widget.winfo_height()+6   # fall back below if no room
                tw.wm_geometry("+%d+%d"%(x,y))
                st["win"]=tw
            except Exception: pass
        def hide(_=None):
            if st["win"]:
                try: st["win"].destroy()
                except Exception: pass
                st["win"]=None
        widget.bind("<Enter>", show); widget.bind("<Leave>", hide)

    def _modal(self, title, message, buttons):
        """Dark-themed modal. buttons: list of (label, value, accent). Returns chosen value."""
        dlg=ctk.CTkToplevel(self); dlg.title(title); dlg.configure(fg_color=BG); dlg.resizable(False,False)
        try: dlg.transient(self)
        except Exception: pass
        w,h=440,200
        try:
            self.update_idletasks()
            if self.winfo_width()>100:
                x=self.winfo_rootx()+(self.winfo_width()-w)//2; y=self.winfo_rooty()+(self.winfo_height()-h)//3
            else:
                x=(self.winfo_screenwidth()-w)//2; y=(self.winfo_screenheight()-h)//2
            dlg.geometry("%dx%d+%d+%d"%(w,h,x,y))
        except Exception: pass
        res={"v":None}
        card=ctk.CTkFrame(dlg, fg_color=CARD, corner_radius=14); card.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(family=WORDMARK, size=15, weight="bold"), text_color=TX).pack(anchor="w", padx=18, pady=(16,4))
        ctk.CTkLabel(card, text=message, font=ctk.CTkFont(size=12), text_color=MUT, justify="left", wraplength=w-64).pack(anchor="w", padx=18, pady=(0,8))
        row=ctk.CTkFrame(card, fg_color="transparent"); row.pack(side="bottom", fill="x", padx=14, pady=(0,14))
        def choose(v): res["v"]=v; dlg.destroy()
        for label,val,accent in buttons:
            ctk.CTkButton(row, text=label, width=96, height=34, corner_radius=17,
                          fg_color=(AC if accent else CARD2), hover_color=(AC_H if accent else STROKE),
                          text_color=("#04121f" if accent else TX), command=lambda v=val: choose(v)).pack(side="right", padx=6)
        try:
            dlg.grab_set(); dlg.wait_window()
        except Exception: pass
        return res["v"]
    def _confirm(self, title, message):
        return self._modal(title, message, [("Yes",True,True),("No",False,False)]) is True
    def _alert(self, title, message):
        self._modal(title, message, [("OK",True,True)])
    def dlg_text(self, title, body):
        t=self._top(title)
        if t is None: return
        box=ctk.CTkTextbox(t, fg_color=CARD, text_color=TX, corner_radius=12, wrap="word"); box.pack(fill="both", expand=True, padx=16, pady=16)
        box.insert("1.0", body); box.configure(state="disabled")
    def dlg_help(self):
        t=self._top("How to use "+APP, 780, 700)
        if t is None: return
        head=ctk.CTkFrame(t, fg_color="transparent"); head.pack(fill="x", padx=22, pady=(18,6))
        if os.path.exists(ICON):
            try: self.imgs["helpico"]=cimg(ICON,46); ctk.CTkLabel(head, image=self.imgs["helpico"], text="").pack(side="left", padx=(0,12))
            except Exception: pass
        hc=ctk.CTkFrame(head, fg_color="transparent"); hc.pack(side="left", anchor="w")
        ctk.CTkLabel(hc, text="How to use PointYoink", font=ctk.CTkFont(size=19,weight="bold"), text_color=TX).pack(anchor="w")
        ctk.CTkLabel(hc, text="Get your MIRACO scans onto Linux in a few clicks", text_color=MUT, font=ctk.CTkFont(size=12)).pack(anchor="w")
        sc=ctk.CTkScrollableFrame(t, fg_color="transparent"); sc.pack(fill="both", expand=True, padx=16, pady=6)
        def card(title, rows, accent=AC):
            f=ctk.CTkFrame(sc, fg_color=CARD, corner_radius=14); f.pack(fill="x", padx=6, pady=7)
            ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=14,weight="bold"), text_color=accent).pack(anchor="w", padx=16, pady=(12,6))
            for r in rows:
                ctk.CTkLabel(f, text=r, font=ctk.CTkFont(size=12), text_color=TX, justify="left",
                             anchor="w", wraplength=690).pack(anchor="w", padx=16, pady=1)
            ctk.CTkFrame(f, fg_color="transparent", height=6).pack()
        card("Quick start", [
            "1.   Plug the scanner into this PC with a USB-C data cable.",
            "2.   On the scanner, tap  “File Transfer”  (Share to PC, USB Cable).",
            "3.   PointYoink connects on its own; your projects show on the left.",
            "4.   Tick the projects you want. Click one to preview its scans.",
            "5.   Pick a Save-to folder and click  Import selected.",
        ])
        card("Models only vs full", [
            "“Models only” (default) grabs the finished meshes and point clouds and",
            "skips the thousands of raw depth frames, so it is far faster.",
            "Turn it off only if you want the raw frames to reprocess a scan later.",
        ], accent=OK)
        card("What you get", [
            "fuse_mesh.ply   -   the finished 3D mesh, with faces (print or render this).",
            "fuse.ply   -   the fused point cloud, points only.",
            "Both are standard .ply for Blender, MeshLab, or CloudCompare.",
            "Tick STL or OBJ in Import options to also export those formats.",
        ])
        card("Trouble?", [
            "Nothing detected:  confirm you tapped File Transfer, and try another",
            "USB-C cable - some cables only charge.",
            "Stuck connecting:  unplug, replug, tap File Transfer, and try again.",
            "Blank previews:  the scanner is waking up; click the project again.",
            "Anything else:  open the error log below and file an issue.",
        ], accent=WARN)
        row=ctk.CTkFrame(t, fg_color="transparent"); row.pack(fill="x", padx=22, pady=(2,16))
        ctk.CTkButton(row, text="Open error log", corner_radius=16, fg_color=CARD2, hover_color=STROKE,
                      text_color=TX, command=self.dlg_logs).pack(side="left")
        ctk.CTkButton(row, text="GitHub ↗", corner_radius=16, fg_color=AC, hover_color=AC_H,
                      text_color="#04121f", command=lambda: subprocess.Popen(["xdg-open",GITHUB])).pack(side="right")

    def dlg_about(self):
        t=self._top("About "+APP, 640, 680)
        if t is None: return
        if os.path.exists(ICON):
            try: self.imgs["about"]=cimg(ICON,88); ctk.CTkLabel(t, image=self.imgs["about"], text="").pack(pady=(22,6))
            except Exception: pass
        ctk.CTkLabel(t, text=APP+"  "+VERSION, font=ctk.CTkFont(family=WORDMARK, size=22,weight="bold"), text_color=TX).pack()
        ctk.CTkLabel(t, text="Yoink your 3D scans off a Revopoint scanner - on Linux, over USB.",
                     text_color=MUT, font=ctk.CTkFont(size=13)).pack(pady=(4,0))
        info=ctk.CTkFrame(t, fg_color=CARD, corner_radius=14); info.pack(fill="x", padx=24, pady=(14,8))
        info.grid_columnconfigure(1, weight=1)
        rows=[("Works with", "Revopoint MIRACO  ·  MIRACO Pro\nany Revopoint scanner with USB “File Transfer” (MTP)"),
              ("Needs", "Linux  ·  jmtpfs  ·  rsync"),
              ("Output", "standard .ply meshes & point clouds\nopen in Blender, MeshLab, or CloudCompare")]
        for i,(k,v) in enumerate(rows):
            ctk.CTkLabel(info, text=k, text_color=AC, font=ctk.CTkFont(size=11,weight="bold"),
                         anchor="ne", width=92).grid(row=i,column=0, sticky="ne", padx=(16,12), pady=(14 if i==0 else 4, 4 if i<2 else 14))
            ctk.CTkLabel(info, text=v, text_color=TX, font=ctk.CTkFont(size=12), justify="left",
                         anchor="w").grid(row=i,column=1, sticky="w", pady=(14 if i==0 else 4, 4 if i<2 else 14))
        ctk.CTkLabel(t, text="MIT licensed · free and open source", text_color=OK, font=ctk.CTkFont(size=12,weight="bold")).pack()
        ctk.CTkLabel(t, text="Unofficial. Not affiliated with or endorsed by Revopoint.\n"
                     "“Revopoint” and “MIRACO” are trademarks of their owners.",
                     text_color=MUT, font=ctk.CTkFont(size=11), justify="center").pack(pady=(6,0))
        ctk.CTkButton(t, text="GitHub  ↗", corner_radius=18, fg_color=AC, hover_color=AC_H, text_color="#04121f",
                      command=lambda: subprocess.Popen(["xdg-open",GITHUB])).pack(pady=12)
        ctk.CTkLabel(t, text="Changelog", text_color=MUT, font=ctk.CTkFont(size=12,weight="bold"), anchor="w").pack(fill="x", padx=24)
        box=ctk.CTkTextbox(t, fg_color=CARD, text_color=TX, corner_radius=12, wrap="word", height=150)
        box.pack(fill="both", expand=True, padx=24, pady=(4,20)); box.insert("1.0", CHANGELOG); box.configure(state="disabled")
    def dlg_settings(self):
        t=self._top("Settings", 560, 400)
        if t is None: return
        ctk.CTkLabel(t, text="Default save folder", text_color=TX, anchor="w").pack(fill="x", padx=20, pady=(20,4))
        dv=ctk.StringVar(value=self.dest.get()); row=ctk.CTkFrame(t, fg_color="transparent"); row.pack(fill="x", padx=20)
        ctk.CTkEntry(row, textvariable=dv, fg_color="#0d0f14", border_color=STROKE, text_color=TX, corner_radius=10).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Browse", width=84, corner_radius=14, fg_color=CARD2, hover_color=STROKE, text_color=TX,
                      command=lambda: dv.set(filedialog.askdirectory(initialdir=dv.get() or HOME) or dv.get())).pack(side="left", padx=6)
        mo=ctk.BooleanVar(value=self.models_only.get()); ao=ctk.BooleanVar(value=self.auto_open.get())
        ctk.CTkCheckBox(t, text="Models only by default", variable=mo, fg_color=AC, hover_color=AC_H, text_color=TX).pack(anchor="w", padx=20, pady=(16,4))
        ctk.CTkCheckBox(t, text="Open folder when import finishes", variable=ao, fg_color=AC, hover_color=AC_H, text_color=TX).pack(anchor="w", padx=20)
        # UI scale (for HiDPI / tiny-window fix)
        sr=ctk.CTkFrame(t, fg_color="transparent"); sr.pack(fill="x", padx=20, pady=(18,0))
        cur=getattr(self,"_ui_scale",1.0)
        sv=ctk.DoubleVar(value=cur)
        lab=ctk.CTkLabel(sr, text="UI scale: %.2fx"%cur, text_color=TX); lab.pack(side="left")
        ctk.CTkLabel(sr, text="(raise this if the window is tiny; applies next launch)", text_color=MUT, font=ctk.CTkFont(size=10)).pack(side="left", padx=(8,0))
        sl=ctk.CTkSlider(t, from_=0.8, to=2.5, number_of_steps=34, variable=sv,
                         command=lambda v: lab.configure(text="UI scale: %.2fx"%float(v)))
        sl.pack(fill="x", padx=20, pady=(4,0))
        def save():
            self.dest.set(dv.get()); self.models_only.set(mo.get()); self.auto_open.set(ao.get())
            self.cfg["ui_scale"]=round(float(sv.get()),2); self._persist(); t.destroy()
            if abs(float(sv.get())-cur)>0.02:
                self._alert("UI scale changed", "The new UI scale takes effect next time you open PointYoink.")
        ctk.CTkButton(t, text="Save", corner_radius=18, fg_color=AC, hover_color=AC_H, text_color="#04121f", command=save).pack(pady=20)

    def _on_tk_error(self, exc, val, tb):
        log_line("UI error: %s\n%s" % (val, "".join(_tb.format_exception(exc, val, tb)).rstrip()))
        try: self.set_banner("Something went wrong - see Help > Error log.", WARN)
        except Exception: pass

    def dlg_logs(self):
        t=self._top("Error log", 720, 520)
        if t is None: return
        ctk.CTkLabel(t, text="If something breaks, copy this into a GitHub issue.",
                     text_color=MUT).pack(anchor="w", padx=20, pady=(16,4))
        box=ctk.CTkTextbox(t, fg_color=CARD, text_color=TX, corner_radius=12, wrap="none",
                           font=ctk.CTkFont(family="monospace", size=11))
        box.pack(fill="both", expand=True, padx=20, pady=6)
        try: content=open(LOGFILE).read()
        except Exception: content=""
        box.insert("1.0", content or "No errors logged. Nice.")
        box.configure(state="disabled")
        row=ctk.CTkFrame(t, fg_color="transparent"); row.pack(fill="x", padx=20, pady=(4,16))
        def copy():
            try:
                self.clipboard_clear(); self.clipboard_append(content); self.set_banner("Log copied to clipboard.", OK)
            except Exception: pass
        def clear():
            try: open(LOGFILE,"w").close()
            except Exception: pass
            box.configure(state="normal"); box.delete("1.0","end"); box.insert("1.0","No errors logged. Nice."); box.configure(state="disabled")
        ctk.CTkButton(row, text="Copy", corner_radius=16, fg_color=AC, hover_color=AC_H, text_color="#04121f", command=copy).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Open log file", corner_radius=16, fg_color=CARD2, hover_color=STROKE, text_color=TX,
                      command=lambda: subprocess.Popen(["xdg-open", LOGFILE])).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Clear", corner_radius=16, fg_color=CARD2, hover_color=STROKE, text_color=TX, command=clear).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Report on GitHub", corner_radius=16, fg_color=CARD2, hover_color=STROKE, text_color=TX,
                      command=lambda: subprocess.Popen(["xdg-open", GITHUB+"/issues/new"])).pack(side="right", padx=4)

    def _persist(self):
        self.cfg.update(dest=self.dest.get(), models_only=self.models_only.get(),
                        auto_open=self.auto_open.get(), geometry=self.geometry(),
                        exp_stl=self.exp_stl.get(), exp_obj=self.exp_obj.get(), exp_glb=self.exp_glb.get(),
                        cleanup=self.cleanup.get(),
                        records=self.records); save_cfg(self.cfg)

    # per-project records (rename + imported memory), keyed by ORIGINAL id
    def disp(self, name):
        return (self.records.get(name,{}).get("label") or name)
    def is_imported(self, name):
        # "imported" must mean a real model actually landed - not just a non-empty folder
        # left behind by a failed/partial transfer. Require at least one mesh/point-cloud .ply.
        d=os.path.join(self.dest.get() or DEFAULT_DEST, name)
        if not os.path.isdir(d): return False
        try:
            if glob.glob(os.path.join(d, "*.ply")): return True          # flat layout
            if glob.glob(os.path.join(d, "data", "*", "*.ply")): return True  # full/nested layout
        except Exception: pass
        return False
    def _proj(self, name):
        return next((x for x in self.projects if x["name"]==name), None)
    def changed(self, name):
        """True if the device project has new scans/meshes or a newer edit time since it was imported."""
        rec=self.records.get(name,{})
        if not rec.get("imported_at"): return False
        sig=rec.get("sig"); p=self._proj(name)
        if not sig or not p: return False
        return ((p.get("edit_time") or 0) > (sig.get("edit_time") or 0)
                or (p.get("nodes") or 0) > (sig.get("nodes") or 0)
                or (p.get("meshes") or 0) > (sig.get("meshes") or 0))
    def rename_project(self, name):
        d=ctk.CTkInputDialog(title="Rename project",
                             text="Friendly name for:\n%s\n\n(the original ID is kept as the folder name /\nreference - clear the box to reset)"%name)
        val=d.get_input()
        if val is None: return
        self.records.setdefault(name,{})["label"]=(val.strip() or None)
        self._persist(); self.projects_sig=None  # force re-render
    def on_close(self): self._persist(); self.destroy()

    # ---- helpers ----
    def browse(self):
        d=filedialog.askdirectory(initialdir=self.dest.get() or HOME)
        if d: self.dest.set(d)
    def set_banner(self, text, color): self.banner.configure(text=text); self.dot.configure(text_color=color)
    def select_all(self):
        for v in self.pull_sel.values(): v.set(True)
        self.update_summary()
    def select_none(self):
        for v in self.pull_sel.values(): v.set(False)
        self.update_summary()
    def update_summary(self):
        sel=[n for n,v in self.pull_sel.items() if v.get()]
        if not sel: self.summary.configure(text="Nothing selected"); return
        known=[self.size_cache.get(n) for n in sel]; tot=sum(s for s in known if s); miss=sum(1 for s in known if not s)
        est=" · ~%s%s"%(human(tot), "+" if miss else "") if tot else ""
        note="" if self.models_only.get() else "  (full - incl. raw frames)"
        self.summary.configure(text="%d project(s)%s%s"%(len(sel),est,note))

    # ---- polling ----
    def refresh_loop(self):
        if not self.pulling:
            st,serial=usb_state(); self.serial=serial; mounted=quick_mounted()
            if st=="absent":
                self.set_banner("Scanner not detected - plug in the USB-C cable.", WARN)
                self.action_btn.configure(text="Connect", state="normal"); self.listed=False; self.auto_tried=False
            elif st=="adb":
                self.set_banner("MIRACO detected · Not connected - tap “File Transfer” on the scanner", WARN)
                self.action_btn.configure(text="Connect", state="normal"); self.listed=False; self.auto_tried=False
            elif st=="mtp" and not mounted:
                self.action_btn.configure(text="Connect", state="normal"); self.listed=False
                if self._mounting:
                    self.set_banner("Connecting…", AC)
                elif not self.auto_tried:
                    self.auto_tried=True; self.set_banner("MIRACO detected - connecting…", AC); self.on_mount()
                else:
                    self.set_banner("MIRACO detected · Not connected - click Connect →", AC)
            elif mounted:
                self.action_btn.configure(text="Rescan", state="normal")
                if self.listed:
                    self.set_banner("Connected - tick scans to import, click one to preview.", OK)
                    if self.projects: self.render_list(self.projects)   # refresh badges if files changed on disk (cheap no-op otherwise)
                else: self.set_banner("Reading projects off the scanner… (MTP is slow)", AC); self.start_listing()
        self.after(1500, self.refresh_loop)
    def start_listing(self):
        if self.listing: return
        self.listing=True
        threading.Thread(target=lambda: self.q.put(("projects", list_projects())), daemon=True).start()
    def on_mount(self):
        if self._mounting: return
        st,_=usb_state()
        if st!="mtp": self.set_banner("Tap “File Transfer” on the MIRACO first.", WARN); return
        self._mounting=True; self._shots_loaded=False; self.set_banner("Connecting…", AC)
        threading.Thread(target=lambda: self.q.put(("mounted", *do_mount())), daemon=True).start()

    # ---- list ----
    def render_list(self, projs):
        # include imported/changed state so the list re-renders when files appear or are deleted
        sig=json.dumps([[p, self.is_imported(p["name"]), self.changed(p["name"])] for p in projs])
        if sig==self.projects_sig: return
        self.projects_sig=sig; self.projects=projs
        for w in self.llist.winfo_children(): w.destroy()
        old=self.pull_sel; self.pull_sel={}; self.rows={}
        dest=self.dest.get() or DEFAULT_DEST
        for i,p in enumerate(projs):
            name=p["name"]; var=old.get(name) or ctk.BooleanVar(value=False)
            var.trace_add("write", lambda *a: self.update_summary()); self.pull_sel[name]=var
            card=ctk.CTkFrame(self.llist, fg_color=CARD2, corner_radius=12, border_width=0)
            card.grid(row=i, column=0, sticky="ew", pady=5, padx=2); card.grid_columnconfigure(2, weight=1)
            self.rows[name]=card
            ctk.CTkCheckBox(card, text="", width=24, variable=var, fg_color=AC, hover_color=AC_H).grid(row=0,column=0, padx=(10,4), pady=10)
            if p.get("thumb"):
                try: self.imgs["row_"+name]=cimg(p["thumb"],54); ctk.CTkLabel(card, image=self.imgs["row_"+name], text="").grid(row=0,column=1, padx=4)
                except Exception: ctk.CTkLabel(card, text="-", text_color=MUT, width=54).grid(row=0,column=1)
            else: ctk.CTkLabel(card, text="-", text_color=MUT, width=54).grid(row=0,column=1)
            txt=ctk.CTkFrame(card, fg_color="transparent"); txt.grid(row=0,column=2, sticky="ew", padx=6, pady=6)
            # line 1: name (+ original id underneath if it was renamed)
            ctk.CTkLabel(txt, text=self.disp(name), text_color=TX, font=ctk.CTkFont(size=12,weight="bold"),
                         anchor="w").pack(anchor="w", fill="x")
            if self.records.get(name,{}).get("label"):
                ctk.CTkLabel(txt, text=name, text_color=MUT, font=ctk.CTkFont(size=9), anchor="w").pack(anchor="w", fill="x")
            # line 2: date · size
            l2=" · ".join([x for x in [p.get("date") or "", human(self.size_cache[name]) if self.size_cache.get(name) else ""] if x])
            if l2:
                ctk.CTkLabel(txt, text=l2, text_color=MUT, font=ctk.CTkFont(size=10), anchor="w").pack(anchor="w", fill="x")
            # line 3: scans · meshes · clouds (+ imported/updated badge)
            parts=[]
            if p.get("nodes"): parts.append("%d scans"%p["nodes"])
            if p.get("meshes"): parts.append("%d mesh%s"%(p["meshes"], "es" if p["meshes"]!=1 else ""))
            if p.get("clouds"): parts.append("%d cloud%s"%(p["clouds"], "s" if p["clouds"]!=1 else ""))
            ml=ctk.CTkFrame(txt, fg_color="transparent"); ml.pack(anchor="w", fill="x")
            ctk.CTkLabel(ml, text=" · ".join(parts), text_color=MUT, font=ctk.CTkFont(size=10)).pack(side="left")
            if self.is_imported(name):
                if self.changed(name):
                    ctk.CTkLabel(ml, text="  ↻ updated", text_color=WARN, font=ctk.CTkFont(size=10)).pack(side="left")
                else:
                    ctk.CTkLabel(ml, text="  ✓ imported", text_color=OK, font=ctk.CTkFont(size=10)).pack(side="left")
            ctk.CTkButton(card, text="✎", width=30, height=30, corner_radius=15, fg_color="transparent",
                          hover_color=STROKE, text_color=MUT, command=lambda n=name: self.rename_project(n)).grid(row=0,column=3, padx=(0,8))
            for w in [card, txt, ml] + txt.winfo_children() + ml.winfo_children():
                w.bind("<Button-1>", lambda e,n=name: self.select_project(n))
        threading.Thread(target=self._compute_sizes, args=([p["name"] for p in projs],), daemon=True).start()
        if projs and not self.selected: self.select_project(projs[0]["name"])
    def _compute_sizes(self, names):
        for n in names:
            if n not in self.size_cache:
                sz,_=project_model_size(n); self.size_cache[n]=sz; self.q.put(("sizes",None))
    def select_project(self, name):
        self.selected=name
        for n,card in self.rows.items():
            card.configure(fg_color=(SELB if n==name else CARD2))
        p=next((x for x in self.projects if x["name"]==name), None)
        if not p: return
        if p.get("thumb"):
            self._set_big_image(p["thumb"])
        self.detail.configure(text="Project: %s     Edited: %s\nMeshes: %s   Point clouds: %s   Scans: %s"%(
            name, p.get("date") or "?", p.get("meshes"), p.get("clouds"), p.get("nodes")))
        self.detail.grid(); self.renders_lbl.grid(); self.film.grid()
        if p.get("meshes"): self.tools.grid()
        else: self.tools.grid_remove()
        for w in self.film.winfo_children(): w.destroy()
        if name in self.gallery_cache: self.render_gallery(name, self.gallery_cache[name])
        else:
            ctk.CTkLabel(self.film, text="loading scan renders…", text_color=MUT).pack(side="left", padx=8)
            threading.Thread(target=lambda n=name: self.q.put(("gallery",n,gather_gallery(n))), daemon=True).start()
        self.files_box.configure(state="normal"); self.files_box.delete("1.0","end")
        self.files_box.insert("end","computing model files…\n"); self.files_box.configure(state="disabled")
        threading.Thread(target=lambda n=name: self.q.put(("files",n,project_model_size(n))), daemon=True).start()
    def render_gallery(self, name, items):
        if self.selected!=name: return
        for w in self.film.winfo_children(): w.destroy()
        if not items:
            self.renders_lbl.grid_remove(); self.film.grid_remove(); return
        self.renders_lbl.grid(); self.film.grid()
        for node,path in items:
            try:
                self.imgs["g_"+name+node]=cimg(path,84)
                lbl=ctk.CTkLabel(self.film, image=self.imgs["g_"+name+node], text="", fg_color="#0a0c10", corner_radius=8)
                lbl.pack(side="left", padx=4, pady=4); lbl.bind("<Button-1>", lambda e,pp=path: self._enlarge(pp))
            except Exception: pass
    def _enlarge(self, path):
        self._set_big_image(path)

    def _set_big_image(self, path):
        """Show a preview that scales to fill the box and re-fits on window resize."""
        try:
            self._big_src=Image.open(path).convert("RGBA")
            self.imgs["big"]=ctk.CTkImage(light_image=self._big_src, dark_image=self._big_src, size=(320,240))
            self.big.configure(image=self.imgs["big"], text="")
            self._fit_big()
        except Exception:
            self._big_src=None; self.big.configure(image=None, text="(preview unavailable)")
    def _on_big_resize(self, e):
        if getattr(self,"_fit_job",None):
            try: self.after_cancel(self._fit_job)
            except Exception: pass
        self._fit_job=self.after(60, self._fit_big)
    def _fit_big(self, _=None):
        src=getattr(self,"_big_src",None)
        if src is None or "big" not in self.imgs: return
        try:
            bw=max(60, self.big.winfo_width()-24); bh=max(60, self.big.winfo_height()-24)
            iw,ih=src.size
            scale=min(bw/iw, bh/ih)
            scale=min(scale, 2.2)   # cap upscaling so a small preview doesn't get too blurry
            self.imgs["big"].configure(size=(max(20,int(iw*scale)), max(20,int(ih*scale))))
        except Exception: pass

    # ---- import ----
    def on_pull(self):
        if self.pulling: return
        sel=[n for n,v in self.pull_sel.items() if v.get()]
        if not sel: self.set_banner("Tick at least one project to import.", WARN); return
        already=[n for n in sel if self.is_imported(n) and not self.changed(n)]
        if already:
            names=", ".join(self.disp(n) for n in already)
            if not self._confirm("Already imported",
                    "%d of these were already imported and haven't changed:\n%s\n\nImport them again anyway?"%(len(already), names)):
                sel=[n for n in sel if n not in already]
                if not sel:
                    self.set_banner("Nothing to import (all already imported).", MUT); return
        self.pulling=True; self.cancel=False; self._pull_list=sel; self._export_fails=[]
        self.import_btn.grid_remove(); self.cancel_btn.grid(row=0,column=3)
        self.progress.grid(row=1,column=0, columnspan=3, sticky="ew", pady=(8,0)); self.progline.grid(row=2,column=0, columnspan=3, sticky="w")
        dest=self.dest.get() or DEFAULT_DEST; mo=self.models_only.get(); cleanup=self.cleanup.get(); self._persist()
        fmts=[]
        if self.exp_stl.get(): fmts.append("stl")
        if self.exp_obj.get(): fmts.append("obj")
        if self.exp_glb.get(): fmts.append("glb")
        threading.Thread(target=self._pull_worker, args=(sel,dest,mo,fmts,cleanup), daemon=True).start()
    def _pull_worker(self, sel, dest, mo, fmts, cleanup):
        os.makedirs(dest, exist_ok=True); total=len(sel); failed=[]
        for i,name in enumerate(sel):
            if self.cancel: break
            try:
                if mo:
                    self._import_flat(name, dest, fmts, cleanup, i, total)   # clean flat layout: <name>/<name>_<node>.ply (+.stl)
                else:
                    self._import_full(name, dest, i, total)         # full project incl. raw frames (nested mirror)
            except Exception as e:
                failed.append(name); log_error("import", e)
        self.proc=None
        self.q.put(("cancelled" if self.cancel else "done", dest, failed))

    def _import_flat(self, name, dest, fmts, cleanup, i, total):
        """Copy just the finished models into <dest>/<name>/ with clean unique names."""
        src=os.path.join(PROJECTS, name); out=os.path.join(dest, name); os.makedirs(out, exist_ok=True)
        revo=os.path.join(src, name+".revo")
        if os.path.exists(revo):
            try: shutil.copyfile(revo, os.path.join(out, name+".revo"))
            except Exception: pass
        nodes=sorted(glob.glob(os.path.join(src, "data", "*")))
        n=max(1,len(nodes))
        meshes=[]
        for j,nd in enumerate(nodes):
            if self.cancel: return
            if not os.path.isdir(nd): continue
            node=os.path.basename(nd)
            self.q.put(("prog", (i*100 + j*90//n)/(total*100), "Importing %s - scan %d/%d"%(name, j+1, n)))
            m=os.path.join(nd,"fuse_mesh.ply"); c=os.path.join(nd,"fuse.ply"); pv=os.path.join(nd,"preview.png")
            if os.path.exists(m):
                d=os.path.join(out, "%s_%s.ply"%(name,node)); shutil.copyfile(m, d); meshes.append(d)
            if os.path.exists(c):
                shutil.copyfile(c, os.path.join(out, "%s_%s_cloud.ply"%(name,node)))
            if os.path.exists(pv):
                try: shutil.copyfile(pv, os.path.join(out, "%s_%s.png"%(name,node)))
                except Exception: pass
        if (fmts or cleanup) and not self.cancel:
            self._process_meshes(meshes, name, fmts, cleanup, i, total)

    def _clean_mesh(self, m):
        """Tidy a mesh: dedupe, keep the largest connected piece, fill small holes, light smooth."""
        import trimesh
        try: m.merge_vertices()
        except Exception: pass
        try:
            m.update_faces(m.nondegenerate_faces()); m.update_faces(m.unique_faces()); m.remove_unreferenced_vertices()
        except Exception: pass
        try:
            comps=m.split(only_watertight=False)
            if len(comps)>1: m=max(comps, key=lambda c: len(c.faces))
        except Exception: pass
        try: m.fill_holes()
        except Exception: pass
        try: trimesh.smoothing.filter_humphrey(m, iterations=5)
        except Exception: pass
        return m

    def _process_meshes(self, plys, name, fmts, cleanup, i, total):
        """Optionally clean each mesh (overwrite its .ply), then export the requested formats.
        Records any failures in self._export_fails so _finish can surface them to the user."""
        import trimesh
        for ply in plys:
            if self.cancel: return
            try:
                m=trimesh.load(ply, force="mesh")
                if cleanup:
                    self.q.put(("prog", (i+1)/total, "Cleaning up %s…"%name))
                    m=self._clean_mesh(m)
                    m.export(ply)   # replace the imported .ply with the cleaned mesh
            except Exception as e:
                log_error("process "+os.path.basename(ply), e)
                self._export_fails.append(os.path.basename(ply)); continue
            for ext in (fmts or []):
                if self.cancel: return
                self.q.put(("prog", (i+1)/total, "Converting %s to %s"%(name, ext.upper())))
                try: m.export(ply[:-4]+"."+ext)
                except Exception as e:
                    log_error("convert %s -> %s"%(os.path.basename(ply), ext), e)
                    self._export_fails.append(os.path.basename(ply)[:-4]+"."+ext)

    def _import_full(self, name, dest, i, total):
        """Full project including raw frames - kept in the device's nested layout (needed to re-process)."""
        src=os.path.join(PROJECTS,name)+"/"; dst=os.path.join(dest,name)+"/"; os.makedirs(dst, exist_ok=True)
        cmd=["rsync","-a","--info=progress2",src,dst]
        self.q.put(("prog", i/total, "Project %d of %d - %s (full)"%(i+1,total,name)))
        self.proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for ln in self.proc.stdout:
            if self.cancel: self.proc.terminate(); break
            mm=re.search(r"(\d+)%",ln)
            if mm:
                fp=int(mm.group(1)); self.q.put(("prog",(i*100+fp)/(total*100),"Project %d of %d - %s (%d%%)"%(i+1,total,name,fp)))
        self.proc.wait()
        if self.proc.returncode not in (0,None) and not self.cancel: raise RuntimeError("rsync rc=%s"%self.proc.returncode)


    def on_cancel(self):
        self.cancel=True
        if self.proc:
            try: self.proc.terminate()
            except Exception: pass
    def open_folder(self): subprocess.Popen(["xdg-open", self.dest.get() or DEFAULT_DEST])

    # ---- 3D view ----
    def _find_mesh(self, name):
        """Largest mesh for a project: prefer the local flat copy, then a full-import mirror, then the device."""
        local=os.path.join(self.dest.get() or DEFAULT_DEST, name)
        flat=[p for p in glob.glob(os.path.join(local, name+"_*.ply")) if not p.endswith("_cloud.ply")]
        if flat:
            try: return max(flat, key=os.path.getsize)
            except Exception: return flat[0]
        for base in (local, os.path.join(PROJECTS, name)):
            plys=glob.glob(os.path.join(base, "data", "*", "fuse_mesh.ply"))
            if plys:
                try: return max(plys, key=os.path.getsize)
                except Exception: return plys[0]
        return None
    def on_view_3d(self):
        name=self.selected
        if not name: return
        src=self._find_mesh(name)
        if not src:
            self.set_banner("No mesh found for this project.", WARN); return
        self.set_status("Loading 3D view — reading the mesh…")
        self._open_loader("Loading 3D view", "Reading the mesh… large scans take a few seconds.")
        threading.Thread(target=self._view_worker, args=(name, src), daemon=True).start()
    def _view_worker(self, name, src):
        # if the mesh is on the (slow) device mount, copy it to a local cache first
        path=src
        if src.startswith(PROJECTS):
            try:
                cache=os.path.join(THUMBS, "view"); os.makedirs(cache, exist_ok=True)
                path=os.path.join(cache, name+"_fuse_mesh.ply")
                if not os.path.exists(path) or os.path.getsize(path)!=os.path.getsize(src):
                    self.q.put(("loader_msg", "Copying mesh from the scanner…"))
                    shutil.copyfile(src, path)
            except Exception as e:
                log_error("view-copy", e); self.q.put(("view_done", None)); return
        try:
            viewer=os.path.join(HERE, "viewer.py")
            proc=subprocess.Popen([_sys.executable, viewer, path, name],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for ln in proc.stdout:
                if "PYVIEW_READY" in ln: self.q.put(("view_done", None)); break
                if "PYVIEW_ERROR" in ln: log_line("viewer: "+ln.strip()); self.q.put(("view_done", ln.strip())); break
        except Exception as e:
            log_error("view-launch", e); self.q.put(("view_done", str(e)))

    # ---- base removal (interactive cut-plane) ----
    def on_remove_base(self):
        if getattr(self, "_basing", False): return
        name=self.selected
        if not name: return
        src=self._find_mesh(name)
        if not src:
            self.set_banner("No mesh found for this project.", WARN); return
        self._basing=True; self.base_btn.configure(state="disabled")
        self.set_status("Base removal — opening the cut-plane tool…")
        self._open_loader("Base removal", "Opening the cut-plane tool… large scans take a few seconds.")
        threading.Thread(target=self._base_worker, args=(name, src), daemon=True).start()
    def _base_worker(self, name, src):
        path=src; dest=self.dest.get() or DEFAULT_DEST; outdir=os.path.join(dest, name)
        if src.startswith(PROJECTS):   # on the slow device mount - copy locally first
            try:
                os.makedirs(outdir, exist_ok=True)
                path=os.path.join(outdir, name+"_fuse_mesh.ply")
                if not os.path.exists(path) or os.path.getsize(path)!=os.path.getsize(src):
                    self.q.put(("loader_msg", "Copying mesh from the scanner…"))
                    shutil.copyfile(src, path)
            except Exception as e:
                log_error("base-copy", e); self.q.put(("base_done", ("err", "copy failed"))); return
        out=os.path.splitext(path)[0]+"_clean.ply"
        try:
            tool=os.path.join(HERE, "cutplane.py")
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1",
                     POINTYOINK_MEM_CAP_GB=os.environ.get("POINTYOINK_MEM_CAP_GB", "10"))
            proc=subprocess.Popen([_sys.executable, tool, path, out],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
            for ln in proc.stdout:
                ln=ln.strip()
                if ln.startswith("CUT_READY"): self.q.put(("loader_close", None))
                elif ln.startswith("CUT_DONE"): self.q.put(("base_done", ("ok", out))); break
                elif ln.startswith("CUT_CANCELLED"): self.q.put(("base_done", ("cancel", None))); break
                elif ln.startswith("CUT_ERROR"): log_line("cutplane: "+ln); self.q.put(("base_done", ("err", ln))); break
        except Exception as e:
            log_error("base-launch", e); self.q.put(("base_done", ("err", str(e))))

    # ---- screenshots ----
    def refresh_screenshots(self):
        if not quick_mounted():
            self.set_banner("Connect the scanner to see its screenshots.", WARN); return
        self.set_status("Reading screenshots off the device…")
        threading.Thread(target=self._shots_worker, daemon=True).start()
    def _shots_worker(self):
        items=list_screenshots(); local=[]
        cache=os.path.join(THUMBS, "shots"); os.makedirs(cache, exist_ok=True)
        for i,(nm,path) in enumerate(items):
            dst=os.path.join(cache, nm)
            try:
                if not os.path.exists(dst) or os.path.getsize(dst)!=os.path.getsize(path):
                    self.q.put(("status", "Loading screenshot %d/%d…"%(i+1, len(items))))
                    shutil.copyfile(path, dst)
                local.append((nm, dst))
            except Exception as e: log_error("shot-copy "+nm, e)
        # recordings: don't copy the (large) video for display - keep the device path + size
        recs=[]
        for nm,path in list_recordings():
            try: recs.append((nm, path, os.path.getsize(path)))
            except Exception: recs.append((nm, path, 0))
        self.q.put(("shots", (local, recs)))
    def render_shots(self, data):
        images, recs = data
        self._shots_items=images; self._recs=recs
        for w in self.shots.winfo_children(): w.destroy()
        self.shots_lbl.configure(text="%d screenshot%s · %d recording%s on the device"
                                 % (len(images), "" if len(images)==1 else "s", len(recs), "" if len(recs)==1 else "s"))
        if not images and not recs:
            ctk.CTkLabel(self.shots, text="Nothing found on the device.\n(Take a screenshot or recording on the scanner, then Refresh.)",
                         text_color=MUT, justify="left").grid(row=0,column=0, padx=20, pady=20, sticky="w"); return
        idx=0
        for nm,path in images:
            r,c=divmod(idx, 4); idx+=1
            cell=ctk.CTkFrame(self.shots, fg_color=CARD2, corner_radius=10); cell.grid(row=r,column=c, padx=6, pady=6, sticky="nsew")
            try:
                self.imgs["shot_"+nm]=cimg(path, 150)
                lbl=ctk.CTkLabel(cell, image=self.imgs["shot_"+nm], text=""); lbl.pack(padx=6, pady=(6,2))
                lbl.bind("<Button-1>", lambda e,p=path: self._enlarge(p))
            except Exception:
                ctk.CTkLabel(cell, text="(image)", text_color=MUT).pack(padx=20, pady=20)
            ctk.CTkLabel(cell, text=nm[:20], text_color=MUT, font=ctk.CTkFont(size=9)).pack(pady=(0,6))
        for nm,path,sz in recs:
            r,c=divmod(idx, 4); idx+=1
            cell=ctk.CTkFrame(self.shots, fg_color=CARD2, corner_radius=10); cell.grid(row=r,column=c, padx=6, pady=6, sticky="nsew")
            ctk.CTkLabel(cell, text="▶", text_color=AC, font=ctk.CTkFont(size=40)).pack(padx=6, pady=(14,2))
            ctk.CTkLabel(cell, text=nm[:20], text_color=MUT, font=ctk.CTkFont(size=9)).pack()
            ctk.CTkLabel(cell, text=human(sz), text_color="#5a6474", font=ctk.CTkFont(size=9)).pack(pady=(0,8))
    def pull_screenshots(self):
        imgs=getattr(self, "_shots_items", []); recs=getattr(self, "_recs", [])
        if not imgs and not recs:
            self.set_banner("Nothing to pull - hit Refresh first.", MUT); return
        dest=os.path.join(self.dest.get() or DEFAULT_DEST, "captures"); os.makedirs(dest, exist_ok=True)
        self.set_status("Pulling screenshots & recordings…")
        threading.Thread(target=self._pull_shots_worker, args=(list(imgs), list(recs), dest), daemon=True).start()
    def _pull_shots_worker(self, imgs, recs, dest):
        n=0
        for nm,path in imgs:
            try: shutil.copyfile(path, os.path.join(dest, nm)); n+=1
            except Exception as e: log_error("pull-shot "+nm, e)
        for j,(nm,path,sz) in enumerate(recs):
            try:
                self.q.put(("status", "Pulling recording %d/%d (%s)…"%(j+1, len(recs), human(sz))))
                shutil.copyfile(path, os.path.join(dest, nm)); n+=1
            except Exception as e: log_error("pull-rec "+nm, e)
        self.q.put(("shots_pulled", (n, dest)))

    def _open_loader(self, title, msg):
        if getattr(self,"_loader",None):
            try: self._loader.destroy()
            except Exception: pass
        t=ctk.CTkToplevel(self); t.title(title); t.configure(fg_color=BG); t.resizable(False,False)
        try: t.transient(self); t.attributes("-topmost",True)
        except Exception: pass
        w,h=380,150
        try:
            self.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w)//2; y=self.winfo_rooty()+(self.winfo_height()-h)//3
            t.geometry("%dx%d+%d+%d"%(w,h,x,y))
        except Exception: pass
        card=ctk.CTkFrame(t, fg_color=CARD, corner_radius=14); card.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(family=WORDMARK, size=15,weight="bold"), text_color=TX).pack(anchor="w", padx=18, pady=(16,2))
        self._loader_msg=ctk.CTkLabel(card, text=msg, text_color=MUT, font=ctk.CTkFont(size=12), wraplength=320, justify="left")
        self._loader_msg.pack(anchor="w", padx=18)
        pb=ctk.CTkProgressBar(card, mode="indeterminate", height=6, corner_radius=3, progress_color=AC); pb.pack(fill="x", padx=18, pady=(14,16)); pb.start()
        self._loader=t
    def _close_loader(self):
        t=getattr(self,"_loader",None)
        if t:
            try: t.destroy()
            except Exception: pass
            self._loader=None

    # ---- export zip ----
    def on_export_zip(self):
        if self.pulling: return
        sel=[n for n,v in self.pull_sel.items() if v.get()]
        if not sel:
            self.set_banner("Tick the project(s) you want to zip.", WARN); return
        dest=self.dest.get() or DEFAULT_DEST
        try: sizes=self._estimate_sizes(sel, dest)
        except Exception: sizes=None
        mode=self._ask_zip_format(sizes)
        if not mode: return
        missing=[n for n in sel if not os.path.isdir(os.path.join(dest,n))]
        if missing:
            if self._confirm("Import first?",
                    "%d selected project(s) haven't been imported yet, so there's nothing local to zip:\n%s\n\nImport them now, then zip?"%(len(missing), ", ".join(self.disp(n) for n in missing))):
                self._zip_after=sel; self._zip_mode=mode
                for n,v in self.pull_sel.items(): v.set(n in sel)
                self.on_pull(); return
            sel=[n for n in sel if n not in missing]
            if not sel:
                self.set_banner("Nothing to zip.", MUT); return
        self._start_zip(sel, dest, mode)
    def _ask_zip_format(self, sizes=None):
        """Choose what goes in the zip. Returns 'stl'/'obj'/'glb'/'models'/'all' or None."""
        t=ctk.CTkToplevel(self); t.title("Export ZIP"); t.configure(fg_color=BG); t.resizable(False,False)
        try: t.transient(self); t.attributes("-topmost",True)
        except Exception: pass
        w,h=470,410
        try:
            self.update_idletasks()
            x=self.winfo_rootx()+(self.winfo_width()-w)//2; y=self.winfo_rooty()+(self.winfo_height()-h)//3
            t.geometry("%dx%d+%d+%d"%(w,h,x,y))
        except Exception: pass
        res={"v":None}
        card=ctk.CTkFrame(t, fg_color=CARD, corner_radius=14); card.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(card, text="Export ZIP", font=ctk.CTkFont(family=WORDMARK, size=15,weight="bold"), text_color=TX).pack(anchor="w", padx=18, pady=(16,2))
        ctk.CTkLabel(card, text="What should go in the zip? Files are added flat with clean names.",
                     text_color=MUT, font=ctk.CTkFont(size=12), wraplength=410, justify="left").pack(anchor="w", padx=18, pady=(0,10))
        def pick(v): res["v"]=v; t.destroy()
        opts=[("STL only","stl","for 3D printing"),("OBJ only","obj","for editing"),
              ("GLB only","glb","for the web / editing"),
              ("All models","models","every PLY, STL, OBJ, GLB"),
              ("Everything","all","models, previews, metadata")]
        for label,val,hint in opts:
            row=ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=16, pady=3)
            ctk.CTkButton(row, text=label, width=120, height=32, corner_radius=16, fg_color=CARD2,
                          hover_color=AC, text_color=TX, anchor="w", command=lambda v=val: pick(v)).pack(side="left")
            szt=""
            if sizes and sizes.get(val):
                szt="≈ "+human(sizes[val])
            ctk.CTkLabel(row, text=szt, text_color=(AC if sizes and sizes.get(val,0)>0 else MUT),
                         font=ctk.CTkFont(size=11,weight="bold"), width=78, anchor="e").pack(side="right")
            ctk.CTkLabel(row, text=hint, text_color=MUT, font=ctk.CTkFont(size=11)).pack(side="left", padx=10)
        ctk.CTkLabel(card, text="Sizes are rough estimates before compression - the real zip is smaller.",
                     text_color=MUT, font=ctk.CTkFont(size=10), wraplength=410, justify="left").pack(anchor="w", padx=18, pady=(8,0))
        try:
            t.grab_set(); t.wait_window()
        except Exception: pass
        return res["v"]
    def _mesh_cloud_sources(self, name, dest):
        """(mesh_plys, cloud_plys) for a project: local flat > local nested > device nested."""
        local=os.path.join(dest, name)
        m=[p for p in glob.glob(os.path.join(local, name+"_*.ply")) if not p.endswith("_cloud.ply")]
        c=glob.glob(os.path.join(local, name+"_*_cloud.ply"))
        if not m:
            m=glob.glob(os.path.join(local, "data","*","fuse_mesh.ply")) or glob.glob(os.path.join(PROJECTS, name, "data","*","fuse_mesh.ply"))
            c=glob.glob(os.path.join(local, "data","*","fuse.ply")) or glob.glob(os.path.join(PROJECTS, name, "data","*","fuse.ply"))
        return m, c
    def _estimate_sizes(self, sel, dest):
        """Rough uncompressed byte estimates per zip mode. The real zip is smaller (compressed)."""
        est={"stl":0,"obj":0,"glb":0,"models":0,"all":0}
        for name in sel:
            meshes,clouds=self._mesh_cloud_sources(name, dest)
            ply_bytes=0
            for mp in meshes:
                try: ply_bytes+=os.path.getsize(mp)
                except Exception: pass
                v,f=_ply_counts(mp)
                # use the real converted file if it already exists, else estimate from the mesh
                for mode,estfn in (("stl",84+50*f),("obj",v*22+f*24),("glb",v*28+f*12+2048)):
                    conv=mp[:-4]+"."+mode
                    est[mode]+= os.path.getsize(conv) if os.path.exists(conv) else estfn
            for cp in clouds:
                try: ply_bytes+=os.path.getsize(cp)
                except Exception: pass
            est["models"]+=ply_bytes
            # everything = models + previews + metadata. Walk the folder only when it's LOCAL
            # (walking the slow device mount here would freeze the dialog); otherwise approximate.
            localdir=os.path.join(dest,name)
            if os.path.isdir(localdir):
                allb=0
                for root,dirs,fs in os.walk(localdir):
                    dirs[:]=[d for d in dirs if d!="cache"]
                    for fn in fs:
                        try: allb+=os.path.getsize(os.path.join(root,fn))
                        except Exception: pass
                est["all"]+=allb
            else:
                est["all"]+=int(ply_bytes*1.03)+256*1024   # models + a little for previews/metadata
        return est
    def _start_zip(self, sel, dest, mode):
        self.pulling=True
        self.zip_btn.configure(state="disabled")
        self.progress.grid(row=1,column=0, columnspan=4, sticky="ew", pady=(8,0)); self.progline.grid(row=2,column=0, columnspan=4, sticky="w")
        threading.Thread(target=self._zip_worker, args=(sel,dest,mode), daemon=True).start()
    def _project_meshes(self, base, name):
        """Mesh .ply files for an imported project (flat layout, else nested mirror)."""
        flat=[p for p in glob.glob(os.path.join(base, name+"_*.ply")) if not p.endswith("_cloud.ply")]
        if flat: return sorted(flat)
        return sorted(glob.glob(os.path.join(base, "data", "*", "fuse_mesh.ply")))
    def _zip_worker(self, sel, dest, mode):
        import zipfile
        os.makedirs(dest, exist_ok=True)
        tag={"stl":"stl","obj":"obj","glb":"glb","models":"models","all":"full"}.get(mode,mode)
        if len(sel)==1:
            zpath=os.path.join(dest, "%s_%s.zip"%(sel[0], tag))
        else:
            zpath=os.path.join(dest, "pointyoink-%s-%s.zip"%(tag, time.strftime("%Y%m%d-%H%M%S")))
        # build the file list (src, arcname). flat for models/format modes; nested for 'all'
        files=[]
        try:
            for name in sel:
                base=os.path.join(dest, name)
                if mode in ("stl","obj","glb"):
                    for ply in self._project_meshes(base, name):
                        # name flat & unique: <name>_<node>.<ext>
                        node=os.path.basename(os.path.dirname(ply)) if os.sep+"data"+os.sep in ply else os.path.basename(ply)[:-4]
                        stem=node if node.startswith(name) else "%s_%s"%(name,node)
                        target=os.path.join(os.path.dirname(ply), stem+"."+mode)
                        if not os.path.exists(target):
                            self.q.put(("prog", 0.0, "Converting %s to %s…"%(name, mode.upper())))
                            try:
                                import trimesh; trimesh.load(ply, force="mesh").export(target)
                            except Exception as e: log_error("zip-convert "+os.path.basename(ply), e); continue
                        files.append((target, os.path.basename(target)))
                elif mode=="models":
                    for f in glob.glob(os.path.join(base,"*")):
                        if f.lower().endswith((".ply",".stl",".obj",".glb")): files.append((f, os.path.basename(f)))
                    for f in glob.glob(os.path.join(base,"data","*","*")):
                        if f.lower().endswith((".ply",".stl",".obj",".glb")): files.append((f, os.path.basename(f)))
                else:  # all
                    for root,dirs,fs in os.walk(base):
                        dirs[:]=[d for d in dirs if d!="cache"]
                        for f in fs: fp=os.path.join(root,f); files.append((fp, os.path.join(name, os.path.relpath(fp, base))))
            if not files:
                self.q.put(("zipfail", "no matching files (try importing with that format first)")); return
            total=len(files); zfails=0
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for i,(fp,arc) in enumerate(files):
                    self.q.put(("prog", i/total, "Zipping %d/%d - %s"%(i+1,total,os.path.basename(fp))))
                    try: z.write(fp, arc)
                    except Exception as e: zfails+=1; log_error("zip "+arc, e)
            self.q.put(("zipped", zpath, os.path.getsize(zpath), zfails))
        except Exception as e:
            log_error("zip", e); self.q.put(("zipfail", str(e)))
    def _finish(self, dest, failed, cancelled=False):
        self.pulling=False; self.cancel_btn.grid_remove(); self.import_btn.grid(row=0,column=3)
        try:
            if self.progress.cget("mode")=="indeterminate": self.progress.stop(); self.progress.configure(mode="determinate")
        except Exception: pass
        self.progress.set(0); self.progress.grid_remove()
        if cancelled: self.progline.configure(text="Cancelled."); self.set_banner("Import cancelled.", WARN)
        elif failed:
            self.progline.configure(text="Done with errors: "+", ".join(failed))
            if self._confirm("Some imports failed", "Some projects failed:\n"+"\n".join(failed)+"\n\nRetry those?"):
                for n,v in self.pull_sel.items(): v.set(n in failed)
                self.on_pull(); return
        else:
            for n in getattr(self, "_pull_list", []):
                if n not in failed:
                    p=self._proj(n) or {}
                    self.records.setdefault(n, {}).update(
                        imported_to=os.path.join(dest, n), imported_at=int(time.time()),
                        sig={"edit_time":p.get("edit_time"), "nodes":p.get("nodes"), "meshes":p.get("meshes")})
            self._persist()
            ef=getattr(self, "_export_fails", [])
            if ef:
                self.progline.configure(text="Imported, but %d export(s) failed."%len(ef))
                self.set_banner("Import done, but %d file(s) failed to export - see Help > Log: %s"
                                % (len(ef), ", ".join(ef[:3]) + ("…" if len(ef)>3 else "")), WARN)
            else:
                self.progline.configure(text="Done."); self.set_banner("Import complete.", OK)
            self.projects_sig=None
            za=getattr(self, "_zip_after", None)
            if za:
                self._zip_after=None
                mode=getattr(self,"_zip_mode","models"); self._zip_mode=None
                self._start_zip([n for n in za if os.path.isdir(os.path.join(dest,n))], dest, mode); return
            if self.auto_open.get(): self.open_folder()

    # ---- queue ----
    def drain_loop(self):
        try:
            while True:
                kind,*rest=self.q.get_nowait()
                if kind=="mounted":
                    ok,msg=rest; self._mounting=False
                    if ok: self.listed=False
                    else: self.set_banner("Couldn't connect: "+msg, WARN); log_line("mount failed: "+msg)
                elif kind=="projects":
                    self.listing=False; self.listed=True; self.render_list(rest[0])
                    if not getattr(self, "_shots_loaded", False):   # auto-load device screenshots once
                        self._shots_loaded=True; self.refresh_screenshots()
                elif kind=="sizes": self.projects_sig=None; self.update_summary()
                elif kind=="gallery": n,items=rest; self.gallery_cache[n]=items; self.render_gallery(n,items)
                elif kind=="files":
                    n,(tot,files)=rest
                    if self.selected==n:
                        self.files_box.configure(state="normal"); self.files_box.delete("1.0","end")
                        self.files_box.insert("end","Model files in %s  (total %s)\n\n"%(n,human(tot)))
                        for node,fn,sz in sorted(files,key=lambda x:-x[2]):
                            self.files_box.insert("end","  %-5s %9s   %s/%s\n"%("MESH" if "mesh" in fn else "CLOUD", human(sz), node, fn))
                        self.files_box.configure(state="disabled")
                elif kind=="prog":
                    frac,line=rest
                    if "Converting" in line:                       # conversion has no % - animate instead of sitting at 99%
                        if self.progress.cget("mode")!="indeterminate":
                            self.progress.configure(mode="indeterminate"); self.progress.start()
                    else:
                        if self.progress.cget("mode")=="indeterminate":
                            self.progress.stop(); self.progress.configure(mode="determinate")
                        self.progress.set(frac)
                    self.progline.configure(text=line)
                elif kind=="done": self._finish(rest[0],rest[1])
                elif kind=="cancelled": self._finish(rest[0],rest[1], cancelled=True)
                elif kind=="zipped":
                    zpath,sz,zfails=rest; self.pulling=False; self.zip_btn.configure(state="normal")
                    self.progress.set(0); self.progress.grid_remove()
                    self.progline.configure(text="Zipped -> %s (%s)"%(os.path.basename(zpath), human(sz)))
                    if zfails:
                        self.set_banner("ZIP ready, but %d file(s) failed - see Help > Log."%zfails, WARN)
                    else:
                        self.set_banner("ZIP ready in your save folder.", OK)
                    if self.auto_open.get(): self.open_folder()
                elif kind=="zipfail":
                    self.pulling=False; self.zip_btn.configure(state="normal"); self.progress.grid_remove()
                    self.set_banner("ZIP failed: "+rest[0], WARN)
                elif kind=="loader_msg":
                    if getattr(self,"_loader_msg",None):
                        try: self._loader_msg.configure(text=rest[0])
                        except Exception: pass
                elif kind=="view_done":
                    self._close_loader(); self.set_status("")
                    if rest[0]: self.set_banner("3D view failed - see Help > Log.", WARN)
                elif kind=="status":
                    self.set_status(rest[0])
                elif kind=="shots":
                    self.render_shots(rest[0]); self.set_status("")
                elif kind=="shots_pulled":
                    n, d = rest[0]; self.set_status("")
                    self.set_banner("Pulled %d screenshot%s -> %s" % (n, "" if n==1 else "s", d), OK)
                    if self.auto_open.get(): subprocess.Popen(["xdg-open", d])
                elif kind=="loader_close":
                    self._close_loader()
                elif kind=="base_done":
                    self._close_loader(); self._basing=False
                    try: self.base_btn.configure(state="normal")
                    except Exception: pass
                    status, info = rest[0]
                    if status=="ok":
                        self.set_banner("Base removed -> %s" % os.path.basename(info), OK)
                        self.set_status("Base removed -> %s" % os.path.basename(info))
                        self.projects_sig=None   # refresh so the _clean file shows
                        if self.auto_open.get(): self.open_folder()
                    elif status=="cancel":
                        self.set_banner("Base removal cancelled.", MUT); self.set_status("")
                    else:
                        self.set_banner("Base removal failed - see Help > Log.", WARN); self.set_status("")
        except queue.Empty: pass
        self.after(200, self.drain_loop)

if __name__ == "__main__":
    App().mainloop()
