"""Smooth deterministic camera moves for still illustrations."""
def camera_filter(index, frames, width=1920, height=1080, fps=30):
    t = f"(on/{max(1,frames-1)})"
    e = f"({t}*{t}*(3-2*{t}))"
    mode = index % 3
    z = [f"1.02+0.16*{e}", f"1.18-0.16*{e}", "1.16"][mode]
    x = f"(iw-iw/zoom)*{e}" if mode == 2 else "(iw-iw/zoom)/2"
    return f"scale=3840:2160,zoompan=z='{z}':x='{x}':y='(ih-ih/zoom)/2':d={frames}:s={width}x{height}:fps={fps},setsar=1"
